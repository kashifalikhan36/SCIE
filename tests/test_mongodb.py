import pytest
from database.mongodb import MongoClientManager, get_mongo_db, get_mongo_client

@pytest.mark.asyncio
async def test_mongodb_connection():
  """Test that MongoDB manager initializes, connects, and checks connection successfully."""
  manager = MongoClientManager.get_instance()
  manager.initialize()
  
  connected = await manager.check_connection()
  assert connected is True, "MongoDB connection check failed"

@pytest.mark.asyncio
async def test_mongodb_crud_operations():
  """Test inserting, reading, updating, and deleting documents in local MongoDB SCIE-mg database."""
  db = get_mongo_db()
  assert db is not None
  
  test_col = db["pytest_test_collection"]
  
  # Ensure clean slate
  await test_col.delete_many({})
  
  # 1. CREATE
  test_doc = {"name": "Test Document", "type": "pytest", "version": 1}
  insert_result = await test_col.insert_one(test_doc)
  assert insert_result.inserted_id is not None
  doc_id = insert_result.inserted_id
  
  # 2. READ
  retrieved_doc = await test_col.find_one({"_id": doc_id})
  assert retrieved_doc is not None
  assert retrieved_doc["name"] == "Test Document"
  assert retrieved_doc["type"] == "pytest"
  assert retrieved_doc["version"] == 1
  
  # 3. UPDATE
  update_result = await test_col.update_one(
      {"_id": doc_id},
      {"$set": {"version": 2, "status": "updated"}}
  )
  assert update_result.modified_count == 1
  
  updated_doc = await test_col.find_one({"_id": doc_id})
  assert updated_doc["version"] == 2
  assert updated_doc["status"] == "updated"
  
  # 4. DELETE
  delete_result = await test_col.delete_one({"_id": doc_id})
  assert delete_result.deleted_count == 1
  
  deleted_doc = await test_col.find_one({"_id": doc_id})
  assert deleted_doc is None

@pytest.mark.asyncio
async def test_mongodb_multiple_documents():
  """Test batch operations and counting in MongoDB."""
  db = get_mongo_db()
  test_col = db["pytest_test_collection"]
  await test_col.delete_many({})
  
  docs = [
      {"name": "doc_a", "index": 0},
      {"name": "doc_b", "index": 1},
      {"name": "doc_c", "index": 2}
  ]
  
  insert_result = await test_col.insert_many(docs)
  assert len(insert_result.inserted_ids) == 3
  
  count = await test_col.count_documents({})
  assert count == 3
  
  # Clean up after test
  await test_col.delete_many({})
  count_after = await test_col.count_documents({})
  assert count_after == 0
