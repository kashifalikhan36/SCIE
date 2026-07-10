from .confidence import BaseEvidenceModule, EvidenceScore
from models import InterviewData
from utils import duration_to_seconds

class SpeakingModule(BaseEvidenceModule):
    def run(self, data: InterviewData) -> list[EvidenceScore]:
        scores = []
        
        if not data.audio or not data.audio.streams:
            return []
            
        total_speaking_time_all = sum(duration_to_seconds(s.speaking_duration) for s in data.audio.streams)
        if total_speaking_time_all == 0:
            return []
            
        for stream in data.audio.streams:
            speaking_secs = duration_to_seconds(stream.speaking_duration)
            turns = len(stream.speaking_activity)
            ratio = speaking_secs / total_speaking_time_all
            
            # Usually candidate speaks around 40-70% of the time. 
            # Interviewer might speak less (just asking questions) or more (if very talkative).
            # But number of turns is also a good indicator.
            
            if 0.4 <= ratio <= 0.8:
                conf = 85.0
                reason = f"Speaking ratio {ratio:.1%} is typical for a candidate. ({turns} turns)"
            elif ratio > 0.8:
                conf = 70.0
                reason = f"Speaking ratio {ratio:.1%} is very high. ({turns} turns)"
            else:
                conf = 40.0
                reason = f"Speaking ratio {ratio:.1%} is low. ({turns} turns)"
                
            scores.append(EvidenceScore(
                participant_id=stream.participant_id,
                module=self.name,
                score=conf / 100.0,
                confidence=conf,
                reason=reason
            ))
            
        return scores
