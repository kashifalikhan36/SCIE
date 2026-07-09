"""
Async Azure OpenAI client for the Conversation Reasoning Engine.

Responsibilities:
- Initialize AsyncAzureOpenAI client once (singleton).
- Send structured JSON requests to Azure OpenAI Foundry (GPT-5.5).
- Support automatic retry with exponential backoff for rate limits, timeouts, or malformed JSON.
- Measure latency and token usage without logging secrets or credentials.
"""
import asyncio
from typing import Dict, Any, Optional, Tuple
from openai import AsyncAzureOpenAI, APIError, APITimeoutError, RateLimitError

from engine.conversation.config import conversation_config
from engine.conversation.exceptions import AzureOpenAIClientError, AzureOpenAITimeoutError, JSONParseError
from engine.conversation.logger import logger
from engine.conversation.utils import extract_json_from_response


class ConversationAzureClient:
  """Singleton async Azure OpenAI client demanding structured JSON responses."""

  _instance: Optional["ConversationAzureClient"] = None
  _client: Optional[AsyncAzureOpenAI] = None

  @classmethod
  def get_instance(cls) -> "ConversationAzureClient":
    """Returns the process-wide singleton client instance."""
    if cls._instance is None:
      cls._instance = cls()
    return cls._instance

  def _get_client(self) -> Optional[AsyncAzureOpenAI]:
    """Lazy-initializes the AsyncAzureOpenAI client using config values."""
    if self._client is not None:
      return self._client

    api_key = conversation_config.AZURE_OPENAI_API_KEY
    endpoint = conversation_config.AZURE_OPENAI_ENDPOINT
    api_version = conversation_config.AZURE_OPENAI_API_VERSION

    if not api_key or not endpoint:
      logger.warning(
          "ConversationAzureClient: AZURE_OPENAI_API_KEY or AZURE_OPENAI_ENDPOINT not configured. "
          "Conversation reasoning will be unavailable or degraded."
      )
      return None

    try:
      self._client = AsyncAzureOpenAI(
          api_key=api_key,
          azure_endpoint=endpoint,
          api_version=api_version,
      )
      logger.info(
          f"ConversationAzureClient: Initialized AsyncAzureOpenAI for endpoint={endpoint}, "
          f"deployment={conversation_config.CONVERSATION_DEPLOYMENT_NAME}"
      )
      return self._client
    except Exception as exc:
      logger.error(f"ConversationAzureClient: Failed to initialize client: {exc}")
      return None

  async def complete_json(
      self,
      system_instruction: str,
      user_prompt: str,
      deployment_name: Optional[str] = None,
      temperature: Optional[float] = None,
      max_tokens: Optional[int] = None
  ) -> Tuple[Dict[str, Any], int]:
    """Execute a chat completion request returning parsed JSON dictionary and total tokens used.

    Performs exponential backoff retries on transient errors or malformed JSON outputs.
    """
    client = self._get_client()
    if client is None:
      raise AzureOpenAIClientError("Azure OpenAI client is unconfigured or failed initialization.")

    deployment = deployment_name or conversation_config.CONVERSATION_DEPLOYMENT_NAME
    temp = temperature if temperature is not None else conversation_config.TEMPERATURE
    tokens = max_tokens if max_tokens is not None else conversation_config.MAX_TOKENS
    retries = conversation_config.RETRY_COUNT
    delay = conversation_config.RETRY_DELAY_SEC

    last_error = None
    for attempt in range(1, retries + 1):
      try:
        logger.debug(f"Executing Azure OpenAI completion (attempt {attempt}/{retries}) for deployment={deployment}")
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=deployment,
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=temp,
                max_tokens=tokens,
                response_format={"type": "json_object"}
            ),
            timeout=conversation_config.TIMEOUT_SEC
        )

        content = response.choices[0].message.content or "{}"
        total_tokens = response.usage.total_tokens if response.usage else 0

        parsed_json = extract_json_from_response(content)
        logger.debug(f"Prompt completion successful ({total_tokens} tokens)")
        return parsed_json, total_tokens

      except APITimeoutError as exc:
        last_error = exc
        logger.warning(f"Timeout on Azure OpenAI request (attempt {attempt}/{retries}): {exc}")
      except asyncio.TimeoutError as exc:
        last_error = exc
        logger.warning(f"Asyncio timeout ({conversation_config.TIMEOUT_SEC}s) on Azure OpenAI request (attempt {attempt}/{retries})")
      except RateLimitError as exc:
        last_error = exc
        logger.warning(f"Rate limit hit on Azure OpenAI (attempt {attempt}/{retries}): {exc}")
      except JSONParseError as exc:
        last_error = exc
        logger.warning(f"JSON parsing error on model response (attempt {attempt}/{retries}): {exc}")
      except APIError as exc:
        last_error = exc
        logger.error(f"Azure OpenAI API error (attempt {attempt}/{retries}): {exc}")
      except Exception as exc:
        last_error = exc
        logger.error(f"Unexpected error calling Azure OpenAI (attempt {attempt}/{retries}): {exc}")

      if attempt < retries:
        await asyncio.sleep(delay * (2 ** (attempt - 1)))

    if isinstance(last_error, (APITimeoutError, asyncio.TimeoutError)):
      raise AzureOpenAITimeoutError(f"Azure OpenAI prompt timed out after {retries} attempts: {last_error}") from last_error
    raise AzureOpenAIClientError(f"Azure OpenAI completion failed after {retries} attempts: {last_error}") from last_error
