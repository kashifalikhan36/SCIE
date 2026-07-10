import json
import os
from models import InterviewData
from detector import Detector
from fusion_engine import FusionEngine

def print_explanation(result):
    candidate = result.get("candidate")
    if not candidate:
        print("\nNo candidate detected.")
        return
        
    print("\n--- FINAL RESULT ---")
    print(f"Selected Candidate: {candidate.get('display_name', 'Unknown')}")
    print(f"Participant ID: {candidate.get('participant_id', 'Unknown')}")
    print(f"Overall Confidence: {candidate.get('confidence', 0.0)}%")
    
    if candidate.get("status") == "AMBIGUOUS":
        print(f"\n[WARNING: AMBIGUOUS]")
        print(f"Reason: {candidate.get('reason')}")
        print(f"Missing Evidence Modules: {', '.join(candidate.get('missing_evidence', []))}")
        print(f"Suggestions: {candidate.get('suggestions')}")
        return
        
    print("\nEvidence:")
    
    # Find candidate in ranking to get evidence summary
    ranking = result.get("ranking", [])
    cand_info = next((r for r in ranking if r["participant_id"] == candidate.get("participant_id")), None)
    
    if cand_info:
        for ev in cand_info.get("evidence_summary", []):
            if ev.get("confidence", 0) > 0:
                print(f"[+] {ev.get('reason')}")
    
    print("--------------------\n")

def main():
    json_path = "data.json"
    
    if not os.path.exists(json_path):
        print(f"Error: {json_path} not found.")
        return
        
    with open(json_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)
        
    try:
        data = InterviewData(**raw_data)
    except Exception as e:
        print(f"Failed to parse data.json: {e}")
        return
        
    print("Starting candidate detection...")
    
    detector = Detector()
    evidence_list = detector.process(data)
    
    fusion = FusionEngine()
    result = fusion.fuse(evidence_list, data.participant_information)
    
    os.makedirs("output", exist_ok=True)
    output_file = os.path.join("output", "candidate_detection.json")
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=4, ensure_ascii=False)
        
    print(f"Candidate Detection complete. Output saved to {output_file}")
    
    print_explanation(result)

if __name__ == "__main__":
    main()
