import json
from .confidence import BaseEvidenceModule, EvidenceScore
from models import InterviewData
from llm import analyze_transcript_roles

class ConversationRoleModule(BaseEvidenceModule):
    def run(self, data: InterviewData) -> list[EvidenceScore]:
        scores = []
        if not data.transcript:
            return []
            
        transcript_text = "\n".join([f"{t.speaker_name} [{t.start_time} - {t.end_time}]: {t.text}" for t in data.transcript])
        
        candidate_md = str(data.external_metadata.model_dump())
        interviewers = ", ".join(data.external_metadata.interviewer_names)
        
        llm_response = analyze_transcript_roles(transcript_text, candidate_md, interviewers)
        
        try:
            parsed = json.loads(llm_response)
            results = parsed.get("participants", [])
        except Exception as e:
            return []
            
        for participant in data.participant_information:
            disp_name = participant.display_name.lower()
            matched_res = None
            for res in results:
                res_name = res.get("participant_name", "").lower()
                if res_name and (res_name in disp_name or disp_name in res_name):
                    matched_res = res
                    break
                    
            if matched_res:
                role = matched_res.get("role", "").lower()
                conf = float(matched_res.get("confidence", 50.0))
                reason = matched_res.get("reason", "")
                
                if role == "candidate":
                    score_val = conf
                else:
                    score_val = 100.0 - conf
                    
                scores.append(EvidenceScore(
                    participant_id=participant.participant_id,
                    module=self.name,
                    score=score_val / 100.0,
                    confidence=score_val,
                    reason=reason,
                    metadata={"role_assigned": role}
                ))
                
        return scores
