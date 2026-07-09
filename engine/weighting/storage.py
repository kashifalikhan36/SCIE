"""
Storage and Persistence Module for the Dynamic Weighting Engine.

Asynchronously persists latest participant weight profiles into Azure Cache for Redis
and archives chronological audit trails in MongoDB across 4 dedicated collections:
- weight_profiles
- weight_history
- strategy_changes
- quality_scores

Provides complete offline in-memory fallback resilience for unit/integration testing.
(`engine/weighting/storage.py`)
"""
from typing import Dict, List, Optional, Any
from engine.weighting.constants import (
    REDIS_KEY_LATEST_WEIGHTS, REDIS_KEY_MEETING_WEIGHT_PARTICIPANTS,
    MONGO_COL_WEIGHT_PROFILES, MONGO_COL_WEIGHT_HISTORY,
    MONGO_COL_STRATEGY_CHANGES, MONGO_COL_QUALITY_SCORES
)
from engine.weighting.config import weighting_config
from engine.weighting.schemas import DynamicWeightProfile, ParticipantWeightState, QualityScores
from engine.weighting.logger import logger, measure_latency

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


class WeightingStorageManager:
  """Manages Redis cache state and historical MongoDB archiving of weight profiles."""

  def __init__(self):
    self._memory_latest: Dict[str, ParticipantWeightState] = {}
    self._memory_participants: Dict[str, set] = {}
    self._memory_history: List[Dict[str, Any]] = []
    self._memory_strategies: List[Dict[str, Any]] = []
    self._memory_qualities: List[Dict[str, Any]] = []

  @measure_latency("weighting.save_profile")
  async def save_profile(
      self,
      profile: DynamicWeightProfile,
      quality: QualityScores,
      previous_strategy: Optional[str] = None
  ) -> ParticipantWeightState:
    """Persist latest weight profile to Redis and archive history snapshots in MongoDB."""
    state = ParticipantWeightState(
        participant_id=profile.participant_id,
        meeting_id=profile.meeting_id,
        weights=profile.as_dict(),
        strategy=profile.strategy_used.value,
        overall_quality=profile.overall_quality,
        reasons=profile.reasoning,
        last_updated=profile.timestamp
    )

    # 1. Update memory fallback
    cache_key = f"{profile.meeting_id}:{profile.participant_id}"
    self._memory_latest[cache_key] = state
    if profile.meeting_id not in self._memory_participants:
      self._memory_participants[profile.meeting_id] = set()
    self._memory_participants[profile.meeting_id].add(profile.participant_id)

    # 2. Persist to Redis
    redis_client = await get_redis()
    if redis_client:
      try:
        key = REDIS_KEY_LATEST_WEIGHTS.format(
            meeting_id=profile.meeting_id, participant_id=profile.participant_id
        )
        await redis_client.set(key, state.model_dump_json(), ex=weighting_config.REDIS_STATE_TTL_SEC)

        part_key = REDIS_KEY_MEETING_WEIGHT_PARTICIPANTS.format(meeting_id=profile.meeting_id)
        await redis_client.sadd(part_key, profile.participant_id)
        await redis_client.expire(part_key, weighting_config.REDIS_STATE_TTL_SEC)
      except Exception as e:
        logger.warning(f"Failed to persist weight state to Redis: {e}")

    # 3. Archive across 4 MongoDB collections
    await self._archive_mongo(profile, quality, previous_strategy)

    return state

  async def get_latest_state(self, meeting_id: str, participant_id: str) -> Optional[ParticipantWeightState]:
    """Retrieve latest participant weight state from Redis or memory fallback cache."""
    cache_key = f"{meeting_id}:{participant_id}"
    redis_client = await get_redis()
    if redis_client:
      try:
        key = REDIS_KEY_LATEST_WEIGHTS.format(meeting_id=meeting_id, participant_id=participant_id)
        raw = await redis_client.get(key)
        if raw:
          if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
          return ParticipantWeightState.model_validate_json(raw)
      except Exception as e:
        logger.warning(f"Failed to retrieve latest weight state from Redis: {e}")

    return self._memory_latest.get(cache_key)

  async def _archive_mongo(
      self,
      profile: DynamicWeightProfile,
      quality: QualityScores,
      previous_strategy: Optional[str]
  ):
    """Archive historical weight profiles, quality metrics, and strategy changes to MongoDB."""
    db = await get_mongo_db()
    
    # 1. weight_profiles & weight_history
    history_doc = profile.model_dump()
    self._memory_history.append(history_doc)

    # 2. strategy_changes if strategy transitioned
    strat_doc = None
    if previous_strategy and previous_strategy != profile.strategy_used.value:
      strat_doc = {
          "meeting_id": profile.meeting_id,
          "participant_id": profile.participant_id,
          "old_strategy": previous_strategy,
          "new_strategy": profile.strategy_used.value,
          "reasoning": profile.reasoning,
          "timestamp": profile.timestamp
      }
      self._memory_strategies.append(strat_doc)

    # 3. quality_scores
    qual_doc = {
        "meeting_id": profile.meeting_id,
        "participant_id": profile.participant_id,
        "scores": quality.model_dump(),
        "overall_quality": profile.overall_quality,
        "timestamp": profile.timestamp
    }
    self._memory_qualities.append(qual_doc)

    if db is not None:
      try:
        col_profiles = db[MONGO_COL_WEIGHT_PROFILES]
        col_history = db[MONGO_COL_WEIGHT_HISTORY]
        col_qual = db[MONGO_COL_QUALITY_SCORES]

        # Upsert latest profile in weight_profiles
        await col_profiles.update_one(
            {"meeting_id": profile.meeting_id, "participant_id": profile.participant_id},
            {"$set": history_doc},
            upsert=True
        )
        await col_history.insert_one(history_doc)
        await col_qual.insert_one(qual_doc)

        if strat_doc:
          col_strat = db[MONGO_COL_STRATEGY_CHANGES]
          await col_strat.insert_one(strat_doc)
      except Exception as e:
        logger.warning(f"Failed to archive weight metrics to MongoDB: {e}")
