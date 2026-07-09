import logging
from typing import List, Optional, Dict, Any

from engine.association.schemas import TimelineMatchEvidence, MeetingEvent
from engine.association.config import association_config
from engine.association.exceptions import TimelineMatcherError

logger = logging.getLogger("SCIE.association_engine.timeline_matcher")


class TimelineMatcher:
  """Correlates multi-modal timestamps (visual tracks, audio speaker activity,
  transcript turns, and DOM join/leave events) within a sliding time window.

  Example:
  00:05 Track_2 becomes visible
  00:05 Participant John joins
  00:06 Speaker_1 starts talking
  00:06 Transcript "I'm John"
  Occurring together significantly boosts association confidence.
  """

  def __init__(self):
    # In-memory circular buffer of recent meeting events across the meeting
    # Keyed by meeting_id -> List[Dict[str, Any]]
    self._recent_events: Dict[str, List[Dict[str, Any]]] = {}

  def record_event(
      self,
      meeting_id: str,
      event_type: str,
      timestamp: int,
      track_id: Optional[str] = None,
      speaker_id: Optional[str] = None,
      display_name: Optional[str] = None,
  ) -> None:
    """Records an event in the sliding timeline buffer for correlation."""
    if meeting_id not in self._recent_events:
      self._recent_events[meeting_id] = []

    # Prune events older than 60 seconds to keep buffer minimal
    cutoff = timestamp - 60000
    self._recent_events[meeting_id] = [
        e for e in self._recent_events[meeting_id] if e["timestamp"] >= cutoff
    ]

    self._recent_events[meeting_id].append({
        "event_type": event_type,
        "timestamp": timestamp,
        "track_id": track_id,
        "speaker_id": speaker_id,
        "display_name": display_name,
    })

  def match(
      self,
      meeting_id: str,
      current_timestamp: int,
      target_track_id: Optional[str] = None,
      target_speaker_id: Optional[str] = None,
      target_display_name: Optional[str] = None,
  ) -> TimelineMatchEvidence:
    """Checks whether recent events within TIMELINE_COOCCURRENCE_WINDOW_SEC co-occur."""
    try:
      if meeting_id not in self._recent_events:
        return TimelineMatchEvidence(
            score=0.0,
            confidence=0.0,
            reasons=["No recent multi-modal timeline events recorded for this meeting."]
        )

      window_ms = int(association_config.TIMELINE_COOCCURRENCE_WINDOW_SEC * 1000)
      window_start = current_timestamp - window_ms
      window_end = current_timestamp + window_ms

      co_occurring_events: List[str] = []
      matched_event_types: set = set()
      matched_ids: set = set()

      for event in self._recent_events[meeting_id]:
        e_time = event["timestamp"]
        if not (window_start <= e_time <= window_end):
          continue

        e_type = event["event_type"]
        e_track = event["track_id"]
        e_speaker = event["speaker_id"]
        e_name = event["display_name"]

        is_match = False
        if target_track_id and e_track == target_track_id:
          is_match = True
          matched_ids.add(f"track:{e_track}")
        if target_speaker_id and e_speaker == target_speaker_id:
          is_match = True
          matched_ids.add(f"speaker:{e_speaker}")
        if target_display_name and e_name and e_name.lower() == target_display_name.lower():
          is_match = True
          matched_ids.add(f"name:{e_name}")

        # If an event co-occurs right when our target joins or speaks or appears
        if is_match or (len(matched_ids) > 0 and e_time >= window_start):
          desc = f"[{e_type}] at {e_time}ms (track={e_track}, speaker={e_speaker}, name={e_name})"
          if desc not in co_occurring_events:
            co_occurring_events.append(desc)
            matched_event_types.add(e_type)

      if len(co_occurring_events) <= 1 and not (target_track_id and target_speaker_id):
        return TimelineMatchEvidence(
            score=0.20 if len(co_occurring_events) == 1 else 0.0,
            confidence=0.30 if len(co_occurring_events) == 1 else 0.0,
            reasons=[
                "Only isolated timeline events found; insufficient multi-modal co-occurrence."
                if len(co_occurring_events) == 1 else "No co-occurring timeline events within window."
            ],
            co_occurring_events=co_occurring_events
        )

      # Calculate score and confidence based on modality diversity
      # E.g., if a track appear/change co-occurs with speaker activity and join event
      modality_count = len(matched_event_types)
      score = min(1.0, 0.40 + (modality_count * 0.20) + (len(matched_ids) * 0.15))
      confidence = min(1.0, 0.50 + (modality_count * 0.15))

      reasons = [
          f"Strong temporal co-occurrence across {modality_count} event type(s) and {len(matched_ids)} identifier(s) "
          f"within ±{association_config.TIMELINE_COOCCURRENCE_WINDOW_SEC}s window."
      ]

      logger.debug(
          f"TimelineMatcher: meeting={meeting_id}, score={score:.2f}, "
          f"conf={confidence:.2f}, co_occurring={len(co_occurring_events)}"
      )
      return TimelineMatchEvidence(
          score=round(score, 4),
          confidence=round(confidence, 4),
          reasons=reasons,
          co_occurring_events=co_occurring_events
      )

    except Exception as exc:
      raise TimelineMatcherError(f"Failed to execute TimelineMatcher: {exc}") from exc
