"""
Storage and Persistence Module for the SCIE Confidence Engine (`engine/confidence/storage.py`).

Manages live participant confidence state in Azure Cache for Redis (`participant:confidence`,
`participant:weights`, `participant:active_evidence`, `participant:latest_timestamp`) and
chronological audit trails inside 4 append-only MongoDB collections:
- `confidence_history`: Snapshot of every evaluation turn.
- `confidence_events`: Discrete state shift events (DECAY_STARTED, RECOVERY_STARTED, CAMERA_OFF).
- `participant_confidence`: Rolling participant checkpoint records.
- `meeting_confidence`: Aggregate meeting distribution records.

Provides complete in-memory offline fallback resilience when Redis/Mongo are disconnected.
"""
import json
from typing import Dict, List, Optional, Any
from engine.confidence.constants import (
    REDIS_KEY_PARTICIPANT_CONFIDENCE, REDIS_KEY_PARTICIPANT_WEIGHTS,
    REDIS_KEY_PARTICIPANT_ACTIVE_EVIDENCE, REDIS_KEY_PARTICIPANT_LATEST_TIMESTAMP,
    REDIS_KEY_MEETING_CONFIDENCE_SET,
    MONGO_COL_CONFIDENCE_HISTORY, MONGO_COL_CONFIDENCE_EVENTS,
    MONGO_COL_PARTICIPANT_CONFIDENCE, MONGO_COL_MEETING_CONFIDENCE
)
from engine.confidence.config import confidence_config
from engine.confidence.schemas import ParticipantConfidence, ConfidenceEvent
from engine.confidence.logger import logger, measure_latency

try:
  from backend.config import get_redis, get_mongo_db
except ImportError:
  try:
    from config import get_redis, get_mongo_db
  except ImportError:
    async def get_redis():
      return None
    async def get_mongo_db():
      return None


class ConfidenceStorageManager:
  """Asynchronously persists live state to Redis and append-only history to MongoDB."""

  def __init__(self):
    self._memory_state: Dict[str, ParticipantConfidence] = {}
    self._memory_events: List[ConfidenceEvent] = []

  @measure_latency
  async def save_participant_state(
      self,
      state: ParticipantConfidence,
      active_weights: Dict[str, float],
      events: Optional[List[ConfidenceEvent]] = None
  ) -> bool:
    """Save live state to Redis and append snapshots/events to MongoDB."""
    mem_key = f"{state.meeting_id}:{state.participant_id}"
    self._memory_state[mem_key] = state
    if events:
      self._memory_events.extend(events)

    # 1. Update Azure Cache for Redis (Live State)
    try:
      redis_client = await get_redis()
      if redis_client:
        ttl = confidence_config.REDIS_STATE_TTL_SEC
        k_conf = REDIS_KEY_PARTICIPANT_CONFIDENCE.format(meeting_id=state.meeting_id, participant_id=state.participant_id)
        k_w = REDIS_KEY_PARTICIPANT_WEIGHTS.format(meeting_id=state.meeting_id, participant_id=state.participant_id)
        k_ev = REDIS_KEY_PARTICIPANT_ACTIVE_EVIDENCE.format(meeting_id=state.meeting_id, participant_id=state.participant_id)
        k_ts = REDIS_KEY_PARTICIPANT_LATEST_TIMESTAMP.format(meeting_id=state.meeting_id, participant_id=state.participant_id)
        k_set = REDIS_KEY_MEETING_CONFIDENCE_SET.format(meeting_id=state.meeting_id)

        # Execute as pipeline when available
        if hasattr(redis_client, "pipeline"):
          pipe = redis_client.pipeline()
          pipe.set(k_conf, str(state.current_confidence), ex=ttl)
          pipe.set(k_w, json.dumps(active_weights), ex=ttl)
          pipe.set(k_ev, json.dumps(state.active_evidence), ex=ttl)
          pipe.set(k_ts, str(state.last_updated), ex=ttl)
          pipe.sadd(k_set, state.participant_id)
          pipe.expire(k_set, ttl)
          await pipe.execute()
        else:
          await redis_client.set(k_conf, str(state.current_confidence), ex=ttl)
          await redis_client.set(k_w, json.dumps(active_weights), ex=ttl)
          await redis_client.set(k_ev, json.dumps(state.active_evidence), ex=ttl)
          await redis_client.set(k_ts, str(state.last_updated), ex=ttl)
          await redis_client.sadd(k_set, state.participant_id)
          await redis_client.expire(k_set, ttl)
    except Exception as e:
      logger.warning(f"Redis state persistence failed ({e}); operating cleanly with memory state")

    # 2. Append history and events to MongoDB
    await self._archive_to_mongo(state, active_weights, events or [])
    return True

  @measure_latency
  async def get_participant_state(self, meeting_id: str, participant_id: str) -> Optional[ParticipantConfidence]:
    """Retrieve latest `ParticipantConfidence` from Redis cache or memory fallback."""
    mem_key = f"{meeting_id}:{participant_id}"
    cached_mem = self._memory_state.get(mem_key)

    try:
      redis_client = await get_redis()
      if not redis_client:
        return cached_mem

      k_conf = REDIS_KEY_PARTICIPANT_CONFIDENCE.format(meeting_id=meeting_id, participant_id=participant_id)
      val_conf = await redis_client.get(k_conf)
      if not val_conf:
        return cached_mem

      # Try to recover full state from memory or rebuild minimal from cache
      if cached_mem:
        # Sync current confidence with what is in Redis if memory drifted
        cached_mem.current_confidence = float(val_conf)
        return cached_mem

      k_ts = REDIS_KEY_PARTICIPANT_LATEST_TIMESTAMP.format(meeting_id=meeting_id, participant_id=participant_id)
      val_ts = await redis_client.get(k_ts)
      ts = float(val_ts) if val_ts else 0.0

      # Reconstruct minimal state if memory is empty
      return ParticipantConfidence(
          participant_id=participant_id,
          meeting_id=meeting_id,
          current_confidence=float(val_conf),
          previous_confidence=float(val_conf),
          highest_confidence=float(val_conf),
          lowest_confidence=float(val_conf),
          confidence_history=[],
          last_updated=ts,
          active_evidence={},
          missing_evidence=[]
      )
    except Exception as e:
      logger.warning(f"Redis get_participant_state failed ({e}); falling back to memory state")
      return cached_mem

  async def _archive_to_mongo(
      self,
      state: ParticipantConfidence,
      active_weights: Dict[str, float],
      events: List[ConfidenceEvent]
  ) -> None:
    """Append evaluation turn records into the 4 dedicated MongoDB collections."""
    try:
      db = await get_mongo_db()
      if not db:
        return

      col_hist = db[MONGO_COL_CONFIDENCE_HISTORY]
      col_ev = db[MONGO_COL_CONFIDENCE_EVENTS]
      col_part = db[MONGO_COL_PARTICIPANT_CONFIDENCE]
      col_meet = db[MONGO_COL_MEETING_CONFIDENCE]

      # 1. Append to `confidence_history`
      hist_doc = {
          "meeting_id": state.meeting_id,
          "participant_id": state.participant_id,
          "confidence": state.current_confidence,
          "previous_confidence": state.previous_confidence,
          "active_weights": dict(active_weights),
          "active_evidence": dict(state.active_evidence),
          "missing_evidence": list(state.missing_evidence),
          "timestamp": state.last_updated
      }
      await col_hist.insert_one(hist_doc)

      # 2. Append to `participant_confidence` (rolling summary check)
      part_doc = state.model_dump()
      part_doc["active_weights"] = dict(active_weights)
      await col_part.insert_one(part_doc)

      # 3. Append discrete events (`confidence_events`)
      if events:
        ev_docs = [ev.model_dump() for ev in events]
        await col_ev.insert_many(ev_docs)

      # 4. Append to `meeting_confidence`
      meet_doc = {
          "meeting_id": state.meeting_id,
          "participant_id": state.participant_id,
          "overall_confidence": state.current_confidence,
          "timestamp": state.last_updated
      }
      await col_meet.insert_one(meet_doc)

    except Exception as e:
      logger.warning(f"MongoDB append-only archiving failed ({e}); continuing cleanly with memory history")
