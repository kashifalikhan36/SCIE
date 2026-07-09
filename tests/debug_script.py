import asyncio
from unittest.mock import patch
from engine.fusion import FusionPipeline, IncomingEvidence
from engine.fusion.constants import DOMAIN_IDENTITY, DOMAIN_BEHAVIOR, DOMAIN_CONVERSATION
from engine.identity.schemas import IdentityEvidence
from engine.behavior.schemas import BehaviorEvidence
from engine.conversation.schemas import ConversationEvidence
from engine.fusion.utils import now_ms
from tests.test_scie_e2e_pipeline import FakeRedis, FakeMongo

async def run_sim():
    mock_redis = FakeRedis()
    mock_mongo = FakeMongo()
    
    with patch("database.redis.RedisClientManager.get_instance", return_value=mock_redis), \
         patch("database.mongodb.MongoClientManager.get_instance", return_value=mock_mongo):
        
        fusion_pipe = FusionPipeline()
        pid = "Candidate_Real"
        meeting_id = "mtg_1"
        now = now_ms()
        
        id_ev = IdentityEvidence(evidence_id=f"e1_{pid}", timestamp=now, meeting_id=meeting_id, participant_id=pid, overall_identity_score=0.95)
        beh_ev = BehaviorEvidence(
            evidence_id=f"e2_{pid}", timestamp=now, meeting_id=meeting_id, participant_id=pid, engagement_score=0.9,
            speaking_ratio=0.5, speech_duration=100.0, camera_ratio=1.0, screen_share_ratio=0.0, behavior_confidence=0.9
        )
        conv_ev = ConversationEvidence(
            evidence_id=f"e3_{pid}", timestamp=now, meeting_id=meeting_id, participant_id=pid, score=0.88,
            speaker_id=pid, evidence_type="interviewer_probability", confidence=0.9, reason="test"
        )
        
        from engine.fusion.state_manager import fusion_state_manager
        
        original_save = fusion_state_manager.save_participant_state
        async def mock_save(state):
            print(f"SAVING STATE for {state.participant_id}:")
            print(f"  Identity: {bool(state.identity_evidence)}")
            print(f"  Behavior: {bool(state.behavior_evidence)}")
            print(f"  Conversation: {bool(state.conversation_evidence)}")
            return await original_save(state)
            
        original_get = fusion_state_manager.get_participant_state
        async def mock_get(meeting_id, target_pid):
            print(f"GETTING STATE for meeting={meeting_id}, target_pid={target_pid}")
            st = await original_get(meeting_id, target_pid)
            print(f"  Returned state: {bool(st)}")
            return st
        
        with patch.object(fusion_state_manager, 'save_participant_state', new=mock_save), \
             patch.object(fusion_state_manager, 'get_participant_state', new=mock_get):
            await fusion_pipe.process_evidence(IncomingEvidence.from_evidence(id_ev, DOMAIN_IDENTITY, participant_id=pid))
            await fusion_pipe.process_evidence(IncomingEvidence.from_evidence(beh_ev, DOMAIN_BEHAVIOR, participant_id=pid))
            res = await fusion_pipe.process_evidence(IncomingEvidence.from_evidence(conv_ev, DOMAIN_CONVERSATION, participant_id=pid))
        print("After CONV, redis has:", mock_redis.store)
        
        print("Final Confidence:", res.confidence)
        print("Final Reasons:", res.reasons)

if __name__ == "__main__":
    asyncio.run(run_sim())
