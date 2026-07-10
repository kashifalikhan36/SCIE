from .confidence import BaseEvidenceModule, EvidenceScore
from models import InterviewData

class TimelineModule(BaseEvidenceModule):
    def run(self, data: InterviewData) -> list[EvidenceScore]:
        scores = []
        
        # This module builds a timeline per participant and evaluates if the timeline resembles a candidate.
        for participant in data.participant_information:
            events = []
            
            for e in participant.join_leave_events:
                events.append({"time": e.timestamp, "type": e.event})
            for e in participant.webcam_events:
                events.append({"time": e.timestamp, "type": e.event})
            for e in participant.screen_share_events:
                events.append({"time": e.timestamp, "type": e.event})
                
            # Find audio stream for this participant
            if data.audio:
                for stream in data.audio.streams:
                    if stream.participant_id == participant.participant_id:
                        for a in stream.speaking_activity:
                            events.append({"time": a.start_time, "type": "speaking_start"})
                            
            events.sort(key=lambda x: x["time"])
            
            if not events:
                continue
                
            # A candidate typically joins, turns on camera, speaks, and maybe shares screen.
            types_seen = set([e["type"] for e in events])
            
            evidence_points = 0
            reasons = []
            
            if "join" in types_seen:
                evidence_points += 20
                reasons.append("Joined interview")
            if "webcam_on" in types_seen:
                evidence_points += 30
                reasons.append("Turned on webcam")
            if "speaking_start" in types_seen:
                evidence_points += 30
                reasons.append("Participated in speaking")
            if "screen_share_start" in types_seen:
                evidence_points += 20
                reasons.append("Shared screen")
                
            conf = min(100.0, float(evidence_points))
            reason_str = "Timeline events: " + ", ".join(reasons)
            
            scores.append(EvidenceScore(
                participant_id=participant.participant_id,
                module=self.name,
                score=conf / 100.0,
                confidence=conf,
                reason=reason_str,
                metadata={"events": list(types_seen)}
            ))
            
        return scores
