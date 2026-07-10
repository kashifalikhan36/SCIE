from openai import AzureOpenAI
from .config import AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_VERSION, CHAT_DEPLOYMENT

def get_chat_client() -> AzureOpenAI:
    return AzureOpenAI(
        api_key=AZURE_OPENAI_API_KEY,
        api_version=AZURE_OPENAI_API_VERSION,
        azure_endpoint=AZURE_OPENAI_ENDPOINT
    )

def analyze_transcript_roles(transcript_text: str) -> str:
    """
    Calls Azure OpenAI to determine candidate vs interviewer roles
    based on the transcript.
    """
    client = get_chat_client()
    
    prompt = f"""
    Analyze the following interview transcript and determine the role of each participant.
    Identify who the 'candidate' is based on:
    - Who mostly asks questions?
    - Who mostly answers?
    - Did anyone introduce themselves?
    - Did the interviewer call anyone by name?
    
    Return a structured JSON output with the format:
    [
      {{
        "participant_name": "...",
        "role": "candidate|interviewer",
        "confidence": 0-100,
        "reason": "..."
      }}
    ]
    
    Transcript:
    {transcript_text}
    """
    
    try:
        response = client.chat.completions.create(
            model=CHAT_DEPLOYMENT,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return response.choices[0].message.content
    except Exception as e:
        # Fallback without json_object if model doesn't support it (like some reasoning deployments)
        try:
            response = client.chat.completions.create(
                model=CHAT_DEPLOYMENT,
                messages=[{"role": "user", "content": prompt + "\nEnsure you respond with strictly valid JSON only."}]
            )
            return response.choices[0].message.content
        except Exception as inner_e:
            return "[]"
