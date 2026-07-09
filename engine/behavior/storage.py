from typing import Any, Dict, List, Optional
from database.mongodb import get_mongo_db
from engine.behavior.schemas import BehaviorEvidence, BehaviorTimelineEntry, BehaviorFeatures
from engine.behavior.constants import (
    MONGO_BEHAVIOR_EVENTS_COL,
    MONGO_BEHAVIOR_METRICS_COL,
    MONGO_PARTICIPANT_TIMELINES_COL,
    MONGO_ENGAGEMENT_HISTORY_COL,
    MONGO_MEETING_STATISTICS_COL,
)
from engine.behavior.utils import now_ms
from engine.behavior.exceptions import BehaviorStorageError
from engine.behavior.logger import logger, measure_latency


class BehaviorStorageManager:
  """
  Handles all MongoDB historical persistence for the Behavior Engine.

  Collections:
  - ``behavior_events``: Raw observation events and significant behavioral triggers.
  - ``behavior_metrics``: Periodic snapshots of complete behavioral evidence & domain metrics.
  - ``participant_timelines``: Append-only chronological timeline milestone entries.
  - ``engagement_history``: Historical trajectory of engagement scores and categorical levels.
  - ``meeting_statistics``: Meeting-level aggregate behavior statistics.

  All writes are timestamped. History is never overwritten.
  """

  @measure_latency("storage.save_event")
  async def save_event(
      self,
      meeting_id: str,
      participant_id: str,
      event_type: str,
      payload: Dict[str, Any],
      timestamp: Optional[int] = None
  ) -> None:
    """Append a raw behavior observation event or milestone trigger to ``behavior_events``."""
    db = get_mongo_db()
    if db is None:
      return
    try:
      doc = {
          "meeting_id": meeting_id,
          "participant_id": participant_id,
          "event_type": event_type,
          "payload": payload,
          "timestamp": timestamp or now_ms()
      }
      await db[MONGO_BEHAVIOR_EVENTS_COL].insert_one(doc)
      logger.debug(f"Storage: Inserted behavior_event {event_type} for {participant_id}")
    except Exception as exc:
      logger.error(f"Storage: Error inserting behavior_event: {exc}")

  @measure_latency("storage.save_metrics_snapshot")
  async def save_metrics_snapshot(self, evidence: BehaviorEvidence) -> None:
    """Append a complete behavioral evidence metrics snapshot to ``behavior_metrics``."""
    db = get_mongo_db()
    if db is None:
      return
    try:
      doc = evidence.model_dump()
      await db[MONGO_BEHAVIOR_METRICS_COL].insert_one(doc)
      logger.debug(f"Storage: Inserted behavior_metrics snapshot {evidence.evidence_id}")
    except Exception as exc:
      logger.error(f"Storage: Error inserting behavior_metrics snapshot: {exc}")

  @measure_latency("storage.save_timeline_entry")
  async def save_timeline_entry(self, entry: BehaviorTimelineEntry) -> None:
    """Append a milestone entry to ``participant_timelines``."""
    db = get_mongo_db()
    if db is None:
      return
    try:
      doc = entry.model_dump()
      await db[MONGO_PARTICIPANT_TIMELINES_COL].insert_one(doc)
      logger.debug(f"Storage: Inserted participant_timeline entry {entry.entry_id}")
    except Exception as exc:
      logger.error(f"Storage: Error inserting participant_timeline entry: {exc}")

  @measure_latency("storage.save_engagement_history")
  async def save_engagement_history(
      self,
      meeting_id: str,
      participant_id: str,
      engagement_score: float,
      engagement_level: str,
      component_scores: Dict[str, float],
      timestamp: Optional[int] = None
  ) -> None:
    """Append an engagement snapshot to ``engagement_history``."""
    db = get_mongo_db()
    if db is None:
      return
    try:
      doc = {
          "meeting_id": meeting_id,
          "participant_id": participant_id,
          "engagement_score": engagement_score,
          "engagement_level": engagement_level,
          "component_scores": component_scores,
          "timestamp": timestamp or now_ms()
      }
      await db[MONGO_ENGAGEMENT_HISTORY_COL].insert_one(doc)
      logger.debug(f"Storage: Inserted engagement_history ({engagement_level}) for {participant_id}")
    except Exception as exc:
      logger.error(f"Storage: Error inserting engagement_history: {exc}")

  @measure_latency("storage.save_meeting_statistics")
  async def save_meeting_statistics(
      self,
      meeting_id: str,
      total_participants: int,
      active_speakers: int,
      screen_shares_count: int,
      average_engagement: float,
      timestamp: Optional[int] = None
  ) -> None:
    """Append meeting-level aggregate behavior summaries to ``meeting_statistics``."""
    db = get_mongo_db()
    if db is None:
      return
    try:
      doc = {
          "meeting_id": meeting_id,
          "total_participants": total_participants,
          "active_speakers": active_speakers,
          "screen_shares_count": screen_shares_count,
          "average_engagement": average_engagement,
          "timestamp": timestamp or now_ms()
      }
      await db[MONGO_MEETING_STATISTICS_COL].insert_one(doc)
      logger.debug(f"Storage: Inserted meeting_statistics for {meeting_id}")
    except Exception as exc:
      logger.error(f"Storage: Error inserting meeting_statistics: {exc}")
