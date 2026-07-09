import logging
from motor.motor_asyncio import AsyncIOMotorClient
from core.config import settings

logger = logging.getLogger("SCIE.mongodb")

class MongoClientManager:
  _instance = None

  def __init__(self):
    self.client = None
    self.db = None

  @classmethod
  def get_instance(cls):
    if cls._instance is None:
      cls._instance = cls()
    return cls._instance

  def initialize(self):
    """Initialize the Motor client and database."""
    if self.client is not None:
      return

    try:
      # Motor client uses connection pooling automatically
      self.client = AsyncIOMotorClient(
          settings.MONGO_URI,
          serverSelectionTimeoutMS=5000,
          connectTimeoutMS=5000
      )
      self.db = self.client[settings.MONGO_DB]
      logger.info(f"MongoDB client initialized with URI: {settings.MONGO_URI}, database: {settings.MONGO_DB}")
    except Exception as e:
      logger.error(f"Failed to initialize MongoDB client: {e}")
      self.client = None
      self.db = None

  def get_db(self):
    """Returns the database instance, initializing if necessary."""
    if self.client is None:
      self.initialize()
    return self.db

  def get_client(self):
    """Returns the client instance, initializing if necessary."""
    if self.client is None:
      self.initialize()
    return self.client

  async def close(self):
    """Close MongoClient connection."""
    if self.client:
      self.client.close()
      self.client = None
      self.db = None
      logger.info("MongoDB client closed.")

  async def check_connection(self) -> bool:
    """Ping MongoDB to check connection status."""
    client = self.get_client()
    if not client:
      return False
    try:
      await client.admin.command('ping')
      logger.info("MongoDB ping successful!")
      return True
    except Exception as e:
      logger.error(f"MongoDB ping failed: {e}")
      return False

# Reusable database and client getters
def get_mongo_db():
  manager = MongoClientManager.get_instance()
  return manager.get_db()

def get_mongo_client():
  manager = MongoClientManager.get_instance()
  return manager.get_client()
