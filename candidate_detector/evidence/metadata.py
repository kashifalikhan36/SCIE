from .confidence import BaseEvidenceModule, EvidenceScore
from models import InterviewData

class MetadataModule(BaseEvidenceModule):
    def run(self, data: InterviewData) -> list[EvidenceScore]:
        scores = []
        
        # Look for any hints in calendar invite or other metadata that points to a specific participant ID or name.
        # This is a very generic module to grab extra context if any exists.
        invite = data.external_metadata.calendar_invite
        invite_str = str(invite).lower() if invite else ""
        
        for participant in data.participant_information:
            disp_name = participant.display_name.lower()
            
            if disp_name and disp_name in invite_str:
                scores.append(EvidenceScore(
                    participant_id=participant.participant_id,
                    module=self.name,
                    score=0.8,
                    confidence=80.0,
                    reason="Participant name mentioned in Calendar Invite.",
                    metadata={"in_invite": True}
                ))
            else:
                scores.append(EvidenceScore(
                    participant_id=participant.participant_id,
                    module=self.name,
                    score=0.2,
                    confidence=20.0,
                    reason="Participant name not explicitly found in Metadata/Invite.",
                    metadata={"in_invite": False}
                ))
                
        return scores
