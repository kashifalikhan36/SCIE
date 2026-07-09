import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
  PROJECT_NAME: str = "SCIE Backend"
  API_V1_STR: str = "/api/v1"
  
  # Directory where ingested meeting data is stored
  SAVE_DIR: str = os.path.join(
      os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
      "temp-saved-data"
  )

  class Config:
    case_sensitive = True

settings = Settings()
