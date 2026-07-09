"""
Conversation Reasoning Engine custom exception hierarchy.

All exceptions derive from ConversationEngineException for uniform catch clauses
in the pipeline and worker layers.
"""


class ConversationEngineException(Exception):
  """Base exception for all Conversation Reasoning Engine errors."""


class AzureOpenAIClientError(ConversationEngineException):
  """Raised when the Azure OpenAI client fails to communicate or return valid data."""


class AzureOpenAITimeoutError(AzureOpenAIClientError):
  """Raised when an Azure OpenAI prompt completion times out."""


class JSONParseError(ConversationEngineException):
  """Raised when GPT output cannot be parsed into valid structured JSON."""


class TranscriptLoaderError(ConversationEngineException):
  """Raised when fetching or formatting transcript turns fails."""


class ReasoningExecutionError(ConversationEngineException):
  """Raised when prompt execution across conversation chunks encounters an unrecoverable error."""


class ConversationStorageError(ConversationEngineException):
  """Raised when MongoDB storage operations fail."""


class ConversationStateError(ConversationEngineException):
  """Raised when Redis state management operations fail."""


class PipelineExecutionError(ConversationEngineException):
  """Raised when the top-level conversation pipeline fails."""
