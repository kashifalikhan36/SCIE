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

  async def match(
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

      # 3. Direct substring mention check
      if not is_self_intro and not is_addressed:
        if clean_target in cleaned_text and len(clean_target) >= 3:
          score = 0.60
          confidence = 0.50
          reasons.append(f"Direct mention of target name '{target_name}' in transcript.")
          
      # 4. Semantic Transcript Analysis using Azure OpenAI text-embedding-3-large
      if not is_self_intro and not is_addressed and score < 0.80:
        from engine.identity.embedding_client import EmbeddingClient
        from engine.identity.utils import cosine_similarity
        
        client = EmbeddingClient.get_instance()
        
        # We compare the transcript text against a synthetic reference string
        reference_text = f"Hello, my name is {target_name} and I am speaking."
        
        import asyncio
        t_emb, ref_emb = await asyncio.gather(
            client.embed(cleaned_text),
            client.embed(reference_text)
        )
        
        if t_emb is not None and ref_emb is not None:
            cos_sim = cosine_similarity(t_emb, ref_emb)
            # Map [-1, 1] to [0, 1]
            norm_sim = (cos_sim + 1.0) / 2.0
            if norm_sim > score and norm_sim > 0.65:
                score = norm_sim
                confidence = 0.70
                reasons.append(f"Semantic transcript analysis matched reference '{reference_text}' (sim={norm_sim:.2f})")

      if score == 0.0:
        return TranscriptMatchEvidence(
            score=0.0,
            confidence=0.0,
            reasons=[f"No conversational introduction, address pattern, or semantic match linking to '{target_name}'."]
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
