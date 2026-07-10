from rapidfuzz import fuzz
from .confidence import BaseEvidenceModule, EvidenceScore
from models import InterviewData

class NameMatchModule(BaseEvidenceModule):
    def run(self, data: InterviewData) -> list[EvidenceScore]:
        scores = []
        candidate_name = data.external_metadata.candidate_name.lower()
        
        for participant in data.participant_information:
            disp_name = participant.display_name.lower()
            
            # Exact match
            if candidate_name == disp_name:
                scores.append(EvidenceScore(
                    participant_id=participant.participant_id,
                    module=self.name,
                    score=1.0,
                    confidence=100.0,
                    reason=f"Exact name match: {disp_name}"
                ))
                continue
                
            # Partial / Fuzzy match
            ratio = fuzz.ratio(candidate_name, disp_name)
            partial_ratio = fuzz.partial_ratio(candidate_name, disp_name)
            token_sort_ratio = fuzz.token_sort_ratio(candidate_name, disp_name)
            
            best_score = max(ratio, partial_ratio, token_sort_ratio)
            
            # Initials matching
            candidate_initials = "".join([part[0] for part in candidate_name.split() if part]).lower()
            disp_initials = "".join([part[0] for part in disp_name.split() if part]).lower()
            if candidate_initials == disp_initials and len(candidate_initials) > 1:
                best_score = max(best_score, 80.0)
                
            if best_score > 60:
                scores.append(EvidenceScore(
                    participant_id=participant.participant_id,
                    module=self.name,
                    score=best_score / 100.0,
                    confidence=best_score,
                    reason=f"Fuzzy name match (score: {best_score}): {disp_name}"
                ))
            else:
                scores.append(EvidenceScore(
                    participant_id=participant.participant_id,
                    module=self.name,
                    score=0.0,
                    confidence=0.0,
                    reason=f"No significant name match found."
                ))
                
        return scores
