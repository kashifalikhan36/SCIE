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
            
        # We can also check Q&A ping-pong logic by merging speaking_activity from all streams 
        # and checking who speaks after the known interviewer. 
        # For simplicity, we use turns, ratio, and average length.
        
        for stream in data.audio.streams:
            speaking_secs = duration_to_seconds(stream.speaking_duration)
            turns = len(stream.speaking_activity)
            ratio = speaking_secs / total_speaking_time_all if total_speaking_time_all else 0
            avg_length = speaking_secs / turns if turns > 0 else 0
            
            # Typical candidate behavior: answers questions (longer avg length, ratio 40-70%)
            # Interviewer behavior: asks questions (shorter avg length, more turns but less total time)
            if 0.4 <= ratio <= 0.8 and avg_length > 5.0:
                conf = 85.0
                reason = f"Speaking ratio {ratio:.1%} and average answer length ({avg_length:.1f}s) strongly suggest candidate responding to questions."
            elif ratio > 0.8:
                conf = 70.0
                reason = f"Speaking ratio {ratio:.1%} is very high. Active participant, likely candidate."
            elif 0.1 < ratio < 0.4 and avg_length < 5.0:
                conf = 30.0
                reason = f"Speaking ratio {ratio:.1%} and short responses suggest interviewer asking questions."
            else:
                conf = 40.0
                reason = f"Speaking ratio {ratio:.1%} ({turns} turns)."
                
            scores.append(EvidenceScore(
                participant_id=stream.participant_id,
                module=self.name,
                score=conf / 100.0,
                confidence=conf,
                reason=reason,
                metadata={"ratio": ratio, "turns": turns, "avg_length": avg_length}
            ))
            
        return scores
