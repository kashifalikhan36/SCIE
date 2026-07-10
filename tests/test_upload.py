import asyncio
import httpx
import json
from pathlib import Path

async def test_upload():
    url = "http://127.0.0.1:8000/api/v1/interviews/upload"
    video_path = Path("test.webm")
    
    if not video_path.exists():
        print(f"Video file not found at {video_path}")
        return
        
    metadata = {
        "external_metadata": {
            "candidate_name": "Test Candidate",
            "interviewer_names": ["Interviewer A"]
        }
    }
    participants = [
        {"participant_id": "P1", "display_name": "Candidate"},
        {"participant_id": "P2", "display_name": "Interviewer"}
    ]
    transcript = [
        {"speaker_id": "P1", "text": "Hello", "start_time": 0.0, "end_time": 1.0}
    ]
    
    with open(video_path, "rb") as f:
        files = {"video": ("interview.mp4", f, "video/mp4")}
        data = {
            "metadata": json.dumps(metadata),
            "participants": json.dumps(participants),
            "transcript": json.dumps(transcript)
        }
        
        print("Sending upload request...")
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, files=files, data=data)
            print(f"Status Code: {response.status_code}")
            print(f"Response: {response.text}")
            
if __name__ == "__main__":
    asyncio.run(test_upload())
