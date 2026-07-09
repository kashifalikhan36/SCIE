import pytest
import asyncio
import numpy as np
import time
import uuid
import os
import cv2
from engine.video.schemas import VideoChunk, DetectedFace, DiarizedTrack, VisualEvidence
from engine.video.frame_buffer import VideoFrameBuffer
from engine.video.frame_sampler import VideoFrameSampler
from engine.video.face_detector import FaceDetector
from engine.video.face_cropper import FaceCropper
from engine.video.tracker import FaceTracker
from engine.video.recognizer import FaceRecognizer
from engine.video.embedding_store import EmbeddingStore
from engine.video.comparator import EmbeddingComparator
from engine.video.pipeline import VideoEnginePipeline
from engine.video.workers import VideoEngineWorkerManager
from database.redis import get_redis
from database.mongodb import get_mongo_db

@pytest.mark.asyncio
async def test_video_buffer_reordering():
  """Test that VideoFrameBuffer buffers, reorders, and groups chunks correctly."""
  buf = VideoFrameBuffer(window_size_chunks=2)
  
  chunk_1 = VideoChunk(meeting_id="test_vid_mtg", timestamp=1000, chunk_index=1, data=b"c1")
  chunk_2 = VideoChunk(meeting_id="test_vid_mtg", timestamp=1250, chunk_index=2, data=b"c2")
  chunk_3 = VideoChunk(meeting_id="test_vid_mtg", timestamp=1500, chunk_index=3, data=b"c3")
  
  buf.add_chunk(chunk_3)
  buf.add_chunk(chunk_1)
  
  # Window of size 2 is not ready because index 2 is missing
  assert buf.get_next_window() is None
  
  buf.add_chunk(chunk_2)
  
  window = buf.get_next_window()
  assert window is not None
  assert len(window) == 2
  assert window[0].chunk_index == 1
  assert window[1].chunk_index == 2

@pytest.mark.asyncio
async def test_video_buffer_gap_recovery():
  """Test that VideoFrameBuffer recovers if intermediate packets are missing."""
  buf = VideoFrameBuffer(window_size_chunks=1)
  # Gap threshold is 4 chunks
  chunk_1 = VideoChunk(meeting_id="test_vid_mtg", timestamp=1000, chunk_index=1, data=b"c1")
  # 2, 3, 4, 5 lost
  chunk_6 = VideoChunk(meeting_id="test_vid_mtg", timestamp=2250, chunk_index=6, data=b"c6")
  
  buf.add_chunk(chunk_1)
  
  # Retrieve chunk 1
  win_1 = buf.get_next_window()
  assert win_1 is not None
  assert win_1[0].chunk_index == 1
  
  # Buffer is now expecting 2. Add 6 (creating gap of 4: 2, 3, 4, 5)
  buf.add_chunk(chunk_6)
  
  # It should trigger gap recovery and advance expected index to 6
  win_6 = buf.get_next_window()
  assert win_6 is not None
  assert win_6[0].chunk_index == 6

def test_face_detector_and_cropper():
  """Test FaceDetector localization and FaceCropper crop resize logic."""
  detector = FaceDetector()
  cropper = FaceCropper(target_size=112)
  
  # Create a solid gray frame (color variability std_dev > 10.0 to trigger mock face)
  frame = np.ones((480, 640, 3), dtype=np.uint8) * 128
  # Draw a simulated shape to increase variance
  frame[100:300, 200:400] = 200
  
  detected = detector.detect_faces(frame, frame_id=1, timestamp=1000)
  
  assert len(detected) == 1
  face = detected[0]
  assert isinstance(face, DetectedFace)
  assert face.confidence > 0.5
  
  # Test cropper on detected face
  cropped = cropper.crop_face(frame, face)
  assert cropped.shape == (112, 112, 3)

def test_face_tracker():
  """Test that FaceTracker tracks active faces, assigns stable IDs, and expires old ones."""
  tracker = FaceTracker()
  
  face_a = DetectedFace(bbox=(0.3, 0.2, 0.3, 0.4), confidence=0.9, frame_id=1, timestamp=1000)
  face_b = DetectedFace(bbox=(0.7, 0.7, 0.2, 0.2), confidence=0.8, frame_id=1, timestamp=1000)
  
  # 1. Update first frame
  tracks_1 = tracker.update([face_a, face_b], timestamp=1000)
  assert len(tracks_1) == 2
  
  # Extract IDs
  id_a = tracks_1[0].track_id
  id_b = tracks_1[1].track_id
  
  # 2. Update second frame (face A shifts slightly, face B shifts slightly)
  face_a_shifted = DetectedFace(bbox=(0.32, 0.21, 0.3, 0.4), confidence=0.9, frame_id=2, timestamp=2000)
  face_b_shifted = DetectedFace(bbox=(0.71, 0.71, 0.2, 0.2), confidence=0.8, frame_id=2, timestamp=2000)
  
  tracks_2 = tracker.update([face_a_shifted, face_b_shifted], timestamp=2000)
  assert len(tracks_2) == 2
  
  # Tracks should preserve IDs due to bbox overlaps (IoU >= 0.3)
  assert tracks_2[0].track_id == id_a
  assert tracks_2[1].track_id == id_b

@pytest.mark.asyncio
async def test_face_recognizer_and_comparator():
  """Test embedding extraction, store scheduling in Redis, and similarity comparing."""
  recognizer = FaceRecognizer()
  store = EmbeddingStore()
  comparator = EmbeddingComparator()
  
  meeting_id = "pytest_vid_rec_meeting"
  track_id = "Track_1"
  
  # Clear existing schedule from Redis
  redis_client = await get_redis()
  assert redis_client is not None
  await redis_client.delete(f"scie:meeting:{meeting_id}:video:embeddings")
  await redis_client.delete(f"scie:meeting:{meeting_id}:video:schedule")
  
  dummy_face = np.ones((112, 112, 3), dtype=np.uint8) * 128
  
  # 1. Test embedding generation
  embedding, confidence = await recognizer.generate_embedding(dummy_face, track_id)
  assert len(embedding) == 512
  assert confidence > 0.0
  
  # 2. Test cache check (is empty first)
  should_refresh = await store.should_refresh_embedding(meeting_id, track_id, frame_id=1)
  assert should_refresh is True
  
  # Save embedding
  await store.store_embedding(meeting_id, track_id, embedding, frame_id=1)
  
  # 3. Test caching scheduler (should not refresh on immediate next frame)
  should_refresh_next = await store.should_refresh_embedding(meeting_id, track_id, frame_id=2)
  assert should_refresh_next is False
  
  # 4. Test compare similarity
  cmp_res = comparator.compare(embedding, embedding)
  assert cmp_res["similarity_score"] == pytest.approx(1.0)
  assert cmp_res["distance"] == pytest.approx(0.0)
  
  # Clean up Redis
  await redis_client.delete(f"scie:meeting:{meeting_id}:video:embeddings")
  await redis_client.delete(f"scie:meeting:{meeting_id}:video:schedule")

@pytest.mark.asyncio
async def test_video_pipeline_execution():
  """Test the end-to-end execution of VideoEnginePipeline using mock chunks."""
  pipeline = VideoEnginePipeline()
  meeting_id = "pytest_vid_pipeline_meeting"
  
  # Clear databases
  mongo_db = get_mongo_db()
  assert mongo_db is not None
  await mongo_db["meetings"].delete_many({"meeting_id": meeting_id})
  await mongo_db["video_frames"].delete_many({"meeting_id": meeting_id})
  await mongo_db["face_tracks"].delete_many({"meeting_id": meeting_id})
  await mongo_db["face_embeddings"].delete_many({"meeting_id": meeting_id})
  await mongo_db["visual_evidence"].delete_many({"meeting_id": meeting_id})
  
  redis_client = await get_redis()
  await redis_client.delete(f"scie:meeting:{meeting_id}:video:embeddings")
  await redis_client.delete(f"scie:meeting:{meeting_id}:video:schedule")
  
  # Create a valid video file in scratch folder (solid color, short duration)
  scratch_dir = "C:/Users/Data/.gemini/antigravity-ide/brain/d6307dde-df5b-41e8-8fc8-2c1c794199ce/scratch"
  os.makedirs(scratch_dir, exist_ok=True)
  video_file_path = os.path.join(scratch_dir, "test_video.webm")
  
  # Write a mock WebM file
  # Note: A real video file is needed for OpenCV capture.
  # We can write a simple mock video using OpenCV VideoWriter if available, or just mock the file read.
  # Let's create a minimal video file!
  fourcc = cv2.VideoWriter_fourcc(*'VP80')
  out = cv2.VideoWriter(video_file_path, fourcc, 10.0, (640, 480))
  for _ in range(5): # 5 frames
    frame = np.ones((480, 640, 3), dtype=np.uint8) * 128
    frame[100:300, 200:400] = 200
    out.write(frame)
  out.release()

  chunk = VideoChunk(
      meeting_id=meeting_id,
      timestamp=int(time.time() * 1000),
      chunk_index=1,
      data=b"", # data can be empty since we provide file_path
      file_path=video_file_path
  )

  # Process window
  evidences = await pipeline.process_window(meeting_id, [chunk])
  
  assert len(evidences) > 0
  evidence = evidences[0]
  assert evidence.meeting_id == meeting_id
  assert evidence.track_id is not None
  assert len(evidence.face_embedding) == 512
  
  # Verify Redis live state
  redis_key = f"scie:meeting:{meeting_id}:video:participant:{evidence.track_id}:state"
  stored_state = await redis_client.get(redis_key)
  assert stored_state is not None
  
  # Verify MongoDB
  ev_doc = await mongo_db["visual_evidence"].find_one({"meeting_id": meeting_id})
  assert ev_doc is not None
  assert ev_doc["track_id"] == evidence.track_id
  
  # Clean up video and database records
  if os.path.exists(video_file_path):
    os.remove(video_file_path)
    
  await mongo_db["meetings"].delete_many({"meeting_id": meeting_id})
  await mongo_db["video_frames"].delete_many({"meeting_id": meeting_id})
  await mongo_db["face_tracks"].delete_many({"meeting_id": meeting_id})
  await mongo_db["face_embeddings"].delete_many({"meeting_id": meeting_id})
  await mongo_db["visual_evidence"].delete_many({"meeting_id": meeting_id})
  await redis_client.delete(redis_key)
  await redis_client.delete(f"scie:meeting:{meeting_id}:video:embeddings")
  await redis_client.delete(f"scie:meeting:{meeting_id}:video:schedule")

@pytest.mark.asyncio
async def test_video_workers_flow():
  """Test visual engine background queue-to-worker flow."""
  manager = VideoEngineWorkerManager.get_instance()
  manager.start()
  
  meeting_id = "pytest_vid_worker_meeting"
  
  scratch_dir = "C:/Users/Data/.gemini/antigravity-ide/brain/d6307dde-df5b-41e8-8fc8-2c1c794199ce/scratch"
  video_file_path = os.path.join(scratch_dir, "test_worker_video.webm")
  
  # Create minimal 5 frame video
  fourcc = cv2.VideoWriter_fourcc(*'VP80')
  out = cv2.VideoWriter(video_file_path, fourcc, 10.0, (640, 480))
  for _ in range(5):
    frame = np.ones((480, 640, 3), dtype=np.uint8) * 128
    frame[100:300, 200:400] = 200
    out.write(frame)
  out.release()
  
  chunk = VideoChunk(
      meeting_id=meeting_id,
      timestamp=int(time.time() * 1000),
      chunk_index=1,
      data=b"",
      file_path=video_file_path
  )
  
  # Clear Mongo
  mongo_db = get_mongo_db()
  await mongo_db["visual_evidence"].delete_many({"meeting_id": meeting_id})
  
  # Enqueue
  await manager.enqueue_chunk(chunk)
  
  # Wait for worker thread to process
  await asyncio.sleep(1.5)
  
  # Verify processed
  doc = await mongo_db["visual_evidence"].find_one({"meeting_id": meeting_id})
  assert doc is not None
  
  # Stop manager
  await manager.stop()
  
  # Cleanup
  if os.path.exists(video_file_path):
    os.remove(video_file_path)
  await mongo_db["visual_evidence"].delete_many({"meeting_id": meeting_id})
