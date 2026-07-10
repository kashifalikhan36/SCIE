import json
from .confidence import BaseEvidenceModule, EvidenceScore
from models import InterviewData
from llm import analyze_transcript_roles

class TranscriptModule(BaseEvidenceModule):
    def run(self, data: InterviewData) -> list[EvidenceScore]:
        scores = []
        if not data.transcript:
            return []
            
        # Format transcript for LLM
        transcript_text = "\n".join([f"{t.speaker_name} [{t.start_time} - {t.end_time}]: {t.text}" for t in data.transcript])
        
        # We might want to truncate if it's too long, but let's assume it fits in context
        llm_response = analyze_transcript_roles(transcript_text)
        
        try:
            results = json.loads(llm_response)
            if not isinstance(results, list):
                if isinstance(results, dict) and "participants" in results:
                    results = results["participants"]
                elif isinstance(results, dict):
                    results = [results]
        except Exception as e:
            return []
            
        for participant in data.participant_information:
            disp_name = participant.display_name
            # Find in results
            matched_res = None
            for res in results:
                # the LLM might return partial names
                if res.get("participant_name", "").lower() in disp_name.lower() or disp_name.lower() in res.get("participant_name", "").lower():
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
                    reason=reason
                ))
                
        return scores
