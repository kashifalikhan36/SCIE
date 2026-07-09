import pytest
import asyncio
from database.redis import RedisClientManager, get_redis

@pytest.mark.asyncio
async def test_redis_connection():
  """Test that Redis manager initializes and verifies Azure Redis connection."""
  manager = RedisClientManager.get_instance()
  manager.initialize()
  
  connected = await manager.check_connection()
  assert connected is True, "Redis connection check failed"

@pytest.mark.asyncio
async def test_redis_string_ops():
  """Test basic string GET, SET, and DELETE operations in Redis."""
  redis_client = await get_redis()
  assert redis_client is not None
  
  test_key = "pytest:test_string_key"
  test_val = "Hello Azure Redis!"
  
  # 1. SET
  set_ok = await redis_client.set(test_key, test_val)
  assert set_ok is True or str(set_ok) == "OK"
  
  # 2. GET
  retrieved_val = await redis_client.get(test_key)
  assert retrieved_val == test_val
  
  # 3. DELETE
  delete_count = await redis_client.delete(test_key)
  assert delete_count == 1
  
  # 4. GET again (should be None)
  val_after_del = await redis_client.get(test_key)
  assert val_after_del is None

@pytest.mark.asyncio
async def test_redis_hash_ops():
  """Test hash set and get operations."""
  redis_client = await get_redis()
  test_key = "pytest:test_hash_key"
  
  hash_data = {
      "username": "tester",
      "email": "tester@scie.io",
      "role": "admin"
  }
  
  # HSET
  hset_ok = await redis_client.hset(test_key, mapping=hash_data)
  assert hset_ok >= 0
  
  # HGETALL
  retrieved_hash = await redis_client.hgetall(test_key)
  assert retrieved_hash == hash_data
  
  # HGET individual
  username = await redis_client.hget(test_key, "username")
  assert username == "tester"
  
  # Clean up
  await redis_client.delete(test_key)
  exists = await redis_client.exists(test_key)
  assert exists == 0

@pytest.mark.asyncio
async def test_redis_expire():
  """Test Redis key expiration TTL."""
  redis_client = await get_redis()
  test_key = "pytest:test_expire_key"
  
  await redis_client.set(test_key, "temp_value", ex=10) # 10 seconds TTL
  
  ttl = await redis_client.ttl(test_key)
  assert 0 < ttl <= 10
  
  # Clean up
  await redis_client.delete(test_key)
