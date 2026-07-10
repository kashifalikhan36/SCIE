from .confidence import BaseEvidenceModule, EvidenceScore
from models import InterviewData

class ScreenShareModule(BaseEvidenceModule):
    def run(self, data: InterviewData) -> list[EvidenceScore]:
        scores = []
        
        for participant in data.participant_information:
            events = participant.screen_share_events
            start_events = [e for e in events if e.event == "screen_share_start"]
            
            if not start_events:
                scores.append(EvidenceScore(
                    participant_id=participant.participant_id,
                    module=self.name,
                    score=0.3,
                    confidence=30.0,
                    reason="Did not share screen."
                ))
                continue
                
            shares = len(start_events)
            
            # Candidates are usually the ones asked to share screen for coding
            if shares == 1:
                conf = 85.0
                reason = "Shared screen once (typical for candidate coding)."
            else:
                conf = 90.0
                reason = f"Shared screen multiple times ({shares} times)."
                
            scores.append(EvidenceScore(
                participant_id=participant.participant_id,
                module=self.name,
                score=conf / 100.0,
                confidence=conf,
                reason=reason
            ))
            
        return scores
