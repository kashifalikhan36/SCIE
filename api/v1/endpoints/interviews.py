import os
import uuid
import json
import shutil
from fastapi import APIRouter, File, UploadFile, Form, BackgroundTasks, HTTPException
from pydantic import BaseModel
from schemas.interview import InterviewMetadata, ParticipantInfo, TranscriptUtterance
from typing import Optional, Dict, Any, List
from pydantic import ValidationError

from engine.offline.processor import OfflineVideoProcessor, PROCESSING_STATUS

router = APIRouter()

import tempfile
UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "scie_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

class OfflineUploadResponse(BaseModel):
    meeting_id: str
    status: str

@router.post("/upload", response_model=OfflineUploadResponse)
async def upload_interview_video(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    metadata: Optional[str] = Form(None),  # JSON string
    participants: Optional[str] = Form(None), # JSON string
    transcript: Optional[str] = Form(None) # JSON string
):
    """Upload a pre-recorded interview video for offline processing."""
    
    if not video.filename:
        raise HTTPException(status_code=400, detail="No video file provided.")
        
    meta_obj = None
    participants_list = []
    transcript_list = []
    
    try:
        if metadata:
            meta_dict = json.loads(metadata)
            meta_obj = InterviewMetadata(**meta_dict)
            
        if participants:
            part_list_raw = json.loads(participants)
            if not isinstance(part_list_raw, list):
                raise ValueError("participants must be a JSON array")
            participants_list = [ParticipantInfo(**p) for p in part_list_raw]
            
        if transcript:
            trans_list_raw = json.loads(transcript)
            if not isinstance(trans_list_raw, list):
                raise ValueError("transcript must be a JSON array")
            transcript_list = [TranscriptUtterance(**t) for t in trans_list_raw]
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON string: {str(e)}")
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=f"Schema validation error: {str(e)}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    meeting_id = f"offline_{uuid.uuid4().hex[:8]}"
    file_extension = os.path.splitext(video.filename)[1]
    
    # Save video to disk
    filepath = os.path.join(UPLOAD_DIR, f"{meeting_id}{file_extension}")
    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(video.file, buffer)
        
    # Start background task
    processor = OfflineVideoProcessor(
        meeting_id=meeting_id, 
        filepath=filepath, 
        metadata=meta_obj,
        participants=participants_list,
        transcript=transcript_list
    )
    
    # We must run processor.process in a new event loop or using asyncio.create_task since 
    # it's async and background_tasks expects async funcs to run properly.
    # FastAPI's BackgroundTasks automatically handles async functions.
    background_tasks.add_task(processor.process)
    
    return OfflineUploadResponse(meeting_id=meeting_id, status="processing")

@router.get("/{meeting_id}/status")
async def get_processing_status(meeting_id: str):
    """Get the current offline processing status for an uploaded video."""
    from database.redis import get_redis
    redis_client = await get_redis()
    status_str = await redis_client.get(f"offline_status:{meeting_id}")
    if not status_str:
        # Check if it was completed earlier
        return {"status": "unknown", "progress": 0.0}
    return json.loads(status_str)

@router.get("/{meeting_id}/timeline")
async def get_meeting_timeline(meeting_id: str):
    """Retrieve timeline events for the meeting."""
    from database.mongodb import get_mongo_db
    db = get_mongo_db()
    events = await db.association_timeline_events.find({"meeting_id": meeting_id}).sort("timestamp", 1).to_list(1000)
    for event in events:
        event["_id"] = str(event["_id"])
    return {"meeting_id": meeting_id, "timeline": events}

@router.get("/{meeting_id}/confidence")
async def get_meeting_confidence(meeting_id: str):
    """Retrieve confidence snapshots for the meeting."""
    from database.mongodb import get_mongo_db
    db = get_mongo_db()
    snapshots = await db.fusion_confidence_snapshots.find({"meeting_id": meeting_id}).sort("timestamp", 1).to_list(1000)
    for snap in snapshots:
        snap["_id"] = str(snap["_id"])
    return {"meeting_id": meeting_id, "confidence_history": snapshots}

@router.get("/{meeting_id}/summary")
async def get_meeting_summary(meeting_id: str):
    """Retrieve the reasoning report summary for the meeting."""
    from database.mongodb import get_mongo_db
    db = get_mongo_db()
    report = await db.reasoning_reports.find_one({"meeting_id": meeting_id})
    if not report:
        raise HTTPException(status_code=404, detail="Reasoning report not found")
    report["_id"] = str(report["_id"])
    return {"meeting_id": meeting_id, "summary": report.get("summary", ""), "is_verified": report.get("is_verified", False)}

@router.get("/{meeting_id}/report")
async def download_json_report(meeting_id: str):
    """Download the comprehensive JSON report for the meeting."""
    from database.mongodb import get_mongo_db
    db = get_mongo_db()
    
    report = await db.reasoning_reports.find_one({"meeting_id": meeting_id})
    if not report:
        raise HTTPException(status_code=404, detail="Report not generated yet.")
    
    report["_id"] = str(report["_id"])
    
    fusion_rankings = await db.fusion_ranking_snapshots.find({"meeting_id": meeting_id}).sort("timestamp", -1).limit(1).to_list(1)
    if fusion_rankings:
        fusion_rankings[0]["_id"] = str(fusion_rankings[0]["_id"])
        report["latest_fusion_ranking"] = fusion_rankings[0]
        
    identity_matches = await db.identity_matches.find({"meeting_id": meeting_id}).to_list(100)
    for match in identity_matches:
        match["_id"] = str(match["_id"])
    report["identity_matches"] = identity_matches
    
    return report
