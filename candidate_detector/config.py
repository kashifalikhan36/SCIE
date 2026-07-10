import os
from dotenv import load_dotenv

# Try to load .env from the current directory or parent directory
load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

WEIGHTS = {
    "Conversation Role": 25,
    "Transcript Mentions": 15,
    "Speaking Behaviour": 15,
    "Name Match": 15,
    "Identity Correlation": 15,
    "Join Timeline": 5,
    "Event Timeline": 5,
    "Webcam Behaviour": 5,
    "Screen Share": 3,
    "Metadata Consistency": 2
}

AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
CHAT_DEPLOYMENT = os.getenv("CHAT_DEPLOYMENT", "gpt-5.3-chat")
EMBEDDING_DEPLOYMENT = os.getenv("EMBEDDING_DEPLOYMENT", "text-embedding-3-large")
