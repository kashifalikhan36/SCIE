import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
  PROJECT_NAME: str = "SCIE Backend"
  API_V1_STR: str = "/api/v1"
  
  # Directory where ingested meeting data is stored
  SAVE_DIR: str = os.path.join(
      os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
      "temp-saved-data"
  )

  # MongoDB Settings (local instance)
  MONGO_URI: str = "mongodb://localhost:27017"
  MONGO_DB: str = "SCIE-mg"

  # Redis Settings (Azure Cache for Redis or local)
  REDIS_URL: str | None = None
  REDIS_HOST: str = "localhost"
  REDIS_PORT: int = 6379
  REDIS_PASSWORD: str | None = None
  REDIS_SSL: bool = False

  model_config = SettingsConfigDict(
      case_sensitive=True,
      env_file=".env",
      extra="ignore"
  )

settings = Settings()
