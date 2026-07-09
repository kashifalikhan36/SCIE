"""
Transcript Loader for the Conversation Reasoning Engine.

Responsibilities:
- Load latest transcript turns from MongoDB (and Redis live state when available).
- Support incremental updates via ``since_turn_index`` to avoid re-reading full history.
- Convert raw timeline entries to structured ``ConversationTurn`` objects if turns are not explicitly materialized.
- Safely support concurrent multiple-meeting access.
"""
from typing import List, Optional
from database.mongodb import get_mongo_db
from database.redis import get_redis
from engine.transcript.schemas import ConversationTurn
from engine.transcript.constants import MONGO_TURNS_COL, MONGO_TIMELINES_COL
from engine.conversation.exceptions import TranscriptLoaderError
from engine.conversation.logger import logger


class ConversationTranscriptLoader:
  """Async loader responsible for fetching and structuring meeting transcript turns."""

  @classmethod
  async def load_turns(
      self, meeting_id: str, since_turn_index: int = 0
  ) -> List[ConversationTurn]:
    """Load ConversationTurns for the given meeting_id, optionally filtered by minimum turn_index.

    Returns turns sorted chronologically by turn_index / start_time.
    """
    try:
      db = get_mongo_db()
      if db is None:
        logger.warning(f"TranscriptLoader: MongoDB unavailable when fetching turns for {meeting_id}.")
        return []

      # 1. Query `conversation_turns` collection
      query = {"meeting_id": meeting_id}
      if since_turn_index > 0:
        query["turn_index"] = {"$gte": since_turn_index}

      cursor = db[MONGO_TURNS_COL].find(query).sort([("turn_index", 1), ("start_time", 1)])
      docs = await cursor.to_list(length=10000)

      if docs:
        turns = []
        for d in docs:
          # Remove MongoDB _id before Pydantic parsing
          d.pop("_id", None)
          try:
            turns.append(ConversationTurn.model_validate(d))
          except Exception as e:
            logger.debug(f"Skipping malformed ConversationTurn doc in {meeting_id}: {e}")
        if turns:
          logger.debug(f"Loaded {len(turns)} ConversationTurns for {meeting_id} from {MONGO_TURNS_COL}")
          return turns

      # 2. Fallback: if no `conversation_turns` documents exist, query `speaker_timelines`
      timeline_doc = await db[MONGO_TIMELINES_COL].find_one({"meeting_id": meeting_id})
      if timeline_doc and "timeline" in timeline_doc:
        raw_entries = timeline_doc["timeline"]
        turns = []
        for idx, entry in enumerate(raw_entries):
          if idx < since_turn_index:
            continue
          if isinstance(entry, dict):
            spk = entry.get("speaker_id", f"speaker_{idx}")
            txt = entry.get("transcript", "")
            start = float(entry.get("start_time", 0.0))
            end = float(entry.get("end_time", 0.0))
            dur = float(entry.get("duration", max(0.0, end - start)))
            conf = float(entry.get("confidence", 0.8))
          else:
            spk = getattr(entry, "speaker_id", f"speaker_{idx}")
            txt = getattr(entry, "transcript", "")
            start = float(getattr(entry, "start_time", 0.0))
            end = float(getattr(entry, "end_time", 0.0))
            dur = float(getattr(entry, "duration", max(0.0, end - start)))
            conf = float(getattr(entry, "confidence", 0.8))

          words = len(txt.split())
          turn = ConversationTurn(
              conversation_turn_id=f"turn_{idx}_{spk}",
              turn_index=idx,
              speaker_id=spk,
              utterances=[txt] if txt else [],
              start_time=start,
              end_time=end,
              duration=dur,
              word_count=words,
              avg_confidence=conf,
          )
          turns.append(turn)

        if turns:
          logger.debug(f"Converted {len(turns)} entries from {MONGO_TIMELINES_COL} into ConversationTurns for {meeting_id}")
          return turns

      return []

    except Exception as exc:
      logger.error(f"TranscriptLoader: Failed to load turns for meeting={meeting_id}: {exc}")
      raise TranscriptLoaderError(f"Failed to fetch transcript turns: {exc}") from exc
