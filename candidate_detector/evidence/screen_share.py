from .confidence import BaseEvidenceModule, EvidenceScore
from models import InterviewData

class ScreenShareModule(BaseEvidenceModule):
    def run(self, data: InterviewData) -> list[EvidenceScore]:
        scores = []
        
        for participant in data.participant_information:
            events = participant.screen_share_events
            start_events = [e for e in events if e.event == "screen_share_start"]
            
            shares = len(start_events)
            
            if shares > 0:
                scores.append(EvidenceScore(
                    participant_id=participant.participant_id,
                    module=self.name,
                    score=1.0,
                    confidence=100.0,
                    reason=f"Participant shared screen {shares} time(s).",
                    metadata={"shares": shares}
                ))
            else:
                scores.append(EvidenceScore(
                    participant_id=participant.participant_id,
                    module=self.name,
                    score=0.0,
                    confidence=0.0,
                    reason="Participant did not share screen.",
                    metadata={"shares": 0}
                ))
                
        return scores
