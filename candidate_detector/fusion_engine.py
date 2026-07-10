from collections import defaultdict
from config import WEIGHTS
from evidence.confidence import EvidenceScore

class FusionEngine:
    def __init__(self, weights=WEIGHTS):
        self.weights = weights

    def fuse(self, evidence_list: list[EvidenceScore], participants_info: list) -> dict:
        participant_scores = defaultdict(float)
        participant_evidence = defaultdict(list)
        
        participant_names = {p.participant_id: p.display_name for p in participants_info}

        # Determine which modules actually fired (dynamic weighting)
        active_modules = set(ev.module for ev in evidence_list)
        # Interviewer Detection is a penalty module, not a weighted positive module
        if "Interviewer Detection" in active_modules:
            active_modules.remove("Interviewer Detection")
            
        dynamic_total_weight = sum(self.weights.get(m, 0) for m in active_modules)

        # Apply weights and penalties
        for ev in evidence_list:
            if ev.module == "Interviewer Detection":
                if ev.confidence == 0:
                    participant_scores[ev.participant_id] -= 1000  # heavy penalty
                continue
                
            weight = self.weights.get(ev.module, 0)
            contribution = (ev.confidence / 100.0) * weight
            participant_scores[ev.participant_id] += contribution
            
            participant_evidence[ev.participant_id].append({
                "module": ev.module,
                "confidence": ev.confidence,
                "reason": ev.reason,
                "metadata": ev.metadata
            })

        # Normalize final scores to 0-100 based on dynamic weight
        ranked = []
        for pid, raw_score in participant_scores.items():
            if raw_score < 0:
                final_conf = 0.0
            else:
                final_conf = max(0.0, min(100.0, (raw_score / dynamic_total_weight) * 100.0)) if dynamic_total_weight > 0 else 0.0
                
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
                missing_evidence = [m for m in self.weights.keys() if m not in active_modules]
                result["candidate"] = {
                    "participant_id": "None",
                    "display_name": "None",
                    "confidence": 0.0,
                    "status": "AMBIGUOUS",
                    "reason": f"Top two candidates ({top_candidate['display_name']} and {second_candidate['display_name']}) differ by less than 5 points.",
                    "missing_evidence": missing_evidence,
                    "suggestions": "Review missing modules like Identity Correlation or Conversation Role. Ensure the transcript and metadata are complete."
                }
                return result
                
        result["candidate"] = {
            "participant_id": top_candidate["participant_id"],
            "display_name": top_candidate["display_name"],
            "confidence": top_candidate["confidence"]
        }
        
        return result
