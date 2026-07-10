from openai import AzureOpenAI
from config import AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_VERSION, CHAT_DEPLOYMENT

def get_chat_client() -> AzureOpenAI:
    return AzureOpenAI(
        api_key=AZURE_OPENAI_API_KEY,
        api_version=AZURE_OPENAI_API_VERSION,
        azure_endpoint=AZURE_OPENAI_ENDPOINT
    )

def analyze_transcript_roles(transcript_text: str, candidate_metadata: str, interviewer_names: str) -> str:
    client = get_chat_client()
    prompt = f"""
    Analyze the following interview transcript and determine the role of each participant.
    Candidate metadata: {candidate_metadata}
    Interviewer names: {interviewer_names}
    
    Determine:
    - Who mostly asks questions?
    - Who mostly answers questions?
    - Who introduces themselves?
    - Who explains technical concepts?
    - Who appears to be evaluated?
    - Who behaves like interviewer?
    - Who behaves like observer?

    Return a structured JSON output with the exact format:
    {{
      "participants": [
        {{
          "participant_name": "...",
          "role": "candidate|interviewer|observer",
          "confidence": 0-100,
          "reason": "..."
        }}
      ]
    }}
    
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
        try:
            response = client.chat.completions.create(
                model=CHAT_DEPLOYMENT,
                messages=[{"role": "user", "content": prompt + "\nEnsure you respond with strictly valid JSON only."}]
            )
            return response.choices[0].message.content
        except Exception as inner_e:
            return '{"participants": []}'

def analyze_transcript_mentions(transcript_text: str, candidate_name: str) -> str:
    client = get_chat_client()
    prompt = f"""
    Analyze the following interview transcript to find if any speaker is repeatedly addressing another participant using the candidate's name: '{candidate_name}'.
    
    Extract who is being addressed by this name.
    Return a structured JSON output with the exact format:
    {{
      "mentions": [
        {{
          "addressed_participant": "...",
          "addressed_as": "...",
          "reason": "..."
        }}
      ]
    }}
    
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
        try:
            response = client.chat.completions.create(
                model=CHAT_DEPLOYMENT,
                messages=[{"role": "user", "content": prompt + "\nEnsure you respond with strictly valid JSON only."}]
            )
            return response.choices[0].message.content
        except Exception as inner_e:
            return '{"mentions": []}'
