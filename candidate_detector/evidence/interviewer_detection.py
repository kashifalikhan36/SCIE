from .confidence import BaseEvidenceModule, EvidenceScore
from models import InterviewData
from rapidfuzz import fuzz

class InterviewerDetectionModule(BaseEvidenceModule):
    def run(self, data: InterviewData) -> list[EvidenceScore]:
        scores = []
        interviewers = data.external_metadata.interviewer_names
        
        if not interviewers:
            return []
            
        for participant in data.participant_information:
            disp_name = participant.display_name.lower()
            
            is_interviewer = False
            for inv in interviewers:
                if fuzz.ratio(disp_name, inv.lower()) > 85:
                    is_interviewer = True
                    break
                    
            if is_interviewer:
                scores.append(EvidenceScore(
                    participant_id=participant.participant_id,
                    module=self.name,
                    score=0.0,
                    confidence=0.0,
                    reason=f"Participant name matches interviewer list."
                ))
            else:
                scores.append(EvidenceScore(
                    participant_id=participant.participant_id,
                    module=self.name,
                    score=1.0,
                    confidence=100.0,
                    reason=f"Participant is not in interviewer list."
                ))
                
        return scores
