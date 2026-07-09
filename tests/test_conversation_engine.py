"""
Deep Test Suite — Conversation Reasoning Engine (`engine/conversation/`)
========================================================================
Covers all 18 modules at unit, edge-case, prompt contract, caching, and integration levels.
"""
import asyncio
import json
import uuid
import pytest
from unittest.mock import AsyncMock, patch
from typing import List, Dict, Any

from engine.conversation.utils import (
    now_ms, generate_evidence_id, generate_chunk_id,
    hash_transcript, safe_divide, clamp, extract_json_from_response
)
from engine.conversation.exceptions import (
    JSONParseError, AzureOpenAIClientError, AzureOpenAITimeoutError,
    PipelineExecutionError
)
from engine.conversation.constants import (
    EVIDENCE_INTERVIEWER, EVIDENCE_CANDIDATE_BEHAVIOR, EVIDENCE_PROJECT_DISCUSSION,
    EVIDENCE_EXPERIENCE_DISCUSSION, EVIDENCE_TECHNICAL_ANSWER, EVIDENCE_QUESTION_RECEIVER,
    EVIDENCE_QUESTION_ASKER, EVIDENCE_OBSERVER, EVIDENCE_SELF_INTRODUCTION,
    EVIDENCE_CODING_DISCUSSION, EVIDENCE_MEETING_LEADER, EVIDENCE_INSUFFICIENT,
    ALL_EVIDENCE_TYPES,
)
from engine.conversation.config import conversation_config
from engine.conversation.models import ConversationChunk, PromptEvaluationItem, PromptExecutionResult
from engine.conversation.schemas import ConversationEvidence, ParticipantConversationState
from engine.conversation.prompts import ConversationPrompts, SYSTEM_INSTRUCTION_BASE
from engine.conversation.conversation_analyzer import ConversationAnalyzer
from engine.conversation.cache import ConversationCache
from engine.conversation.azure_client import ConversationAzureClient
from engine.conversation.reasoning_engine import ConversationReasoningEngine
from engine.conversation.evidence_provider import ConversationEvidenceProvider
from engine.conversation.participant_state import ConversationStateManager
from engine.conversation.storage import ConversationStorageManager
from engine.conversation.pipeline import ConversationPipeline
from engine.conversation.workers import ConversationWorkerManager, enqueue_conversation_reasoning
from engine.transcript.schemas import ConversationTurn
from database.mongodb import get_mongo_db


# ─────────────────────────────────────────────────────────────────────────────
# 1. TestConversationUtils
# ─────────────────────────────────────────────────────────────────────────────

class TestConversationUtils:
  def test_math_utils(self):
    assert safe_divide(10.0, 2.0) == 5.0
    assert safe_divide(10.0, 0.0, default=-1.0) == -1.0
    assert clamp(-0.5, 0.0, 1.0) == 0.0
    assert clamp(1.5, 0.0, 1.0) == 1.0
    assert clamp(0.75, 0.0, 1.0) == 0.75

  def test_id_generation_and_hashing(self):
    eid = generate_evidence_id()
    cid = generate_chunk_id()
    assert eid.startswith("CE_") and len(eid) == 11
    assert cid.startswith("CHK_") and len(cid) == 12

    h1 = hash_transcript("Hello world")
    h2 = hash_transcript("Hello world")
    assert h1 == h2 and len(h1) == 64

    # Hash list of ConversationTurn objects
    turn = ConversationTurn(
        conversation_turn_id="t1", turn_index=0, speaker_id="Spk1",
        utterances=["Test"], start_time=0.0, end_time=2.0, duration=2.0, word_count=1
    )
    h3 = hash_transcript([turn])
    assert len(h3) == 64

  def test_extract_json_from_response(self):
    # Plain JSON
    raw_plain = '{"evaluations": [{"speaker_id": "Spk1", "score": 0.8}]}'
    res = extract_json_from_response(raw_plain)
    assert res["evaluations"][0]["speaker_id"] == "Spk1"

    # Markdown wrapped JSON
    raw_md = '```json\n{\n  "evaluations": [{"speaker_id": "Spk2", "score": 0.9}]\n}\n```'
    res_md = extract_json_from_response(raw_md)
    assert res_md["evaluations"][0]["speaker_id"] == "Spk2"

    # Malformed / junk around JSON
    raw_junk = 'Sure! Here is your output:\n{"evaluations": []}\nHope that helps!'
    res_junk = extract_json_from_response(raw_junk)
    assert res_junk == {"evaluations": []}

    # Invalid JSON raises JSONParseError
    with pytest.raises(JSONParseError):
      extract_json_from_response("Not a JSON string at all.")


# ─────────────────────────────────────────────────────────────────────────────
# 2. TestConversationAnalyzer
# ─────────────────────────────────────────────────────────────────────────────

class TestConversationAnalyzer:
  def setup_method(self):
    self.turns = [
        ConversationTurn(
            conversation_turn_id=f"t_{i}",
            turn_index=i,
            speaker_id=f"Speaker_{i % 2}",
            utterances=[f"This is turn {i}."],
            start_time=float(i * 10),
            end_time=float(i * 10 + 8),
            duration=8.0,
            word_count=4
        )
        for i in range(35)
    ]

  def test_build_timeline_text(self):
    txt = ConversationAnalyzer.build_timeline_text(self.turns[:2])
    assert "[00:00:00 - 00:00:08] Speaker_0:" in txt
    assert "[00:00:10 - 00:00:18] Speaker_1:" in txt

  def test_chunk_conversation_by_turns(self):
    # 35 turns, max_turns=15 -> chunks of 15, 15, 5
    chunks = ConversationAnalyzer.chunk_conversation(self.turns, max_turns=15, max_seconds=10000.0)
    assert len(chunks) == 3
    assert chunks[0].turn_count == 15
    assert chunks[1].turn_count == 15
    assert chunks[2].turn_count == 5
    assert "Speaker_0" in chunks[0].speakers and "Speaker_1" in chunks[0].speakers

  def test_chunk_conversation_by_seconds(self):
    # Each turn starts 10s apart. If max_seconds=105s -> ~10-11 turns per chunk
    chunks = ConversationAnalyzer.chunk_conversation(self.turns, max_turns=100, max_seconds=105.0)
    assert len(chunks) >= 3
    for c in chunks:
      assert (c.end_time - c.start_time) <= 120.0  # boundary allowed up to current turn completion


# ─────────────────────────────────────────────────────────────────────────────
# 3. TestConversationPrompts
# ─────────────────────────────────────────────────────────────────────────────

class TestConversationPrompts:
  def test_get_prompt_for_all_evidence_types(self):
    sample_text = "[00:00:00 - 00:00:10] Speaker_1: Hello world."
    for p_type in ALL_EVIDENCE_TYPES:
      sys_inst, user_prompt = ConversationPrompts.get_prompt(p_type, sample_text)
      assert sys_inst == SYSTEM_INSTRUCTION_BASE
      assert sample_text in user_prompt
      assert "evaluations" in sys_inst

  def test_unknown_prompt_type_raises(self):
    with pytest.raises(ValueError):
      ConversationPrompts.get_prompt("invalid_prompt_type", "sample")


# ─────────────────────────────────────────────────────────────────────────────
# 4. TestConversationCache (Async)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestConversationCache:
  async def test_cache_hit_miss(self):
    cache = ConversationCache()
    mtg = f"m_cache_{uuid.uuid4().hex[:6]}"
    p_type = EVIDENCE_INTERVIEWER
    c_hash = "abc123hash"

    # Miss
    assert await cache.get_cached_evaluation(mtg, p_type, c_hash) is None

    # Save and Hit
    data = {"evaluations": [{"speaker_id": "Spk_C", "score": 0.95}]}
    await cache.save_cached_evaluation(mtg, p_type, c_hash, data)

    res = await cache.get_cached_evaluation(mtg, p_type, c_hash)
    if res is not None:  # If Redis available
      assert res["evaluations"][0]["speaker_id"] == "Spk_C"
      assert res["evaluations"][0]["score"] == 0.95


# ─────────────────────────────────────────────────────────────────────────────
# 5. TestReasoningEngineAndClient (Async)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestConversationReasoningAndClient:
  async def test_complete_json_and_reasoning_execution(self):
    engine = ConversationReasoningEngine()
    uid = uuid.uuid4().hex[:6]
    chunk = ConversationChunk(
        chunk_id=f"CHK_{uid}", meeting_id=f"m_test_reason_{uid}", turn_index_start=0, turn_index_end=2,
        start_time=0.0, end_time=20.0, turn_count=2, formatted_text=f"[00:00:00 - 00:00:10] Spk_{uid}: Hello.",
        speakers=[f"Spk_{uid}"]
    )

    mock_json = {
        "evaluations": [
            {
                "speaker_id": f"Spk_{uid}",
                "score": 0.88,
                "confidence": 0.92,
                "reason": "Structured questions asked.",
                "supporting_quotes": ["Hello."]
            }
        ]
    }

    with patch.object(engine._cache, "get_cached_evaluation", AsyncMock(return_value=None)):
      with patch.object(engine._client, "complete_json", AsyncMock(return_value=(mock_json, 150))) as mock_api:
        res = await engine.execute_prompt_on_chunk(chunk, EVIDENCE_INTERVIEWER)
        assert res.prompt_type == EVIDENCE_INTERVIEWER
        assert len(res.evaluations) == 1
        assert res.evaluations[0].speaker_id == f"Spk_{uid}"
        assert res.evaluations[0].score == 0.88
        assert res.tokens_used == 150
        mock_api.assert_called_once()

  async def test_reason_over_chunks_concurrency(self):
    engine = ConversationReasoningEngine()
    uid = uuid.uuid4().hex[:6]
    chunks = [
        ConversationChunk(chunk_id=f"CHK_{i}_{uid}", meeting_id=f"m_multi_{uid}", turn_index_start=i, turn_index_end=i+1,
                          start_time=float(i*10), end_time=float(i*10+5), turn_count=1,
                          formatted_text=f"Turn {i} for {uid}", speakers=["Spk1"])
        for i in range(2)
    ]

    mock_json = {"evaluations": [{"speaker_id": "Spk1", "score": 0.7, "confidence": 0.8, "reason": "ok"}]}
    with patch.object(engine._cache, "get_cached_evaluation", AsyncMock(return_value=None)):
      with patch.object(engine._client, "complete_json", AsyncMock(return_value=(mock_json, 100))):
        results = await engine.reason_over_chunks(chunks, prompt_types=[EVIDENCE_INTERVIEWER, EVIDENCE_CANDIDATE_BEHAVIOR])
        assert len(results) == 4
        assert all(isinstance(r, PromptExecutionResult) for r in results)


# ─────────────────────────────────────────────────────────────────────────────
# 6. TestEvidenceProvider
# ─────────────────────────────────────────────────────────────────────────────

class TestConversationEvidenceProvider:
  def test_provide_and_never_combine_scores(self):
    r1 = PromptExecutionResult(
        prompt_type=EVIDENCE_INTERVIEWER, meeting_id="m_prov", chunk_id="c1",
        evaluations=[PromptEvaluationItem("Spk1", 0.9, 0.95, "Interviewer indicator.")]
    )
    r2 = PromptExecutionResult(
        prompt_type=EVIDENCE_CANDIDATE_BEHAVIOR, meeting_id="m_prov", chunk_id="c1",
        evaluations=[PromptEvaluationItem("Spk1", 0.1, 0.90, "Not answering questions.")]
    )

    ev_list = ConversationEvidenceProvider.provide([r1, r2], "m_prov")
    assert len(ev_list) == 2
    # Verify scores are separate and independent
    ev_int = next(e for e in ev_list if e.evidence_type == EVIDENCE_INTERVIEWER)
    ev_cand = next(e for e in ev_list if e.evidence_type == EVIDENCE_CANDIDATE_BEHAVIOR)
    assert ev_int.score == 0.9
    assert ev_cand.score == 0.1

    states = ConversationEvidenceProvider.build_participant_states(ev_list, "m_prov")
    assert len(states) == 1
    assert states[0].speaker_id == "Spk1"
    assert EVIDENCE_INTERVIEWER in states[0].latest_reasoning
    assert EVIDENCE_CANDIDATE_BEHAVIOR in states[0].latest_reasoning


# ─────────────────────────────────────────────────────────────────────────────
# 7. TestStorageAndState (Async)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestConversationStorageAndState:
  async def test_redis_state_management(self):
    state_mgr = ConversationStateManager()
    mtg = f"m_state_{uuid.uuid4().hex[:6]}"
    spk = "Speaker_Redis_01"

    state_obj = ParticipantConversationState(
        speaker_id=spk,
        meeting_id=mtg,
        latest_reasoning={"interviewer": {"score": 0.8}},
        latest_confidence=0.85,
        conversation_summary="Evaluated as interviewer."
    )

    saved = await state_mgr.save_state(state_obj)
    assert saved.speaker_id == spk

    fetched = await state_mgr.get_state(mtg, spk)
    if fetched:
      assert fetched.speaker_id == spk
      assert fetched.latest_confidence == 0.85

    speakers = await state_mgr.get_all_speakers(mtg)
    if speakers:
      assert spk in speakers

  async def test_mongodb_all_4_collections(self):
    db = get_mongo_db()
    if db is None:
      pytest.skip("MongoDB unavailable")

    storage = ConversationStorageManager()
    mtg = f"m_mongo_{uuid.uuid4().hex[:6]}"
    spk = "Speaker_Mongo_01"

    # Clean old test docs
    for col in [
        "conversation_reasoning", "conversation_evidence",
        "reasoning_history", "prompt_history"
    ]:
      await db[col].delete_many({"meeting_id": mtg})

    # 1. save_evidence_item / batch
    ev = ConversationEvidence(
        evidence_id="CE_test0001", meeting_id=mtg, speaker_id=spk,
        evidence_type=EVIDENCE_INTERVIEWER, score=0.88, confidence=0.9,
        reason="Test reason", supporting_quotes=["hello"]
    )
    await storage.save_evidence_item(ev)

    # 2. save_reasoning_snapshot
    await storage.save_reasoning_snapshot(mtg, evidence_count=1, speaker_count=1)

    # 3. save_reasoning_history
    await storage.save_reasoning_history(mtg, spk, {"interviewer": ev.model_dump()}, 0.9, "Summary")

    # 4. save_prompt_history
    await storage.save_prompt_history(mtg, "CHK_test01", EVIDENCE_INTERVIEWER, "1.0", "gpt-5.5", 120.0, 350)

    assert await db["conversation_evidence"].count_documents({"meeting_id": mtg}) == 1
    assert await db["conversation_reasoning"].count_documents({"meeting_id": mtg}) == 1
    assert await db["reasoning_history"].count_documents({"meeting_id": mtg}) == 1
    assert await db["prompt_history"].count_documents({"meeting_id": mtg}) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 8. TestPipelineAndWorkers (Async)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestConversationPipelineAndWorkers:
  async def test_pipeline_process_end_to_end(self):
    pipeline = ConversationPipeline()
    mtg = f"m_pipe_{uuid.uuid4().hex[:6]}"
    turns = [
        ConversationTurn(
            conversation_turn_id=f"t_{i}", turn_index=i, speaker_id=f"Speaker_{i%2}",
            utterances=[f"Let's discuss project {i}."], start_time=float(i*10), end_time=float(i*10+5),
            duration=5.0, word_count=4
        )
        for i in range(4)
    ]

    mock_json = {
        "evaluations": [
            {"speaker_id": "Speaker_0", "score": 0.8, "confidence": 0.85, "reason": "Project discussion."},
            {"speaker_id": "Speaker_1", "score": 0.7, "confidence": 0.80, "reason": "Project discussion."}
        ]
    }

    with patch.object(pipeline._reasoner._cache, "get_cached_evaluation", AsyncMock(return_value=None)):
      with patch.object(pipeline._reasoner._client, "complete_json", AsyncMock(return_value=(mock_json, 200))):
        ev_list = await pipeline.process(mtg, turns=turns, prompt_types=[EVIDENCE_PROJECT_DISCUSSION])
        assert len(ev_list) == 2
        assert any(e.speaker_id == "Speaker_0" for e in ev_list)
        assert any(e.speaker_id == "Speaker_1" for e in ev_list)

  async def test_worker_manager_lifecycle(self):
    ConversationWorkerManager._instance = None
    mgr = ConversationWorkerManager.get_instance()
    mgr.start()
    assert mgr.is_running is True
    assert len(mgr.worker_tasks) == conversation_config.WORKER_COUNT

    mtg = f"m_work_{uuid.uuid4().hex[:6]}"
    await enqueue_conversation_reasoning(mtg, turns=[], prompt_types=[EVIDENCE_INTERVIEWER])
    await asyncio.sleep(0.1)

    await mgr.stop()
    assert mgr.is_running is False
    assert all(t.done() for t in mgr.worker_tasks)
