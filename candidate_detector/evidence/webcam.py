from .confidence import BaseEvidenceModule, EvidenceScore
from models import InterviewData
from utils import parse_time

class WebcamModule(BaseEvidenceModule):
    def run(self, data: InterviewData) -> list[EvidenceScore]:
        scores = []
        
        for participant in data.participant_information:
            events = participant.webcam_events
            on_events = [e for e in events if e.event == "webcam_on"]
            off_events = [e for e in events if e.event == "webcam_off"]
            
            toggles = len(events)
            
            # Simple assumption: Interviewers might sometimes turn off camera, candidates usually keep it on.
            if toggles == 0:
                # No events might mean it was always off or always on. 
                # Check video streams from video object.
                has_stream = False
                if data.video:
                    has_stream = any(s.participant_id == participant.participant_id for s in data.video.webcam_streams)
                
                if has_stream:
                    scores.append(EvidenceScore(
                        participant_id=participant.participant_id,
                        module=self.name,
                        score=0.9,
                        confidence=90.0,
                        reason="Camera on consistently (no toggles detected, but stream exists)."
                    ))
                else:
                    scores.append(EvidenceScore(
                        participant_id=participant.participant_id,
                        module=self.name,
                        score=0.2,
                        confidence=20.0,
                        reason="Camera always off."
                    ))
            else:
                # Had some toggles.
                if len(on_events) > len(off_events):
                    conf = 80.0
                    reason = f"Camera mostly on ({toggles} toggles)."
                else:
                    conf = 50.0
                    reason = f"Camera toggled often or mostly off ({toggles} toggles)."
                    
                scores.append(EvidenceScore(
                    participant_id=participant.participant_id,
                    module=self.name,
                    score=conf / 100.0,
                    confidence=conf,
                    reason=reason
                ))
                
        return scores
