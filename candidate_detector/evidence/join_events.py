from .confidence import BaseEvidenceModule, EvidenceScore
from models import InterviewData
from utils import parse_time
from datetime import timedelta

class JoinTimingModule(BaseEvidenceModule):
    def run(self, data: InterviewData) -> list[EvidenceScore]:
        scores = []
        schedule = data.external_metadata.interview_schedule
        
        if not schedule:
            return []
            
        try:
            start_dt_str = f"{schedule.date}T{schedule.start_time}"
            interview_start = parse_time(start_dt_str)
        except Exception:
            return []

        for participant in data.participant_information:
            join_events = [e for e in participant.join_leave_events if e.event == "join"]
            
            if not join_events:
                scores.append(EvidenceScore(
                    participant_id=participant.participant_id,
                    module=self.name,
                    score=0.0,
                    confidence=0.0,
                    reason="No join events found.",
                    metadata={"join_events": 0}
                ))
                continue
                
            first_join = parse_time(join_events[0].timestamp)
            diff = (first_join - interview_start).total_seconds()
            diff_minutes = round(diff / 60.0, 1)
            
            if diff < -300:
                conf = 80.0
                reason = "Joined more than 5 mins early."
            elif -300 <= diff <= 0:
                conf = 90.0
                reason = "Joined just before the interview started."
            elif 0 < diff <= 300:
                conf = 70.0
                reason = "Joined slightly late (within 5 mins)."
            else:
                conf = 40.0
                reason = "Joined very late."
                
            if len(join_events) > 1:
                reason += f" Participant rejoined {len(join_events) - 1} times."
                
            scores.append(EvidenceScore(
                participant_id=participant.participant_id,
                module=self.name,
                score=conf / 100.0,
                confidence=conf,
                reason=reason,
                metadata={"join_delta_minutes": diff_minutes, "rejoins": len(join_events) - 1}
            ))
            
        return scores
