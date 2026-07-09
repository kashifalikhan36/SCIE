import pytest
import pytest_asyncio
import asyncio
import os
import sys

# Add project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

@pytest.fixture(scope="session")
def event_loop():
  """Create an instance of the default event loop for the test session."""
  try:
    loop = asyncio.get_running_loop()
  except RuntimeError:
    loop = asyncio.new_event_loop()
  yield loop
  loop.close()

@pytest_asyncio.fixture(autouse=True)
async def cleanup_db_connections():
  """Automatically close connections and clear singletons between tests to prevent closed event loop errors."""
  yield
  from database.mongodb import MongoClientManager
  from database.redis import RedisClientManager
  
  await MongoClientManager.get_instance().close()
  await RedisClientManager.get_instance().close()
