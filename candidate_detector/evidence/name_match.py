from .confidence import BaseEvidenceModule, EvidenceScore
from models import InterviewData
from rapidfuzz import fuzz, process
import re

class NameMatchModule(BaseEvidenceModule):
    def run(self, data: InterviewData) -> list[EvidenceScore]:
        scores = []
        candidate_name = data.external_metadata.candidate_name
        
        if not candidate_name:
            return []
            
        candidate_lower = candidate_name.lower()
        cand_parts = candidate_lower.split()
        cand_initials = "".join([p[0] for p in cand_parts if p])
        
        for participant in data.participant_information:
            disp_name = participant.display_name.lower()
            
            # Exact Match
            if candidate_lower == disp_name:
                scores.append(EvidenceScore(
                    participant_id=participant.participant_id,
                    module=self.name,
                    score=1.0,
                    confidence=100.0,
                    reason=f"Exact display name match: {participant.display_name}",
                    metadata={"match_type": "exact", "target": candidate_name}
                ))
                continue
                
            # Initials match
            disp_initials = "".join([p[0] for p in disp_name.split() if p])
            if cand_initials and disp_initials == cand_initials and len(cand_initials) > 1:
                scores.append(EvidenceScore(
                    participant_id=participant.participant_id,
                    module=self.name,
                    score=0.7,
                    confidence=70.0,
                    reason=f"Display name initials match: {participant.display_name} -> {cand_initials}",
                    metadata={"match_type": "initials", "target": cand_initials}
                ))
                continue

            # Partial/Typo Match via RapidFuzz
            ratio = fuzz.token_sort_ratio(candidate_lower, disp_name)
            partial_ratio = fuzz.partial_ratio(candidate_lower, disp_name)
            
            best_ratio = max(ratio, partial_ratio)
            
            if best_ratio > 80:
                scores.append(EvidenceScore(
                    participant_id=participant.participant_id,
                    module=self.name,
                    score=best_ratio / 100.0,
                    confidence=best_ratio,
                    reason=f"Display name partially matches candidate ({best_ratio}% similarity)",
                    metadata={"match_type": "partial_fuzzy", "similarity": best_ratio}
                ))
            elif best_ratio > 50:
                scores.append(EvidenceScore(
                    participant_id=participant.participant_id,
                    module=self.name,
                    score=best_ratio / 100.0,
                    confidence=best_ratio,
                    reason=f"Weak partial name match ({best_ratio}% similarity)",
                    metadata={"match_type": "weak_fuzzy", "similarity": best_ratio}
                ))
            else:
                scores.append(EvidenceScore(
                    participant_id=participant.participant_id,
                    module=self.name,
                    score=0.0,
                    confidence=0.0,
                    reason="No significant name match found.",
                    metadata={"match_type": "none"}
                ))
                
        return scores
