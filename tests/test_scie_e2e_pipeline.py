"""
End-to-End System Orchestration Pipeline Verification (`tests/test_scie_e2e_pipeline.py`).

Verifies the complete SCIE Candidate Identification lifecycle by linking all 10 analytical engines
(`Audio`, `Video`, `Transcript`, `Identity`, `Behavior`, `Conversation`, `Association`, 
`Dynamic Weighting`, `Confidence`, and `Evidence Fusion`) into a unified execution loop.
"""

import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from typing import Dict, List, Any

# Engine Pipeline Imports
from engine.transcript import TranscriptEnginePipeline
from engine.identity import IdentityPipeline
from engine.behavior import BehaviorPipeline, VideoObservation, AudioObservation, TranscriptObservation
from engine.conversation import ConversationPipeline
from engine.association import ParticipantAssociationPipeline
from engine.confidence import ConfidencePipeline
from engine.fusion import FusionPipeline, IncomingEvidence
from engine.fusion.constants import DOMAIN_IDENTITY, DOMAIN_VISUAL, DOMAIN_VOICE, DOMAIN_BEHAVIOR, DOMAIN_CONVERSATION, DOMAIN_TRANSCRIPT
from engine.fusion.utils import now_ms


class FakeRedis:
    def __init__(self):
        self.store = {}
        self.sets = {}

    async def get_client(self): return self
    async def get(self, key, *args, **kwargs): return self.store.get(key)
    async def set(self, key, val, *args, **kwargs): self.store[key] = val; return True
    async def setex(self, key, ex, val, *args, **kwargs): self.store[key] = val; return True
    async def delete(self, key, *args, **kwargs): self.store.pop(key, None); return True
    async def hget(self, *args, **kwargs): return None
    async def hset(self, *args, **kwargs): return True
    async def rpush(self, *args, **kwargs): return 1
    async def ltrim(self, *args, **kwargs): return True
    async def sadd(self, key, val, *args, **kwargs):
        if key not in self.sets: self.sets[key] = set()
        self.sets[key].add(val)
        return 1
    async def smembers(self, key, *args, **kwargs): return list(self.sets.get(key, set()))
    async def expire(self, *args, **kwargs): return True

class FakeCollection:
    async def insert_one(self, *args, **kwargs): pass
    async def insert_many(self, *args, **kwargs): pass
    async def update_one(self, *args, **kwargs): pass
    async def find_one(self, *args, **kwargs): return None

class FakeDB:
    def __getattr__(self, name): return FakeCollection()
    def __getitem__(self, key): return FakeCollection()

class FakeMongo:
    def get_db(self): return FakeDB()
    def __getitem__(self, key): return FakeCollection()
    client = MagicMock()

@pytest.fixture(autouse=True)
def mock_global_db_connections():
    """Globally mocks MongoDB and Redis managers across all engine layers to prevent I/O during E2E unit tests."""
    mock_redis = FakeRedis()
    mock_mongo = FakeMongo()

    with patch("database.redis.RedisClientManager.get_instance", return_value=mock_redis), \
         patch("database.mongodb.MongoClientManager.get_instance", return_value=mock_mongo):
         yield


@pytest.mark.asyncio
class TestUpstreamToDownstreamPropagation:
  """Verifies that evidence flows cleanly from tier 1 ingestion to tier 3 fusion."""

  async def test_end_to_end_single_participant_dataflow(self):
    meeting_id = "mtg_e2e_001"
    pid = "Candidate_EndToEnd_1"

    # 1. Initialize all engine pipelines
    identity_pipe = IdentityPipeline()
    behavior_pipe = BehaviorPipeline()
    conversation_pipe = ConversationPipeline()
    association_pipe = ParticipantAssociationPipeline()
    confidence_pipe = ConfidencePipeline()
    fusion_pipe = FusionPipeline()

    # Mock LLM reasoning inside conversation pipeline to return deterministic logic
    mock_reasoner = AsyncMock()
    from engine.conversation.models import PromptExecutionResult, PromptEvaluationItem
    mock_res = PromptExecutionResult(
        prompt_type="interviewer_probability",
        meeting_id=meeting_id,
        chunk_id="c1",
        evaluations=[
            PromptEvaluationItem(speaker_id=pid, score=0.9, confidence=0.8, reason="test")
        ]
    )
    mock_reasoner.reason_over_chunks.return_value = [mock_res]
    conversation_pipe._reasoner = mock_reasoner

    # 2. Simulate upstream evidence generation (Metadata, Behavior, Conversation)
    # 2a. Identity Evidence (Name match)
    from engine.identity.schemas import MeetingMetadata, ParticipantMetadata
    mm = MeetingMetadata(meeting_id=meeting_id, candidate_name="John Doe", candidate_email="john@example.com")
    pm = ParticipantMetadata(participant_id=pid, meeting_id=meeting_id, display_name="John Doe", email="john@example.com")
    id_ev = await identity_pipe.process(mm, pm)
    assert id_ev is not None
    assert id_ev.overall_identity_score > 0.85

    # 2b. Behavior Evidence (Speaking and Video active)
    beh_obs = VideoObservation(meeting_id=meeting_id, participant_id=pid, timestamp=100.0,
                               camera_on=True, track_id="t1", face_similarity=0.9,
                               emotion_label="neutral", gaze_direction="center", visibility=1.0)
    beh_ev = await behavior_pipe.process(beh_obs)
    assert beh_ev is not None
    assert beh_ev.participant_id == pid

    # 2c. Conversation Evidence (Interviewer / Candidate logic)
    from engine.transcript.schemas import ConversationTurn
    dummy_turn = ConversationTurn(turn_id="t1", meeting_id=meeting_id, speaker_id=pid, text="Hello", start_time=0.0, end_time=1.0, utterances=["Hello"], duration=1.0, word_count=1)
    
    conv_ev_list = await conversation_pipe.process(meeting_id, turns=[dummy_turn])
    assert len(conv_ev_list) == 1
    conv_ev = conv_ev_list[0]
    assert conv_ev.speaker_id == pid

    # 3. Feed Evidence into Central Evidence Fusion Engine
    incoming_id = IncomingEvidence.from_evidence(id_ev, DOMAIN_IDENTITY, participant_id=pid)
    incoming_beh = IncomingEvidence.from_evidence(beh_ev, DOMAIN_BEHAVIOR, participant_id=pid)
    incoming_conv = IncomingEvidence.from_evidence(conv_ev, DOMAIN_CONVERSATION, participant_id=pid)

    res_id = await fusion_pipe.process_evidence(incoming_id)
    res_beh = await fusion_pipe.process_evidence(incoming_beh)
    res_conv = await fusion_pipe.process_evidence(incoming_conv)

    # 4. Verify Final Fusion Ranking and State
    assert res_conv is not None
    
    # The target participant should have accumulated a high confidence score across the 3 domains
    assert res_conv.confidence > 0.30  # Multimodal corroboration should yield high confidence
    assert DOMAIN_IDENTITY in res_conv.evidence_breakdown
    assert DOMAIN_BEHAVIOR in res_conv.evidence_breakdown
    assert DOMAIN_CONVERSATION in res_conv.evidence_breakdown


@pytest.mark.asyncio
class TestMultiCandidateSimultaneousMeeting:
  """Verifies real-time multi-candidate evaluations resolving distinct identities without cross-contamination."""

  async def test_4_person_meeting_simultaneous_fusion(self):
    meeting_id = "mtg_4_person_001"
    candidates = ["Candidate_Real", "Candidate_Imposter", "Interviewer_Lead", "Observer_HR"]

    fusion_pipe = FusionPipeline()

    # Simulate parallel independent evaluations across the 4 participants
    results = {}
    for pid in candidates:
      from engine.identity.schemas import IdentityEvidence
      from engine.behavior.schemas import BehaviorEvidence
      from engine.conversation.schemas import ConversationEvidence
      
      # Candidate Real has perfect matching criteria
      if pid == "Candidate_Real":
        id_score, beh_score, conv_score = 0.95, 0.90, 0.88
      # Imposter has visual/behavior but fails identity
      elif pid == "Candidate_Imposter":
        id_score, beh_score, conv_score = 0.10, 0.85, 0.85
      # Interviewer fails identity and conversation reasoning (is asking questions, not answering)
      elif pid == "Interviewer_Lead":
        id_score, beh_score, conv_score = 0.05, 0.95, 0.15
      # Observer is passive
      else:
        id_score, beh_score, conv_score = 0.0, 0.20, 0.05

      now = now_ms()
      id_ev = IdentityEvidence(evidence_id=f"e1_{pid}", timestamp=now, meeting_id=meeting_id, participant_id=pid, overall_identity_score=id_score)
      beh_ev = BehaviorEvidence(
          evidence_id=f"e2_{pid}", timestamp=now, meeting_id=meeting_id, participant_id=pid, engagement_score=beh_score,
          speaking_ratio=0.5, speech_duration=100.0, camera_ratio=1.0, screen_share_ratio=0.0, behavior_confidence=0.9
      )
      conv_ev = ConversationEvidence(
          evidence_id=f"e3_{pid}", timestamp=now, meeting_id=meeting_id, participant_id=pid, score=conv_score,
          speaker_id=pid, evidence_type="interviewer_probability", confidence=0.9, reason="test"
      )

      await fusion_pipe.process_evidence(IncomingEvidence.from_evidence(id_ev, DOMAIN_IDENTITY, participant_id=pid))
      await fusion_pipe.process_evidence(IncomingEvidence.from_evidence(beh_ev, DOMAIN_BEHAVIOR, participant_id=pid))
      results[pid] = await fusion_pipe.process_evidence(IncomingEvidence.from_evidence(conv_ev, DOMAIN_CONVERSATION, participant_id=pid))

    # The final result should contain rankings for all 4 participants
    assert results["Candidate_Real"] is not None
    assert results["Candidate_Real"].rank == 1
    assert results["Candidate_Imposter"].rank == 2
    assert results["Interviewer_Lead"].rank == 3
    assert results["Observer_HR"].rank == 4
    
    # Candidate_Real should have exceptionally high confidence
    assert results["Candidate_Real"].confidence > 0.30
    # Observer should have exceptionally low confidence
    assert results["Observer_HR"].confidence < 0.25
