import json
import os
from models import InterviewData
from detector import Detector
from fusion_engine import FusionEngine

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
    
    # Save output
    os.makedirs("output", exist_ok=True)
    output_file = os.path.join("output", "candidate_detection.json")
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=4, ensure_ascii=False)
        
    print(f"Candidate Detection complete. Output saved to {output_file}")
    
    candidate = result.get("candidate")
    if candidate:
        print("\n--- FINAL RESULT ---")
        print(f"Candidate Selected: {candidate.get('display_name', 'Unknown')}")
        print(f"Participant ID: {candidate.get('participant_id', 'Unknown')}")
        print(f"Overall Confidence: {candidate.get('confidence', 0.0)}")
        if candidate.get("status") == "AMBIGUOUS":
            print(f"WARNING: AMBIGUOUS - {candidate.get('reason')}")
        print("--------------------\n")

if __name__ == "__main__":
    main()
