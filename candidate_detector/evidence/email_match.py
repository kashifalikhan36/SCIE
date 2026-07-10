from .confidence import BaseEvidenceModule, EvidenceScore
from models import InterviewData

class EmailMatchModule(BaseEvidenceModule):
    def run(self, data: InterviewData) -> list[EvidenceScore]:
        scores = []
        candidate_email = data.external_metadata.candidate_email
        
        if not candidate_email:
            return [] # No evidence if candidate email is missing
            
        candidate_email = candidate_email.lower()
        
        for participant in data.participant_information:
            # Our data.json doesn't guarantee participant email.
            # If we had it, we would check it here. Let's assume we can fetch it via attribute if it existed.
            # Using getattr to safely handle it since it's not strictly in our Pydantic model.
            part_email = getattr(participant, "email", None)
            
            if part_email and part_email.lower() == candidate_email:
                scores.append(EvidenceScore(
                    participant_id=participant.participant_id,
                    module=self.name,
                    score=1.0,
                    confidence=100.0,
                    reason="Exact email match."
                ))
            else:
                # If email is missing or doesn't match, return 0 or no evidence
                # We'll just return low score if not matched but email was present
                if part_email:
                    scores.append(EvidenceScore(
                        participant_id=participant.participant_id,
                        module=self.name,
                        score=0.0,
                        confidence=0.0,
                        reason="Email mismatch."
                    ))
                else:
                    # Missing data -> neutral / no evidence
                    scores.append(EvidenceScore(
                        participant_id=participant.participant_id,
                        module=self.name,
                        score=0.0,
                        confidence=0.0,
                        reason="Participant email missing, cannot compare."
                    ))
                    
        return scores
