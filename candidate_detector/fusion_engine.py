from collections import defaultdict
from config import WEIGHTS
from evidence.confidence import EvidenceScore

class FusionEngine:
    def __init__(self, weights=WEIGHTS):
        self.weights = weights
        self.total_weight = sum(weights.values())

    def fuse(self, evidence_list: list[EvidenceScore], participants_info: list) -> dict:
        participant_scores = defaultdict(float)
        participant_evidence = defaultdict(list)
        
        participant_names = {p.participant_id: p.display_name for p in participants_info}

        for ev in evidence_list:
            weight = self.weights.get(ev.module, 0)
            # Normalize module confidence (0-100) by weight to get contribution
            contribution = (ev.confidence / 100.0) * weight
            
            # Special case for InterviewerDetectionModule: if they match, penalize heavily
            if ev.module == "InterviewerDetectionModule" and ev.confidence == 0:
                participant_scores[ev.participant_id] -= 1000  # huge penalty
                
            participant_scores[ev.participant_id] += contribution
            
            # Save readable evidence
            participant_evidence[ev.participant_id].append({
                "module": ev.module,
                "confidence": ev.confidence,
                "reason": ev.reason
            })

        # Normalize final scores to 0-100
        ranked = []
        for pid, raw_score in participant_scores.items():
            final_conf = max(0.0, min(100.0, (raw_score / self.total_weight) * 100.0)) if self.total_weight > 0 else 0.0
            ranked.append({
                "participant_id": pid,
                "display_name": participant_names.get(pid, "Unknown"),
                "confidence": round(final_conf, 2),
                "evidence_summary": participant_evidence[pid]
            })

        # Sort descending
        ranked.sort(key=lambda x: x["confidence"], reverse=True)
        
        result = {
            "candidate": None,
            "ranking": ranked,
            "evidence": ranked
        }

        if len(ranked) == 0:
            return result

        top_candidate = ranked[0]
        
        # Check ambiguity
        if len(ranked) > 1:
            second_candidate = ranked[1]
            if (top_candidate["confidence"] - second_candidate["confidence"]) < 5.0:
                result["candidate"] = {
                    "participant_id": top_candidate["participant_id"],
                    "display_name": top_candidate["display_name"],
                    "confidence": top_candidate["confidence"],
                    "status": "AMBIGUOUS",
                    "reason": f"Top two candidates have very similar confidence scores ({top_candidate['confidence']} vs {second_candidate['confidence']})"
                }
                return result
                
        result["candidate"] = {
            "participant_id": top_candidate["participant_id"],
            "display_name": top_candidate["display_name"],
            "confidence": top_candidate["confidence"]
        }
        
        return result
