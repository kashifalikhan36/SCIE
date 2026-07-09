import pytest
import asyncio
from typing import List
from unittest.mock import patch, AsyncMock

from engine.fusion import FusionPipeline
from engine.fusion.schemas import IncomingEvidence, FusionResult, DOMAIN_IDENTITY, DOMAIN_BEHAVIOR, DOMAIN_CONVERSATION
from engine.identity.schemas import IdentityEvidence
from engine.behavior.schemas import BehaviorEvidence
from engine.conversation.schemas import ConversationEvidence
from tests.test_scie_e2e_pipeline import mock_global_db_connections, FakeRedis, FakeMongo

pytestmark = pytest.mark.asyncio

class TestDeepPipelineLifecycle:
    """Simulates a full 45-minute meeting lifecycle and network chaos resilience."""

    async def test_45_minute_lifecycle_staleness(self):
        """
        Simulate a 45-minute meeting where evidence comes in batches at 0m, 15m, 30m, 45m.
        Validates that when behavior evidence stops coming, the confidence drops due to staleness.
        """
        meeting_id = "mtg_lifecycle_001"
        pid = "Candidate_Lifecycle"
        
        fusion_pipe = FusionPipeline()
        
        # t=0 min
        t0 = 1700000000000
        
        id_ev = IdentityEvidence(evidence_id=f"e1_{pid}_t0", timestamp=t0, meeting_id=meeting_id, participant_id=pid, overall_identity_score=0.95)
        beh_ev = BehaviorEvidence(
            evidence_id=f"e2_{pid}_t0", timestamp=t0, meeting_id=meeting_id, participant_id=pid, engagement_score=0.9,
            speaking_ratio=0.5, speech_duration=100.0, camera_ratio=1.0, screen_share_ratio=0.0, behavior_confidence=0.9
        )
        
        with patch("engine.fusion.utils.now_ms", return_value=t0):
            await fusion_pipe.process_evidence(IncomingEvidence.from_evidence(id_ev, DOMAIN_IDENTITY, participant_id=pid))
            res_t0 = await fusion_pipe.process_evidence(IncomingEvidence.from_evidence(beh_ev, DOMAIN_BEHAVIOR, participant_id=pid))
        
        # t=0, active behavior and identity
        assert res_t0.confidence > 0.10  # Should have some confidence
        
        # t=15 min (900 seconds later)
        # Behavior continues, conversation starts
        t15 = t0 + (15 * 60 * 1000)
        beh_ev_15 = BehaviorEvidence(
            evidence_id=f"e2_{pid}_t15", timestamp=t15, meeting_id=meeting_id, participant_id=pid, engagement_score=0.95,
            speaking_ratio=0.6, speech_duration=300.0, camera_ratio=1.0, screen_share_ratio=0.0, behavior_confidence=0.95
        )
        conv_ev_15 = ConversationEvidence(
            evidence_id=f"e3_{pid}_t15", timestamp=t15, meeting_id=meeting_id, participant_id=pid, score=0.88,
            speaker_id=pid, evidence_type="interviewer_probability", confidence=0.9, reason="test"
        )
        
        with patch("engine.fusion.utils.now_ms", return_value=t15):
            await fusion_pipe.process_evidence(IncomingEvidence.from_evidence(beh_ev_15, DOMAIN_BEHAVIOR, participant_id=pid))
            res_t15 = await fusion_pipe.process_evidence(IncomingEvidence.from_evidence(conv_ev_15, DOMAIN_CONVERSATION, participant_id=pid))
            
        assert res_t15.confidence > res_t0.confidence # Multi-modal score increased
        
        # t=45 min (45 minutes later)
        # Network outage: no new behavior or conversation evidence!
        t45 = t0 + (45 * 60 * 1000)
        
        # We process a dummy identity update just to trigger a fusion eval at t=45
        id_ev_45 = IdentityEvidence(evidence_id=f"e1_{pid}_t45", timestamp=t45, meeting_id=meeting_id, participant_id=pid, overall_identity_score=0.95)
        
        with patch("engine.fusion.utils.now_ms", return_value=t45):
            res_t45 = await fusion_pipe.process_evidence(IncomingEvidence.from_evidence(id_ev_45, DOMAIN_IDENTITY, participant_id=pid))
            
        # Behavior and Conversation are 30 mins old, should be STALE.
        print(f"t0 confidence: {res_t0.confidence}")
        print(f"t15 confidence: {res_t15.confidence}")
        print(f"t45 confidence: {res_t45.confidence}")
        print(f"t45 reasons: {res_t45.reasons}")
        print(f"t45 breakdown: {res_t45.evidence_breakdown}")
        assert res_t45.confidence < res_t15.confidence
        assert any("currently unavailable or off" in reason for reason in res_t45.reasons)

    async def test_network_chaos_out_of_order_resilience(self):
        """
        Simulate network delays where older evidence arrives AFTER newer evidence.
        Validates that EvidenceAggregator discards older evidence correctly.
        """
        meeting_id = "mtg_chaos_001"
        pid = "Candidate_Chaos"
        
        fusion_pipe = FusionPipeline()
        
        t0 = 1700000000000
        t_newer = t0 + 10000
        t_older = t0 + 5000
        
        # 1. Newer evidence arrives first
        beh_newer = BehaviorEvidence(
            evidence_id=f"e2_{pid}_newer", timestamp=t_newer, meeting_id=meeting_id, participant_id=pid, engagement_score=0.9,
            speaking_ratio=0.5, speech_duration=100.0, camera_ratio=1.0, screen_share_ratio=0.0, behavior_confidence=0.9
        )
        
        with patch("engine.fusion.utils.now_ms", return_value=t_newer):
            res_newer = await fusion_pipe.process_evidence(IncomingEvidence.from_evidence(beh_newer, DOMAIN_BEHAVIOR, participant_id=pid))
        
        # 2. Older evidence arrives LATE due to network lag
        beh_older = BehaviorEvidence(
            evidence_id=f"e2_{pid}_older", timestamp=t_older, meeting_id=meeting_id, participant_id=pid, engagement_score=0.1,
            speaking_ratio=0.1, speech_duration=10.0, camera_ratio=1.0, screen_share_ratio=0.0, behavior_confidence=0.9
        )
        
        with patch("engine.fusion.utils.now_ms", return_value=t_newer + 1000):
            res_after_lag = await fusion_pipe.process_evidence(IncomingEvidence.from_evidence(beh_older, DOMAIN_BEHAVIOR, participant_id=pid))
            
        # The engine should have IGNORED the older evidence because the slot already has a newer timestamp
        assert res_after_lag.evidence_breakdown[DOMAIN_BEHAVIOR] == 0.9 # Should stay at 0.9, not drop to 0.1
