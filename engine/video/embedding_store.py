import json
import logging
from typing import Optional, List, Dict
from database.redis import get_redis
from engine.video.schemas import DiarizedTrack
from engine.video.config import video_config
from engine.video.exceptions import EmbeddingStoreError

logger = logging.getLogger("SCIE.video_engine.embedding_store")

class EmbeddingStore:
  """Manages caching, retrieval, and update schedules for face embeddings in Redis."""

  @staticmethod
  def _get_embedding_key(meeting_id: str) -> str:
    return f"scie:meeting:{meeting_id}:video:embeddings"

  @staticmethod
  def _get_schedule_key(meeting_id: str) -> str:
    return f"scie:meeting:{meeting_id}:video:schedule"

  async def get_cached_embedding(self, meeting_id: str, track_id: str) -> Optional[List[float]]:
    """Retrieves cached embedding for a track ID from Redis."""
    redis_client = await get_redis()
    if not redis_client:
      return None
    try:
      key = self._get_embedding_key(meeting_id)
      data = await redis_client.hget(key, track_id)
      if data:
        return json.loads(data)
      return None
    except Exception as e:
      logger.error(f"Failed to fetch cached embedding for track {track_id}: {e}")
      return None

  async def store_embedding(self, meeting_id: str, track_id: str, embedding: List[float], frame_id: int):
    """Saves track embedding and updates its refresh frame schedule in Redis."""
    redis_client = await get_redis()
    if not redis_client:
      return
    try:
      emb_key = self._get_embedding_key(meeting_id)
      sched_key = self._get_schedule_key(meeting_id)
      
      # Store embedding hash
      await redis_client.hset(emb_key, track_id, json.dumps(embedding))
      # Store schedule info (last updated frame_id)
      await redis_client.hset(sched_key, track_id, str(frame_id))
      logger.debug(f"Cached embedding and updated schedule for track {track_id} at frame {frame_id}")
    except Exception as e:
      logger.error(f"Failed to cache embedding for track {track_id}: {e}")

  async def should_refresh_embedding(self, meeting_id: str, track_id: str, frame_id: int) -> bool:
    """Checks the scheduling configuration to determine if the track needs recognition refresh."""
    redis_client = await get_redis()
    if not redis_client:
      return True # Always compute if Redis is unavailable
      
    try:
      emb_key = self._get_embedding_key(meeting_id)
      sched_key = self._get_schedule_key(meeting_id)
      
      # 1. Check if embedding exists
      exists = await redis_client.hexists(emb_key, track_id)
      if not exists:
        logger.debug(f"Scheduling: Track {track_id} is new. Must extract embedding.")
        return True

      # 2. Check if refresh interval has passed
      last_frame_str = await redis_client.hget(sched_key, track_id)
      if not last_frame_str:
        return True

      last_frame = int(last_frame_str)
      frames_since_update = frame_id - last_frame
      
      if frames_since_update >= video_config.RECOGNITION_REFRESH_INTERVAL:
        logger.debug(f"Scheduling: Track {track_id} reached refresh interval ({frames_since_update} frames since last update).")
        return True

      return False
    except Exception as e:
      logger.error(f"Error checking embedding schedule: {e}")
      return True

  async def expire_tracks(self, meeting_id: str, active_track_ids: List[str]):
    """Removes historical embeddings and schedules for tracks that are no longer active."""
    redis_client = await get_redis()
    if not redis_client:
      return
    try:
      emb_key = self._get_embedding_key(meeting_id)
      sched_key = self._get_schedule_key(meeting_id)
      
      stored_emb_keys = await redis_client.hkeys(emb_key)
      if not stored_emb_keys:
        return

      # Decode track IDs from bytes to str
      stored_tracks = [k.decode('utf-8') if isinstance(k, bytes) else k for k in stored_emb_keys]
      
      for track_id in stored_tracks:
        if track_id not in active_track_ids:
          logger.info(f"Scheduling: Expiring track cache for inactive track {track_id}")
          await redis_client.hdel(emb_key, track_id)
          await redis_client.hdel(sched_key, track_id)
    except Exception as e:
      logger.error(f"Error during track expiration cleanup: {e}")
