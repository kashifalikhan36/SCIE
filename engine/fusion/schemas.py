"""
Pydantic V2 schemas for the Evidence Fusion Engine (`engine/fusion/`).

Defines standardized evidence wrappers, unified participant state, ranking scores,
explanations, confidence history items, and final fusion outputs.
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from engine.fusion.constants import EvidenceStatus, DOMAIN_IDENTITY, DOMAIN_VISUAL, DOMAIN_VOICE, DOMAIN_BEHAVIOR, DOMAIN_CONVERSATION, DOMAIN_TRANSCRIPT
from engine.fusion.utils import now_ms, generate_explanation_id, generate_fusion_event_id


# ──────────────────────────────────────────────────────────────────────────────
# Standardized Incoming Evidence Wrapper
# ──────────────────────────────────────────────────────────────────────────────

class IncomingEvidence(BaseModel):
  """Standardized wrapper encapsulating evidence emitted by any upstream engine.

  Enables plug-and-play ingestion without modifying upstream engine structures.
  If a signal is UNAVAILABLE or STALE, its status is explicitly tracked rather
  than converting it to a zero score.
  """
  evidence_id: str = Field(..., description="Unique string ID of the evidence item")
  meeting_id: str = Field(..., description="Unique meeting identifier")
  source_type: str = Field(..., description="Domain or engine identifier (e.g., identity, visual, voice)")
  participant_id: Optional[str] = Field(default=None, description="Resolved participant ID if known")
  track_id: Optional[str] = Field(default=None, description="Visual track ID if from Video Engine")
  speaker_id: Optional[str] = Field(default=None, description="Speaker ID if from Audio/Transcript Engine")
  score: float = Field(default=0.0, ge=0.0, le=1.0, description="Raw or normalized score [0, 1]")
  reliability: float = Field(default=1.0, ge=0.0, le=1.0, description="Signal reliability or confidence [0, 1]")
  timestamp: int = Field(default_factory=now_ms, description="Epoch milliseconds of generation")
  status: EvidenceStatus = Field(default=EvidenceStatus.AVAILABLE, description="Availability status")
  payload: Dict[str, Any] = Field(default_factory=dict, description="Raw serialized dictionary of upstream evidence")

  @classmethod
  def from_evidence(
      cls,
      evidence_obj: Any,
      source_type: str,
      participant_id: Optional[str] = None,
      track_id: Optional[str] = None,
      speaker_id: Optional[str] = None,
      score: Optional[float] = None,
      reliability: Optional[float] = None,
      status: EvidenceStatus = EvidenceStatus.AVAILABLE
  ) -> "IncomingEvidence":
    """Wrap an upstream Pydantic model or dict into an IncomingEvidence item."""
    if isinstance(evidence_obj, dict):
      payload = dict(evidence_obj)
    elif hasattr(evidence_obj, "model_dump"):
      payload = evidence_obj.model_dump()
    else:
      payload = {"raw": str(evidence_obj)}

    ev_id = str(payload.get("evidence_id") or payload.get("conversation_turn_id") or payload.get("entry_id") or generate_fusion_event_id())
    mtg_id = str(payload.get("meeting_id") or "unknown_meeting")
    ts = int(payload.get("timestamp") or payload.get("last_updated") or now_ms())

    # Auto-extract score if not provided
    if score is None:
      if source_type == DOMAIN_IDENTITY:
        score = float(payload.get("overall_identity_score", payload.get("score", 0.0)))
      elif source_type == DOMAIN_VISUAL:
        score = float(payload.get("face_similarity", payload.get("score", 0.0)))
      elif source_type == DOMAIN_VOICE:
        score = float(payload.get("speaker_similarity", payload.get("score", 0.0)))
      elif source_type == DOMAIN_BEHAVIOR:
        score = float(payload.get("engagement_score", payload.get("score", 0.0)))
      elif source_type == DOMAIN_CONVERSATION:
        score = float(payload.get("score", payload.get("conversation_confidence", 0.0)))
      else:
        score = float(payload.get("score", payload.get("confidence", 0.0)))

    # Auto-extract reliability if not provided
    if reliability is None:
      if source_type == DOMAIN_IDENTITY:
        reliability = float(payload.get("confidence", payload.get("reliability", 0.8)))
      elif source_type == DOMAIN_VISUAL:
        reliability = float(payload.get("recognition_confidence", payload.get("tracking_confidence", payload.get("confidence", payload.get("reliability", 0.8)))))
      elif source_type == DOMAIN_VOICE:
        reliability = float(payload.get("recognition_confidence", payload.get("speech_confidence", payload.get("confidence", payload.get("reliability", 0.8)))))
      elif source_type == DOMAIN_BEHAVIOR:
        reliability = float(payload.get("behavior_confidence", payload.get("confidence", payload.get("reliability", 0.8))))
      elif source_type == DOMAIN_CONVERSATION:
        reliability = float(payload.get("confidence", payload.get("reliability", 0.8)))
      else:
        reliability = float(payload.get("confidence", payload.get("reliability", 0.8)))

    # Auto-extract IDs if not explicitly passed
    pid = participant_id or str(payload.get("participant_id")) if payload.get("participant_id") else None
    tid = track_id or str(payload.get("track_id")) if payload.get("track_id") else None
    sid = speaker_id or str(payload.get("speaker_id")) if payload.get("speaker_id") else None

    return cls(
        evidence_id=ev_id,
        meeting_id=mtg_id,
        source_type=source_type,
        participant_id=pid,
        track_id=tid,
        speaker_id=sid,
        score=max(0.0, min(1.0, score)),
        reliability=max(0.0, min(1.0, reliability)),
        timestamp=ts,
        status=status,
        payload=payload
    )


# ──────────────────────────────────────────────────────────────────────────────
# Unified Participant State Schema
# ──────────────────────────────────────────────────────────────────────────────

class ParticipantState(BaseModel):
  """Unified state object representing one real meeting participant.

  Aggregates the latest evidence across identity, visual, voice, behavior,
  conversation, and future signals without mixing raw values or losing timestamps.
  """
  participant_id: str
  meeting_id: str
  track_id: Optional[str] = None
  speaker_id: Optional[str] = None
  display_name: Optional[str] = None
  identity_evidence: Optional[Dict[str, Any]] = None
  visual_evidence: Optional[Dict[str, Any]] = None
  voice_evidence: Optional[Dict[str, Any]] = None
  behavior_evidence: Optional[Dict[str, Any]] = None
  conversation_evidence: Optional[Dict[str, Any]] = None
  transcript_evidence: Optional[Dict[str, Any]] = None
  extra_evidence: Dict[str, Any] = Field(
      default_factory=dict,
      description="Extensible storage for future evidence domains (e.g., emotion, gaze)"
  )
  confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Current evolving confidence [0, 1]")
  reasons: List[str] = Field(default_factory=list, description="Top aggregated reasons explaining the current state")
  last_updated: int = Field(default_factory=now_ms, description="Epoch milliseconds of latest update")


# ──────────────────────────────────────────────────────────────────────────────
# Scoring & Ranking Schemas
# ──────────────────────────────────────────────────────────────────────────────

class ParticipantScore(BaseModel):
  """Evaluated and normalized score object for a participant."""
  participant_id: str
  final_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Normalized weighted score across active domains")
  confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Multi-signal confidence score")
  rank: int = Field(default=0, description="Sequential rank (1 = highest confidence/score)")
  reasons: List[str] = Field(default_factory=list, description="Justifications for the rank and score")
  evidence_breakdown: Dict[str, float] = Field(
      default_factory=dict,
      description="Map of domain name -> normalized domain score"
  )


class RankingResult(BaseModel):
  """Complete ranking list of all meeting participants."""
  meeting_id: str
  ranking: List[ParticipantScore] = Field(default_factory=list, description="Sorted list of participant scores")
  timestamp: int = Field(default_factory=now_ms)


# ──────────────────────────────────────────────────────────────────────────────
# Structured Explanation Schema
# ──────────────────────────────────────────────────────────────────────────────

class Explanation(BaseModel):
  """Rule-based structured explanation explaining a participant's score and ranking.

  Generated without GPT; can be displayed as structured cards or consumed downstream by GPT-5.5.
  """
  explanation_id: str = Field(default_factory=generate_explanation_id)
  meeting_id: str
  participant_id: str
  summary_points: List[str] = Field(default_factory=list, description="Top-level human readable bullet points")
  reasons_by_domain: Dict[str, List[str]] = Field(
      default_factory=dict,
      description="Specific justifications grouped by domain (visual, voice, etc.)"
  )
  key_strengths: List[str] = Field(default_factory=list, description="Dominant high-confidence positive signals")
  key_gaps: List[str] = Field(default_factory=list, description="Unavailable or low-confidence areas")
  timestamp: int = Field(default_factory=now_ms)


# ──────────────────────────────────────────────────────────────────────────────
# Confidence History & Audit Output Schemas
# ──────────────────────────────────────────────────────────────────────────────

class ConfidenceHistoryItem(BaseModel):
  """Historical snapshot of a participant's confidence score at a specific point in time."""
  participant_id: str
  meeting_id: str
  confidence: float = Field(..., ge=0.0, le=1.0)
  timestamp: int = Field(default_factory=now_ms)


class FusionResult(BaseModel):
  """Canonical final output object emitted by the Evidence Fusion Engine."""
  meeting_id: str
  participant_id: str
  rank: int = Field(..., ge=1, description="Sequential rank in the meeting")
  confidence: float = Field(..., ge=0.0, le=1.0, description="Final multi-signal confidence score")
  final_score: float = Field(..., ge=0.0, le=1.0, description="Overall weighted score")
  reasons: List[str] = Field(default_factory=list, description="Rule-based explanations")
  evidence_breakdown: Dict[str, float] = Field(
      default_factory=dict,
      description="Normalized scores per domain (identity, visual, voice, behavior, conversation)"
  )
  timestamp: int = Field(default_factory=now_ms)
