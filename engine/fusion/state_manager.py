"""
Live State Manager (Azure Cache for Redis) for the Evidence Fusion Engine (`engine/fusion/`).

Manages live participant fusion profiles, active participant sets, real-time confidence history lists,
and latest meeting rankings with automatic TTL expiration (`REDIS_STATE_TTL_SEC`).
"""
from typing import List, Optional, Dict
import json
from database.redis import get_redis
from engine.fusion.config import fusion_config
from engine.fusion.constants import (
    REDIS_KEY_PARTICIPANT_STATE,
    REDIS_KEY_ACTIVE_PARTICIPANTS,
    REDIS_KEY_LATEST_RANKING,
    REDIS_KEY_CONFIDENCE_HISTORY
)
from engine.fusion.schemas import ParticipantState, RankingResult, ConfidenceHistoryItem
from engine.fusion.exceptions import FusionStateError
from engine.fusion.logger import logger, measure_latency


class FusionStateManager:
  """Async Redis manager for live Evidence Fusion Engine states with in-memory fallback."""

  def __init__(self) -> None:
    self._ttl = fusion_config.REDIS_STATE_TTL_SEC
    # In-memory fallback caches for when Redis is offline or mocked
    self._mem_states: Dict[str, str] = {}
    self._mem_active_pids: Dict[str, set] = {}
    self._mem_rankings: Dict[str, str] = {}
    self._mem_history: Dict[str, List[str]] = {}

  @measure_latency("save_participant_state")
  async def save_participant_state(self, state: ParticipantState) -> ParticipantState:
    """Save or update live ParticipantState in Redis (with memory fallback)."""
    try:
      redis = await get_redis()
      key = REDIS_KEY_PARTICIPANT_STATE.format(meeting_id=state.meeting_id, participant_id=state.participant_id)
      if redis is None:
        self._mem_states[key] = state.model_dump_json()
        if state.meeting_id not in self._mem_active_pids:
          self._mem_active_pids[state.meeting_id] = set()
        self._mem_active_pids[state.meeting_id].add(state.participant_id)
        return state

      await redis.set(key, state.model_dump_json(), ex=self._ttl)

      # Track participant ID in meeting set
      set_key = REDIS_KEY_ACTIVE_PARTICIPANTS.format(meeting_id=state.meeting_id)
      await redis.sadd(set_key, state.participant_id)
      await redis.expire(set_key, self._ttl)

      logger.debug(f"FusionStateManager: Saved live state for participant={state.participant_id} in meeting={state.meeting_id}.")
      return state
    except Exception as exc:
      logger.error(f"FusionStateManager: Failed to save state to Redis for {state.participant_id}: {exc}")
      raise FusionStateError(f"Failed to save state to Redis: {exc}") from exc

  @measure_latency("get_participant_state")
  async def get_participant_state(self, meeting_id: str, participant_id: str) -> Optional[ParticipantState]:
    """Retrieve live ParticipantState from Redis (or memory fallback)."""
    try:
      redis = await get_redis()
      key = REDIS_KEY_PARTICIPANT_STATE.format(meeting_id=meeting_id, participant_id=participant_id)
      if redis is None:
        raw = self._mem_states.get(key)
        return ParticipantState.model_validate_json(raw) if raw else None

      raw = await redis.get(key)
      if raw:
        return ParticipantState.model_validate_json(raw)
      return None
    except Exception as exc:
      logger.warning(f"FusionStateManager: Failed to get state for {participant_id}: {exc}")
      return None

  @measure_latency("get_active_participant_ids")
  async def get_active_participant_ids(self, meeting_id: str) -> List[str]:
    """Retrieve all active participant IDs tracked for a meeting from Redis (or memory fallback)."""
    try:
      redis = await get_redis()
      if redis is None:
        return list(self._mem_active_pids.get(meeting_id, set()))

      set_key = REDIS_KEY_ACTIVE_PARTICIPANTS.format(meeting_id=meeting_id)
      members = await redis.smembers(set_key)
      return [m.decode("utf-8") if isinstance(m, bytes) else str(m) for m in members]
    except Exception as exc:
      logger.warning(f"FusionStateManager: Failed to get active participants for meeting {meeting_id}: {exc}")
      return []

  @measure_latency("get_all_participant_states")
  async def get_all_participant_states(self, meeting_id: str) -> Dict[str, ParticipantState]:
    """Retrieve all active ParticipantState objects for a meeting."""
    pids = await self.get_active_participant_ids(meeting_id)
    states: Dict[str, ParticipantState] = {}
    for pid in pids:
      st = await self.get_participant_state(meeting_id, pid)
      if st:
        states[pid] = st
    return states

  @measure_latency("save_latest_ranking")
  async def save_latest_ranking(self, ranking: RankingResult) -> None:
    """Save latest meeting RankingResult in Redis (or memory fallback)."""
    try:
      redis = await get_redis()
      key = REDIS_KEY_LATEST_RANKING.format(meeting_id=ranking.meeting_id)
      if redis is None:
        self._mem_rankings[key] = ranking.model_dump_json()
        return
      await redis.set(key, ranking.model_dump_json(), ex=self._ttl)
      logger.debug(f"FusionStateManager: Saved latest ranking for meeting={ranking.meeting_id}.")
    except Exception as exc:
      logger.error(f"FusionStateManager: Failed to save latest ranking: {exc}")

  @measure_latency("get_latest_ranking")
  async def get_latest_ranking(self, meeting_id: str) -> Optional[RankingResult]:
    """Retrieve latest meeting RankingResult from Redis (or memory fallback)."""
    try:
      redis = await get_redis()
      key = REDIS_KEY_LATEST_RANKING.format(meeting_id=meeting_id)
      if redis is None:
        raw = self._mem_rankings.get(key)
        return RankingResult.model_validate_json(raw) if raw else None
      raw = await redis.get(key)
      if raw:
        return RankingResult.model_validate_json(raw)
      return None
    except Exception as exc:
      logger.warning(f"FusionStateManager: Failed to get ranking for meeting {meeting_id}: {exc}")
      return None

  @measure_latency("save_confidence_history")
  async def save_confidence_history(self, item: ConfidenceHistoryItem) -> None:
    """Append confidence snapshot to Redis history list (or memory fallback)."""
    try:
      redis = await get_redis()
      key = REDIS_KEY_CONFIDENCE_HISTORY.format(meeting_id=item.meeting_id, participant_id=item.participant_id)
      if redis is None:
        if key not in self._mem_history:
          self._mem_history[key] = []
        self._mem_history[key].append(item.model_dump_json())
        if len(self._mem_history[key]) > fusion_config.HISTORY_MAX_LENGTH:
          self._mem_history[key].pop(0)
        return
      await redis.rpush(key, item.model_dump_json())
      await redis.ltrim(key, -fusion_config.HISTORY_MAX_LENGTH, -1)
      await redis.expire(key, self._ttl)
    except Exception as exc:
      logger.warning(f"FusionStateManager: Failed to save confidence history to Redis: {exc}")

  @measure_latency("get_confidence_history")
  async def get_confidence_history(self, meeting_id: str, participant_id: str) -> List[ConfidenceHistoryItem]:
    """Retrieve confidence history list from Redis (or memory fallback)."""
    try:
      redis = await get_redis()
      key = REDIS_KEY_CONFIDENCE_HISTORY.format(meeting_id=meeting_id, participant_id=participant_id)
      if redis is None:
        raw_items = self._mem_history.get(key, [])
        return [ConfidenceHistoryItem.model_validate_json(raw) for raw in raw_items]
      raw_items = await redis.lrange(key, 0, -1)
      items: List[ConfidenceHistoryItem] = []
      for raw in raw_items:
        items.append(ConfidenceHistoryItem.model_validate_json(raw))
      return items
    except Exception as exc:
      logger.warning(f"FusionStateManager: Failed to get confidence history for {participant_id}: {exc}")
      return []


fusion_state_manager = FusionStateManager()
