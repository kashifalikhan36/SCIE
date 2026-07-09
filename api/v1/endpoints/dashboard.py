from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any, Optional
from database.mongodb import get_mongo_db
from engine.fusion.constants import (
    MONGO_MEETINGS_COL,
    MONGO_PARTICIPANT_STATES_COL,
    MONGO_CONFIDENCE_HISTORY_COL,
    MONGO_FUSION_EVENTS_COL,
    MONGO_RANKING_HISTORY_COL,
    MONGO_EXPLANATIONS_COL
)

router = APIRouter()

@router.get("/meetings")
async def get_all_meetings(limit: int = 100):
    """Get latest meetings."""
    db = get_mongo_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    
    cursor = db[MONGO_MEETINGS_COL].find({}, {"_id": 0}).sort("created_at", -1).limit(limit)
    meetings = await cursor.to_list(length=limit)
    return meetings

@router.get("/meetings/{meeting_id}")
async def get_meeting_summary(meeting_id: str):
    """Get metadata for a specific meeting."""
    db = get_mongo_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    
    meeting = await db[MONGO_MEETINGS_COL].find_one({"meeting_id": meeting_id}, {"_id": 0})
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    
    # Get latest ranking
    latest_ranking = await db[MONGO_RANKING_HISTORY_COL].find_one(
        {"meeting_id": meeting_id},
        {"_id": 0},
        sort=[("snapshot_timestamp", -1)]
    )
    
    return {
        "meeting": meeting,
        "latest_ranking": latest_ranking
    }

@router.get("/meetings/{meeting_id}/participants")
async def get_meeting_participants(meeting_id: str):
    """Get the latest participant states for a meeting."""
    db = get_mongo_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    
    # We want the *latest* state per participant in this meeting.
    pipeline = [
        {"$match": {"meeting_id": meeting_id}},
        {"$sort": {"snapshot_timestamp": -1}},
        {"$group": {
            "_id": "$participant_id",
            "latest_state": {"$first": "$$ROOT"}
        }},
        {"$project": {"latest_state._id": 0}}
    ]
    
    states = []
    async for doc in db[MONGO_PARTICIPANT_STATES_COL].aggregate(pipeline):
        states.append(doc.get("latest_state"))
        
    return states

@router.get("/meetings/{meeting_id}/timeline")
async def get_meeting_timeline(meeting_id: str, limit: int = 1000):
    """Get chronological events and confidence history."""
    db = get_mongo_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    
    events_cursor = db[MONGO_FUSION_EVENTS_COL].find(
        {"meeting_id": meeting_id},
        {"_id": 0}
    ).sort("timestamp", 1).limit(limit)
    
    events = await events_cursor.to_list(length=limit)
    
    confidence_cursor = db[MONGO_CONFIDENCE_HISTORY_COL].find(
        {"meeting_id": meeting_id},
        {"_id": 0}
    ).sort("timestamp", 1).limit(limit)
    
    confidence_history = await confidence_cursor.to_list(length=limit)
    
    return {
        "events": events,
        "confidence_history": confidence_history
    }

@router.get("/meetings/{meeting_id}/analytics")
async def get_meeting_analytics(meeting_id: str):
    """Get aggregated analytics for charts."""
    # Simplified version: returns raw explanations and stats 
    db = get_mongo_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    
    explanations = await db[MONGO_EXPLANATIONS_COL].find(
        {"meeting_id": meeting_id},
        {"_id": 0}
    ).sort("timestamp", 1).to_list(length=500)
    
    return {
        "explanations": explanations
    }
