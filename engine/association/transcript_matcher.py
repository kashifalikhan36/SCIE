import re
import logging
from typing import Optional, List
from rapidfuzz import fuzz

from engine.association.schemas import TranscriptMatchEvidence
from engine.transcript.schemas import TranscriptEvidence
from engine.association.utils import clean_string
from engine.association.exceptions import TranscriptMatcherError

logger = logging.getLogger("SCIE.association_engine.transcript_matcher")


class TranscriptMatcher:
  """Scans transcript text for deterministic self-introductions ("I am John", "My name is John")
  or addressed cues ("Hi John", "Thanks John").

  Does NOT call GPT; uses deterministic regex and fuzzy matching patterns.
  """

  # Self-introduction patterns
  SELF_INTRO_PATTERNS = [
      r"\bi am ([a-z\s]{2,25})\b",
      r"\bi\'m ([a-z\s]{2,25})\b",
      r"\bmy name is ([a-z\s]{2,25})\b",
      r"\bi call myself ([a-z\s]{2,25})\b",
      r"\bthis is ([a-z\s]{2,25}) speaking\b"
  ]

  # Interlocutor addressing patterns
  ADDRESSED_PATTERNS = [
      r"\bhi ([a-z]{2,20})\b",
      r"\bhello ([a-z]{2,20})\b",
      r"\bthanks ([a-z]{2,20})\b",
      r"\bthank you ([a-z]{2,20})\b",
      r"\bwelcome ([a-z]{2,20})\b"
  ]

  STOP_WORDS = {
      "and", "or", "who", "where", "when", "i", "we", "you", "he", "she", "they",
      "will", "am", "is", "are", "to", "be", "have", "has", "had", "do", "does",
      "did", "can", "could", "would", "should", "may", "might", "must", "from",
      "in", "on", "at", "by", "for", "with", "about", "as", "into", "like",
      "through", "after", "over", "between", "out", "against", "during", "without",
      "before", "under", "around", "among", "speaking", "here", "today", "now"
  }

  def _clean_extracted_name(self, raw_name: str) -> str:
    """Strips sentence tails, stop words, and conjunctions from extracted name."""
    if not raw_name:
      return ""
    words = raw_name.strip().split()
    valid_words = []
    for w in words:
      if w.lower() in self.STOP_WORDS:
        break
      valid_words.append(w)
    return " ".join(valid_words).strip()

  def match(
      self,
      target_name: Optional[str],
      target_speaker_id: Optional[str],
      transcript_evidence: TranscriptEvidence,
  ) -> TranscriptMatchEvidence:
    """Evaluates whether transcript text associates target_name with target_speaker_id."""
    try:
      text = transcript_evidence.text.lower()
      cleaned_text = clean_string(text)
      if not cleaned_text or not target_name:
        return TranscriptMatchEvidence(
            score=0.0,
            confidence=0.0,
            reasons=["Missing target name or empty transcript."]
        )

      clean_target = clean_string(target_name)
      reasons: List[str] = []
      score = 0.0
      confidence = 0.0
      extracted_name: Optional[str] = None
      is_self_intro = False
      is_addressed = False

      # 1. Check for self-introduction patterns if the speaker matches or is being tested
      for pattern in self.SELF_INTRO_PATTERNS:
        match = re.search(pattern, cleaned_text)
        if match:
          candidate_name = self._clean_extracted_name(match.group(1))
          sim = fuzz.WRatio(clean_target, candidate_name) / 100.0
          if sim >= 0.70:
            score = max(score, sim)
            extracted_name = candidate_name
            is_self_intro = True
            if target_speaker_id and target_speaker_id == transcript_evidence.speaker_id:
              confidence = 0.95
              reasons.append(f"Speaker {transcript_evidence.speaker_id} introduced themselves as '{candidate_name}' (sim={sim:.2f})")
            else:
              confidence = 0.75
              reasons.append(f"Self-introduction pattern detected: '{candidate_name}' (sim={sim:.2f})")
            break

      # 2. Check for addressed patterns if not self-introduction
      if not is_self_intro:
        for pattern in self.ADDRESSED_PATTERNS:
          match = re.search(pattern, cleaned_text)
          if match:
            candidate_name = self._clean_extracted_name(match.group(1))
            sim = fuzz.WRatio(clean_target, candidate_name) / 100.0
            if sim >= 0.75:
              score = max(score, sim * 0.85)
              extracted_name = candidate_name
              is_addressed = True
              confidence = 0.65
              reasons.append(f"Addressed name pattern detected: '{candidate_name}' (sim={sim:.2f})")
              break

      # 3. Direct substring mention check if neither intro nor addressed pattern caught it
      if not is_self_intro and not is_addressed:
        if clean_target in cleaned_text and len(clean_target) >= 3:
          score = 0.60
          confidence = 0.50
          reasons.append(f"Direct mention of target name '{target_name}' in transcript.")
        else:
          return TranscriptMatchEvidence(
              score=0.0,
              confidence=0.0,
              reasons=[f"No conversational introduction or address pattern linking to '{target_name}'."]
          )

      logger.debug(
          f"TranscriptMatcher: speaker={transcript_evidence.speaker_id}, score={score:.2f}, "
          f"conf={confidence:.2f}, intro={is_self_intro}, addressed={is_addressed}"
      )
      return TranscriptMatchEvidence(
          score=round(score, 4),
          confidence=round(confidence, 4),
          reasons=reasons,
          extracted_name=extracted_name,
          is_self_intro=is_self_intro,
          is_addressed=is_addressed
      )

    except Exception as exc:
      raise TranscriptMatcherError(f"Failed to execute TranscriptMatcher: {exc}") from exc
