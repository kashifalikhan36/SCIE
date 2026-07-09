from typing import List, Dict, Any, Optional
from engine.behavior.schemas import BehaviorTimelineEntry
from engine.behavior.config import behavior_config
from engine.behavior.utils import generate_timeline_id, format_timestamp_ms, now_ms
from engine.behavior.exceptions import TimelineBuilderError
from engine.behavior.logger import logger, measure_latency


class BehaviorTimelineBuilder:
  """
  Assembles and maintains chronological behavioral milestone timelines per participant.
  """

  def __init__(self):
    # participant_id -> list of BehaviorTimelineEntry
    self._timelines: Dict[str, List[BehaviorTimelineEntry]] = {}
    # participant_id -> meeting start time (or join time) for relative HH:MM:SS formatting
    self._start_times: Dict[str, int] = {}

  def get_timeline(self, participant_id: str) -> List[BehaviorTimelineEntry]:
    """Retrieve chronologically ordered timeline entries for a participant."""
    return self._timelines.get(participant_id, [])

  def clear_timeline(self, participant_id: str) -> None:
    """Clear timeline entries for a participant."""
    if participant_id in self._timelines:
      self._timelines[participant_id].clear()

  @measure_latency("timeline_builder.add_entry")
  def add_entry(
      self,
      meeting_id: str,
      participant_id: str,
      event_type: str,
      description: str,
      timestamp_ms: Optional[int] = None,
      metadata: Optional[Dict[str, Any]] = None
  ) -> BehaviorTimelineEntry:
    """Create and append a new chronological milestone entry for a participant."""
    try:
      ts = timestamp_ms if timestamp_ms is not None else now_ms()

      if participant_id not in self._start_times:
        self._start_times[participant_id] = ts
      if participant_id not in self._timelines:
        self._timelines[participant_id] = []

      # Calculate elapsed duration from participant start or meeting start for HH:MM:SS
      start_ts = self._start_times[participant_id]
      elapsed_ms = max(0, ts - start_ts)
      formatted = f"{format_timestamp_ms(elapsed_ms)} {description}"

      entry = BehaviorTimelineEntry(
          entry_id=generate_timeline_id(),
          meeting_id=meeting_id,
          participant_id=participant_id,
          timestamp_ms=ts,
          formatted_time=formatted,
          event_type=event_type,
          description=description,
          metadata=metadata or {}
      )

      # Insert maintaining chronological order by timestamp_ms
      timeline = self._timelines[participant_id]
      timeline.append(entry)
      timeline.sort(key=lambda x: x.timestamp_ms)

      # Trim if exceeding max length
      if len(timeline) > behavior_config.TIMELINE_MAX_LENGTH:
        self._timelines[participant_id] = timeline[-behavior_config.TIMELINE_MAX_LENGTH:]

      logger.debug(f"Added timeline entry for {participant_id}: {formatted}")
      return entry

    except Exception as e:
      logger.error(f"Error adding timeline entry for {participant_id}: {str(e)}")
      raise TimelineBuilderError(f"TimelineBuilder add_entry failed: {str(e)}") from e
