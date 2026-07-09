from typing import Generator

def get_db() -> Generator:
  try:
    db = "mock_db_session"
    yield db
  finally:
    pass
