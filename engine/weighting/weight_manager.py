"""
Performance Calculation Cache & Weight Manager for the Dynamic Weighting Engine.

Avoids recalculating weights unnecessarily during real-time meetings. Recomputes only when:
- New evidence payloads arrive with updated timestamps
- Evidence quality scores change significantly (> 0.05)
- Participant hardware/state changes (camera_on, mic_on, screen_share toggles)
- Weighting strategy profile changes

(`engine/weighting/weight_manager.py`)
"""
from typing import Dict, Optional, Tuple
from engine.weighting.constants import WeightingStrategyType
from engine.weighting.config import weighting_config
from engine.weighting.schemas import DynamicWeightProfile, QualityScores, UpstreamParticipantState


class WeightManager:
  """Manages memory-level caching of computed dynamic weight profiles for high performance."""

  def __init__(self):
    self._profile_cache: Dict[str, DynamicWeightProfile] = {}
    self._last_state_cache: Dict[str, Tuple[bool, bool, bool, bool, bool]] = {}
    self._last_quality_cache: Dict[str, QualityScores] = {}
    self._last_strategy_cache: Dict[str, WeightingStrategyType] = {}

  def should_recompute(
      self,
      meeting_id: str,
      participant_id: str,
      p_state: UpstreamParticipantState,
      quality: QualityScores,
      strategy: WeightingStrategyType,
      force_recompute: bool = False
  ) -> bool:
    """Check if cached weight profile is stale and needs recalculation."""
    if force_recompute:
      return True

    cache_key = f"{meeting_id}:{participant_id}"
    if cache_key not in self._profile_cache:
      return True

    # 1. Check if strategy changed
    last_strat = self._last_strategy_cache.get(cache_key)
    if last_strat != strategy:
      return True

    # 2. Check if hardware / state toggled
    current_state_tuple = (
        p_state.camera_on,
        p_state.mic_on,
        p_state.screen_share,
        p_state.face_visible,
        p_state.voice_detected
    )
    last_state_tuple = self._last_state_cache.get(cache_key)
    if last_state_tuple != current_state_tuple:
      return True

    # 3. Check if overall quality changed above delta threshold
    last_q = self._last_quality_cache.get(cache_key)
    if not last_q:
      return True

    q_delta = abs(quality.get_overall_quality() - last_q.get_overall_quality())
    if q_delta >= weighting_config.QUALITY_CHANGE_RECOMPUTE_DELTA:
      return True

    return False

  def get_cached_profile(self, meeting_id: str, participant_id: str) -> Optional[DynamicWeightProfile]:
    """Retrieve cached profile if valid."""
    return self._profile_cache.get(f"{meeting_id}:{participant_id}")

  def update_cache(
      self,
      profile: DynamicWeightProfile,
      p_state: UpstreamParticipantState,
      quality: QualityScores
  ):
    """Store newly computed profile into local fast cache."""
    cache_key = f"{profile.meeting_id}:{profile.participant_id}"
    self._profile_cache[cache_key] = profile
    self._last_strategy_cache[cache_key] = profile.strategy_used
    self._last_quality_cache[cache_key] = quality
    self._last_state_cache[cache_key] = (
        p_state.camera_on,
        p_state.mic_on,
        p_state.screen_share,
        p_state.face_visible,
        p_state.voice_detected
    )

  def clear_cache(self, meeting_id: Optional[str] = None):
    """Clear memory cache globally or for a specific meeting."""
    if not meeting_id:
      self._profile_cache.clear()
      self._last_state_cache.clear()
      self._last_quality_cache.clear()
      self._last_strategy_cache.clear()
    else:
      keys = [k for k in self._profile_cache.keys() if k.startswith(f"{meeting_id}:")]
      for k in keys:
        self._profile_cache.pop(k, None)
        self._last_state_cache.pop(k, None)
        self._last_quality_cache.pop(k, None)
        self._last_strategy_cache.pop(k, None)
