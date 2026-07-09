"""
High-frequency active evidence cache for the Evidence Fusion Engine (`engine/fusion/`).

Provides fast in-memory caching and deduplication checks to prevent unnecessary
recomputation and database queries during rapid streaming evidence arrival.
"""
from typing import Dict, Optional
import time
from engine.fusion.schemas import IncomingEvidence
from engine.fusion.config import fusion_config
from engine.fusion.logger import logger, measure_latency


class EvidenceCache:
  """High-speed local cache for active domain evidence items per participant."""

  def __init__(self) -> None:
    # Structure: { f"{meeting_id}:{participant_id}": { domain: IncomingEvidence } }
    self._participant_cache: Dict[str, Dict[str, IncomingEvidence]] = {}
    # Structure: { evidence_id: timestamp_received }
    self._processed_ids: Dict[str, float] = {}

  @measure_latency("cache_get_active")
  def get_active_evidence(self, meeting_id: str, participant_id: str) -> Dict[str, IncomingEvidence]:
    """Retrieve all cached active domain evidence items for a specific participant."""
    key = f"{meeting_id}:{participant_id}"
    return dict(self._participant_cache.get(key, {}))

  @measure_latency("cache_set_evidence")
  def set_evidence_item(self, meeting_id: str, participant_id: str, evidence: IncomingEvidence) -> None:
    """Store or update an active domain evidence item in the cache."""
    key = f"{meeting_id}:{participant_id}"
    if key not in self._participant_cache:
      self._participant_cache[key] = {}
    self._participant_cache[key][evidence.source_type] = evidence
    self._processed_ids[evidence.evidence_id] = time.time()

  def is_duplicate(self, evidence: IncomingEvidence) -> bool:
    """Check if an incoming evidence item has already been processed recently."""
    if evidence.evidence_id in self._processed_ids:
      logger.debug(f"EvidenceCache: Duplicate evidence_id={evidence.evidence_id} detected.")
      return True

    # Check for windowed deduplication across identical source_type and timestamp
    pid = evidence.participant_id or "unknown"
    cached_domain_map = self._participant_cache.get(f"{evidence.meeting_id}:{pid}", {})
    existing = cached_domain_map.get(evidence.source_type)
    if existing:
      # If exact same payload and very close timestamp
      time_diff = abs((evidence.timestamp - existing.timestamp) / 1000.0)
      if time_diff <= fusion_config.DEDUPLICATION_WINDOW_SEC and evidence.score == existing.score:
        logger.debug(
            f"EvidenceCache: Window duplicate detected for domain={evidence.source_type} "
            f"within {time_diff:.2f}s."
        )
        return True

    return False

  def clear_cache(self, meeting_id: str, participant_id: Optional[str] = None) -> None:
    """Clear cached evidence for a specific participant or an entire meeting."""
    if participant_id:
      key = f"{meeting_id}:{participant_id}"
      self._participant_cache.pop(key, None)
    else:
      keys_to_remove = [k for k in self._participant_cache if k.startswith(f"{meeting_id}:")]
      for k in keys_to_remove:
        self._participant_cache.pop(k, None)


# Singleton instance for process-wide caching
evidence_cache = EvidenceCache()
