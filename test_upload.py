import requests
import json
import time

url = "http://127.0.0.1:8000/api/v1/interviews/upload"

metadata = {
    "candidate": "Test Candidate",
    "candidate_email": "test@example.com",
    "calendar_invite": "N/A",
    "interview_schedule": "Today",
    "interviewers": ["John", "Jane"]
}

participants = [
    {
        "participant_id": "p_1",
        "display_name": "Test Candidate",
        "extra_data": {
            "join_event": "Joined 0:00",
            "leave_event": "Left 10:00",
            "webcam": "On",
            "screen_share": "None",
            "speaking_activity": "50%",
            "speaking_duration": "5m"
        }
    }
]

print("Uploading video...")
with open(r"C:\Users\Data\Documents\GitHub\SCIE\tests\video\interview.mp4", "rb") as f:
    files = {
        "video": ("interview.mp4", f, "video/mp4")
    }
    data = {
        "metadata": json.dumps(metadata),
        "participants": json.dumps(participants)
    }
    
    response = requests.post(url, files=files, data=data)

if response.status_code == 200:
    res_data = response.json()
    meeting_id = res_data.get("meeting_id")
    print(f"Upload successful! Meeting ID: {meeting_id}")
else:
    print(f"Upload failed: {response.status_code}")
    print(response.text)
