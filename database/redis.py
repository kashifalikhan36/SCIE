import logging
from redis.asyncio import Redis, ConnectionPool
from core.config import settings

logger = logging.getLogger("SCIE.redis")

class RedisClientManager:
  _instance = None
  
  def __init__(self):
    self.pool = None
    self.client = None

  @classmethod
  def get_instance(cls):
    if cls._instance is None:
      cls._instance = cls()
    return cls._instance

  def initialize(self):
    """Initialize the Redis connection pool and client."""
    if self.client is not None:
      return
      
    try:
      if settings.REDIS_URL:
        # Azure Cache for Redis / connection URL configured in settings
        self.pool = ConnectionPool.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=50,
            socket_timeout=5.0,
            socket_connect_timeout=5.0,
            retry_on_timeout=True
        )
        logger.info("Redis client initialized from connection URL.")
      else:
        # Azure Cache for Redis requires SSL, password, and port 6380 (usually)
        # Standard Redis can use port 6379, no SSL, no password
        pool_kwargs = {
            "host": settings.REDIS_HOST,
            "port": settings.REDIS_PORT,
            "password": settings.REDIS_PASSWORD or None,
            "decode_responses": True,
            "max_connections": 50,
            "socket_timeout": 5.0,
            "socket_connect_timeout": 5.0,
            "retry_on_timeout": True
        }
        if settings.REDIS_SSL:
          pool_kwargs["ssl"] = True
          pool_kwargs["ssl_cert_reqs"] = None

        self.pool = ConnectionPool(**pool_kwargs)
        logger.info(f"Redis client initialized with host={settings.REDIS_HOST}, port={settings.REDIS_PORT}")
      
      self.client = Redis(connection_pool=self.pool)
    except Exception as e:
      logger.error(f"Failed to initialize Redis connection pool: {e}")
      self.client = None
      self.pool = None

  async def get_client(self) -> Redis:
    """Returns the Redis client, initializing it if necessary."""
    if self.client is None:
      self.initialize()
    return self.client

  async def close(self):
    """Close connection pool and client."""
    if self.client:
      try:
        # Use aclose() in newer redis-py versions, fallback to close()
        if hasattr(self.client, "aclose"):
          await self.client.aclose()
        else:
          await self.client.close()
      except Exception as e:
        logger.error(f"Error closing Redis client: {e}")
      self.client = None
    if self.pool:
      try:
        await self.pool.disconnect()
      except Exception as e:
        logger.error(f"Error disconnecting Redis pool: {e}")
      self.pool = None
    logger.info("Redis connection pool closed.")

  async def check_connection(self) -> bool:
    """Ping Redis to check connection status."""
    try:
      client = await self.get_client()
      if not client:
        return False
      await client.ping()
      logger.info("Redis ping successful!")
      return True
    except Exception as e:
      logger.warn(f"Redis ping failed: {e}")
      return False

# Reusable client getter
async def get_redis() -> Redis:
  manager = RedisClientManager.get_instance()
  return await manager.get_client()
