import json
from .confidence import BaseEvidenceModule, EvidenceScore
from models import InterviewData
from llm import analyze_transcript_mentions

class TranscriptMentionsModule(BaseEvidenceModule):
    def run(self, data: InterviewData) -> list[EvidenceScore]:
        scores = []
        if not data.transcript or not data.external_metadata.candidate_name:
            return []
            
        transcript_text = "\n".join([f"{t.speaker_name} [{t.start_time} - {t.end_time}]: {t.text}" for t in data.transcript])
        candidate_name = data.external_metadata.candidate_name
        
        llm_response = analyze_transcript_mentions(transcript_text, candidate_name)
        
        try:
            parsed = json.loads(llm_response)
            mentions = parsed.get("mentions", [])
        except Exception as e:
            return []
            
        # Give confidence boost to participants addressed by the candidate name
        for participant in data.participant_information:
            disp_name = participant.display_name.lower()
            was_mentioned = False
            mention_reason = ""
            
            for m in mentions:
                addressed = m.get("addressed_participant", "").lower()
                if addressed and (addressed in disp_name or disp_name in addressed):
                    was_mentioned = True
                    mention_reason = m.get("reason", "Addressed by candidate's name.")
                    break
                    
            if was_mentioned:
                scores.append(EvidenceScore(
                    participant_id=participant.participant_id,
                    module=self.name,
                    score=0.9,
                    confidence=90.0,
                    reason=f"Interviewer repeatedly addressed participant as '{candidate_name}': {mention_reason}",
                    metadata={"mentioned": True}
                ))
            else:
                scores.append(EvidenceScore(
                    participant_id=participant.participant_id,
                    module=self.name,
                    score=0.0,
                    confidence=0.0,
                    reason="Participant was not addressed by candidate's name.",
                    metadata={"mentioned": False}
                ))
                
        return scores
