import pytest
import time
from database.redis import get_redis
from engine.audio.participant_state import ParticipantStateManager
from engine.audio.schemas import VoiceEvidence, ParticipantAudioState

@pytest.mark.asyncio
async def test_participant_state_manager():
  """Test that ParticipantStateManager correctly creates, retrieves, and merges participant audio metrics in Redis."""
  redis_client = await get_redis()
  assert redis_client is not None
  
  state_manager = ParticipantStateManager()
  meeting_id = "pytest_state_meeting"
  speaker_id = "speaker_alice"
  
  # Ensure clean Redis state
  redis_key = f"scie:meeting:{meeting_id}:participant:{speaker_id}:state"
  await redis_client.delete(redis_key)
  
  # 1. Create new participant state via update_state
  timestamp_1 = int(time.time() * 1000)
  evidence_1 = VoiceEvidence(
      meeting_id=meeting_id,
      speaker_id=speaker_id,
      voice_embedding=[0.3] * 192,
      speaker_similarity=0.80,
      transcript="First sentence",
      language="en",
      speech_start=0.0,
      speech_end=2.0,
      speech_duration=2.0,
      speech_confidence=0.95,
      recognition_confidence=1.0,
      timestamp=timestamp_1
  )
  
  state_1 = await state_manager.update_state(meeting_id, evidence_1)
  assert state_1 is not None
  assert state_1.speaker_id == speaker_id
  assert state_1.last_transcript == "First sentence"
  assert state_1.speech_duration == 2.0
  assert len(state_1.speech_segments) == 1
  assert state_1.speech_segments[0]["duration"] == 2.0
  
  # Verify saved in Redis
  stored_val = await redis_client.get(redis_key)
  assert stored_val is not None
  
  # 2. Merge/update with new evidence
  timestamp_2 = timestamp_1 + 5000
  evidence_2 = VoiceEvidence(
      meeting_id=meeting_id,
      speaker_id=speaker_id,
      voice_embedding=[0.3] * 192,
      speaker_similarity=0.90, # updated similarity
      transcript="Second sentence",
      language="en",
      speech_start=2.0,
      speech_end=5.0,
      speech_duration=3.0, # duration: 3.0s
      speech_confidence=0.90,
      recognition_confidence=1.0,
      timestamp=timestamp_2
  )
  
  state_2 = await state_manager.update_state(meeting_id, evidence_2)
  assert state_2 is not None
  # Speech duration should be cumulative (2.0 + 3.0 = 5.0)
  assert state_2.speech_duration == 5.0
  # Segments count should be 2
  assert len(state_2.speech_segments) == 2
  assert state_2.speech_segments[1]["duration"] == 3.0
  assert state_2.recognition_score == pytest.approx(0.85)
  assert state_2.last_transcript == "Second sentence"
  
  # 3. Retrieve state using get_state
  retrieved = await state_manager.get_state(meeting_id, speaker_id)
  assert retrieved is not None
  assert retrieved.speech_duration == 5.0
  assert retrieved.recognition_score == pytest.approx(0.85)

  # Clean up after test
  await redis_client.delete(redis_key)
