import logging
from typing import Dict, List

from engine.transcript.schemas import TranscriptChunk, SpeakerTimelineEntry, SpeakerStats
from engine.transcript.utils import compute_avg_wpm, count_words
from engine.transcript.exceptions import TimelineBuilderError

logger = logging.getLogger("SCIE.transcript_engine.timeline_builder")


class SpeakerTimelineBuilder:
  """Builds a chronological, typed conversation timeline from finalized chunks.

  Produces two complementary outputs:

  ``build_timeline``
      An ordered list of ``SpeakerTimelineEntry`` objects representing the
      full conversation flow — one entry per finalized utterance.  This is
      the human-readable "transcript scroll".

  ``build_speaker_stats``
      A per-speaker dict of ``SpeakerStats`` objects with cumulative metrics
      (utterance count, total speaking time, avg WPM, avg confidence).
      Consumed by the Behavior Engine and Evidence Fusion Engine.
  """

  def build_timeline(
      self,
      finalized_chunks: List[TranscriptChunk],
  ) -> List[SpeakerTimelineEntry]:
    """Orders all finalized utterances chronologically.

    Parameters
    ----------
    finalized_chunks:
        Unordered list of finalized ``TranscriptChunk`` objects.

    Returns
    -------
    List[SpeakerTimelineEntry]
        Chronologically sorted timeline; empty list if *finalized_chunks*
        is empty.

    Raises
    ------
    TimelineBuilderError
        If sorting or entry construction fails unexpectedly.
    """
    if not finalized_chunks:
      return []

    try:
      ordered = sorted(finalized_chunks, key=lambda c: c.start_time)
      timeline: List[SpeakerTimelineEntry] = []

      for chunk in ordered:
        duration = max(0.0, chunk.end_time - chunk.start_time)
        timeline.append(
            SpeakerTimelineEntry(
                speaker_id=chunk.speaker_id,
                start_time=chunk.start_time,
                end_time=chunk.end_time,
                duration=duration,
                transcript=chunk.text,
                confidence=chunk.confidence,
            )
        )

      logger.debug(
          f"TimelineBuilder: Built timeline with {len(timeline)} entries."
      )
      return timeline

    except Exception as exc:
      raise TimelineBuilderError(
          f"Failed to assemble speaker timeline: {exc}"
      ) from exc

  def build_speaker_stats(
      self,
      finalized_chunks: List[TranscriptChunk],
  ) -> Dict[str, SpeakerStats]:
    """Computes cumulative per-speaker metrics from finalized chunks.

    Parameters
    ----------
    finalized_chunks:
        All finalized chunks for a meeting (may span multiple speakers).

    Returns
    -------
    Dict[str, SpeakerStats]
        Mapping from ``speaker_id`` to their ``SpeakerStats``.
    """
    if not finalized_chunks:
      return {}

    try:
      # Accumulate raw counters per speaker
      accum: Dict[str, dict] = {}

      for chunk in finalized_chunks:
        sid = chunk.speaker_id
        if sid not in accum:
          accum[sid] = {
              "utterance_count":     0,
              "total_speaking_time": 0.0,
              "total_words":         0,
              "total_confidence":    0.0,
          }

        words     = count_words(chunk.text)
        duration  = max(0.0, chunk.end_time - chunk.start_time)

        accum[sid]["utterance_count"]     += 1
        accum[sid]["total_speaking_time"] += duration
        accum[sid]["total_words"]         += words
        accum[sid]["total_confidence"]    += chunk.confidence

      # Build typed SpeakerStats objects
      stats: Dict[str, SpeakerStats] = {}
      for sid, a in accum.items():
        count = a["utterance_count"]
        stats[sid] = SpeakerStats(
            speaker_id=sid,
            utterance_count=count,
            total_speaking_time=round(a["total_speaking_time"], 3),
            avg_wpm=compute_avg_wpm(
                a["total_words"], a["total_speaking_time"]
            ),
            avg_confidence=round(
                a["total_confidence"] / count if count > 0 else 0.0, 4
            ),
        )

      logger.info(
          f"TimelineBuilder: Computed stats for {len(stats)} speaker(s)."
      )
      return stats

    except Exception as exc:
      raise TimelineBuilderError(
          f"Failed to build speaker stats: {exc}"
      ) from exc
