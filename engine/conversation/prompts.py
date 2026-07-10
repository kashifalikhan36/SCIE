"""
Reusable prompt templates and system instructions for the Conversation Reasoning Engine.

Every prompt focuses on exactly one semantic dimension and enforces strict JSON output matching:
{
  "evaluations": [
    {
      "speaker_id": "Speaker_1",
      "score": 0.9,
      "confidence": 0.85,
      "reason": "Clear explanation of why this speaker scored high/low on this dimension.",
      "supporting_quotes": ["Direct quote supporting this evaluation."]
    }
  ]
}
"""
from typing import Dict, Tuple
from engine.conversation.constants import (
    EVIDENCE_INTERVIEWER, EVIDENCE_CANDIDATE_BEHAVIOR, EVIDENCE_PROJECT_DISCUSSION,
    EVIDENCE_EXPERIENCE_DISCUSSION, EVIDENCE_TECHNICAL_ANSWER, EVIDENCE_QUESTION_RECEIVER,
    EVIDENCE_QUESTION_ASKER, EVIDENCE_OBSERVER, EVIDENCE_SELF_INTRODUCTION,
    EVIDENCE_CODING_DISCUSSION, EVIDENCE_MEETING_LEADER, EVIDENCE_INSUFFICIENT,
)

SYSTEM_INSTRUCTION_BASE = (
    "You are an expert conversation analyst for an interview observation system. "
    "Your responsibility is strictly to evaluate the provided conversation transcript chunk "
    "along a single specific behavioral or communication dimension. "
    "Do NOT make any final hiring decisions or identify who the ultimate candidate is. "
    "You must return ONLY valid, well-formed JSON conforming exactly to this structure:\n"
    "{\n"
    '  "evaluations": [\n'
    "    {\n"
    '      "speaker_id": "Speaker_X",\n'
    '      "score": 0.85,\n'
    '      "confidence": 0.90,\n'
    '      "reason": "Detailed justification based on transcript evidence.",\n'
    '      "supporting_quotes": ["Exact quote from transcript"],\n'
    '      "extracted_name": "Alex Smith"\n'
    "    }\n"
    "  ]\n"
    "}\n"
    "Rules:\n"
    "1. Score must be between 0.0 (does not exhibit trait at all) and 1.0 (strongly exhibits trait).\n"
    "2. Confidence must be between 0.0 (very uncertain / insufficient speech) and 1.0 (absolute certainty).\n"
    "3. Include all participating speakers present in the chunk.\n"
    "4. Return strictly valid JSON object without markdown formatting or introductory text.\n"
    "5. Use 'extracted_name' ONLY if the prompt asks you to extract a name (e.g. self introductions). Otherwise omit it or set it to null."
)


PROMPT_TEMPLATES: Dict[str, str] = {
    EVIDENCE_INTERVIEWER: (
        "Analyze the following conversation chunk and determine:\n"
        "**Who appears to be the interviewer?**\n\n"
        "Look for indicators such as asking structured interview questions, guiding the agenda, "
        "evaluating answers, or introducing the structure of the meeting.\n\n"
        "Conversation Transcript:\n{transcript}\n"
    ),
    EVIDENCE_CANDIDATE_BEHAVIOR: (
        "Analyze the following conversation chunk and determine:\n"
        "**Who appears to be answering interview questions?**\n\n"
        "Look for indicators such as providing comprehensive answers about background, "
        "skills, projects, or problem-solving approaches in response to prompts.\n\n"
        "Conversation Transcript:\n{transcript}\n"
    ),
    EVIDENCE_SELF_INTRODUCTION: (
        "Analyze the following conversation chunk and determine:\n"
        "**Who is introducing themselves?**\n\n"
        "Look for indicators such as stating one's name, background, career history, "
        "or current role during the start or transitions of the meeting.\n"
        "If a speaker explicitly states their name (e.g. 'Hi, I am Alex' or 'My name is Sarah'), "
        "extract that name exactly as spoken into the `extracted_name` field.\n\n"
        "Conversation Transcript:\n{transcript}\n"
    ),
    EVIDENCE_EXPERIENCE_DISCUSSION: (
        "Analyze the following conversation chunk and determine:\n"
        "**Who is discussing previous work experience?**\n\n"
        "Look for indicators such as describing past employers, job responsibilities, "
        "career timeline, or professional achievements.\n\n"
        "Conversation Transcript:\n{transcript}\n"
    ),
    EVIDENCE_PROJECT_DISCUSSION: (
        "Analyze the following conversation chunk and determine:\n"
        "**Who is describing specific engineering or architectural projects?**\n\n"
        "Look for indicators such as explaining system design, system components, "
        "project challenges, technical architecture, or delivery outcomes.\n\n"
        "Conversation Transcript:\n{transcript}\n"
    ),
    EVIDENCE_CODING_DISCUSSION: (
        "Analyze the following conversation chunk and determine:\n"
        "**Who appears to be solving or explaining coding problems?**\n\n"
        "Look for indicators such as discussing algorithms, data structures, syntax, "
        "debugging steps, time/space complexity, or writing code.\n\n"
        "Conversation Transcript:\n{transcript}\n"
    ),
    EVIDENCE_TECHNICAL_ANSWER: (
        "Analyze the following conversation chunk and determine:\n"
        "**Who is answering technical questions?**\n\n"
        "Look for indicators such as explaining technical concepts, trade-offs, "
        "protocols, language features, or technical best practices.\n\n"
        "Conversation Transcript:\n{transcript}\n"
    ),
    EVIDENCE_QUESTION_RECEIVER: (
        "Analyze the following conversation chunk and determine:\n"
        "**Who receives the majority of direct questions?**\n\n"
        "Evaluate which speakers are the primary target of inquiries from other participants.\n\n"
        "Conversation Transcript:\n{transcript}\n"
    ),
    EVIDENCE_QUESTION_ASKER: (
        "Analyze the following conversation chunk and determine:\n"
        "**Who asks the majority of questions?**\n\n"
        "Evaluate which speakers frequently interrogate, prompt, or inquire about topics.\n\n"
        "Conversation Transcript:\n{transcript}\n"
    ),
    EVIDENCE_OBSERVER: (
        "Analyze the following conversation chunk and determine:\n"
        "**Who appears to be observing without active participation?**\n\n"
        "Look for speakers who only give brief acknowledgments ('yes', 'ok', 'mm-hmm') "
        "or remain silent/passive during deep technical discussions.\n\n"
        "Conversation Transcript:\n{transcript}\n"
    ),
    EVIDENCE_MEETING_LEADER: (
        "Analyze the following conversation chunk and determine:\n"
        "**Who appears to be leading or facilitating the meeting?**\n\n"
        "Look for indicators such as controlling time, managing speaker turns, "
        "transitioning topics, and keeping the meeting on schedule.\n\n"
        "Conversation Transcript:\n{transcript}\n"
    ),
    EVIDENCE_INSUFFICIENT: (
        "Analyze the following conversation chunk and determine:\n"
        "**Which speakers have insufficient speech evidence to evaluate their role?**\n\n"
        "Identify speakers whose total speech or content is too minimal, fragmented, or generic "
        "to draw any reliable conclusions.\n\n"
        "Conversation Transcript:\n{transcript}\n"
    ),
}


class ConversationPrompts:
  """Utility class providing system instructions and formatted user prompts."""

  @classmethod
  def get_prompt(cls, prompt_type: str, formatted_transcript: str) -> Tuple[str, str]:
    """Return (system_instruction, user_prompt) for the specified prompt_type and chunk text."""
    template = PROMPT_TEMPLATES.get(prompt_type)
    if not template:
      raise ValueError(f"Unknown prompt_type: {prompt_type}")

    user_prompt = template.format(transcript=formatted_transcript)
    return SYSTEM_INSTRUCTION_BASE, user_prompt
