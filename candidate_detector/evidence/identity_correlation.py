from .confidence import BaseEvidenceModule, EvidenceScore
from models import InterviewData

class IdentityCorrelationModule(BaseEvidenceModule):
    def run(self, data: InterviewData) -> list[EvidenceScore]:
        scores = []
        candidate_email = data.external_metadata.candidate_email
        calendar_invite = data.external_metadata.calendar_invite
        
        has_any_identity = False

        for participant in data.participant_information:
            p_email = participant.email
            p_account = participant.account_id
            
            # Check if any participant has identity info
            if p_email or p_account:
                has_any_identity = True
                
            if p_email and candidate_email:
                if p_email.lower() == candidate_email.lower():
                    scores.append(EvidenceScore(
                        participant_id=participant.participant_id,
                        module=self.name,
                        score=1.0,
                        confidence=100.0,
                        reason="Participant email exactly matches candidate email.",
                        metadata={"type": "email_match"}
                    ))
                else:
                    scores.append(EvidenceScore(
                        participant_id=participant.participant_id,
                        module=self.name,
                        score=0.0,
                        confidence=0.0,
                        reason="Participant email does not match candidate email.",
                        metadata={"type": "email_mismatch"}
                    ))
            elif p_account and calendar_invite and "attendees" in calendar_invite:
                # Mock example of account mapping check
                attendee_accounts = [a.get("account_id") for a in calendar_invite.get("attendees", []) if a.get("account_id")]
                if p_account in attendee_accounts:
                    # Is this account the candidate's? Hard to know without specific calendar schema,
                    # but if we had candidate account ID, we would check it.
                    pass
        
        # If no participant identity information is available, skip module completely by returning empty list
        if not has_any_identity:
            # We skip module completely. The Fusion Engine handles empty results by not counting weight.
            return []
            
        return scores
