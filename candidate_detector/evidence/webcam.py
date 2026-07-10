from .confidence import BaseEvidenceModule, EvidenceScore
from models import InterviewData

class WebcamModule(BaseEvidenceModule):
    def run(self, data: InterviewData) -> list[EvidenceScore]:
        scores = []
        
        for participant in data.participant_information:
            events = participant.webcam_events
            toggles = len(events)
            
            has_stream = False
            if data.video:
                has_stream = any(s.participant_id == participant.participant_id for s in data.video.webcam_streams)
                
            if toggles == 0 and has_stream:
                scores.append(EvidenceScore(
                    participant_id=participant.participant_id,
                    module=self.name,
                    score=0.9,
                    confidence=90.0,
                    reason="Camera remained continuously active with zero toggles.",
                    metadata={"toggles": 0, "active": True}
                ))
            elif toggles > 0:
                scores.append(EvidenceScore(
                    participant_id=participant.participant_id,
                    module=self.name,
                    score=0.6,
                    confidence=60.0,
                    reason=f"Camera was active but toggled {toggles} times.",
                    metadata={"toggles": toggles, "active": True}
                ))
            else:
                scores.append(EvidenceScore(
                    participant_id=participant.participant_id,
                    module=self.name,
                    score=0.0,
                    confidence=0.0,
                    reason="Camera was never active.",
                    metadata={"toggles": 0, "active": False}
                ))
                
        return scores
