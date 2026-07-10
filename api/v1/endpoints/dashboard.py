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

@router.get("/stats")
async def get_dashboard_stats():
    """Get high-level stats for the overview dashboard cards."""
    db = get_mongo_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    total_meetings = await db[MONGO_MEETINGS_COL].count_documents({})
    
    # Count unique participants across all meetings
    pipeline = [{"$group": {"_id": "$participant_id"}}]
    unique_participants = len(await db[MONGO_PARTICIPANT_STATES_COL].aggregate(pipeline).to_list(length=100000))

    # Average fusion confidence from latest ranking snapshots
    avg_pipeline = [
        {"$group": {"_id": "$meeting_id", "latest_ts": {"$max": "$snapshot_timestamp"}}},
    ]
    # Simpler: average confidence across all ranking history
    conf_pipeline = [
        {"$group": {"_id": None, "avg_confidence": {"$avg": "$confidence_score"}}}
    ]
    conf_result = await db[MONGO_RANKING_HISTORY_COL].aggregate(conf_pipeline).to_list(length=1)
    avg_confidence = round(conf_result[0]["avg_confidence"] * 100, 1) if conf_result and conf_result[0]["avg_confidence"] else 0

    # Count fusion events in last 60 seconds as a proxy for "active" interviews
    import time
    recent_cutoff = time.time() - 60
    active_meetings_pipeline = [
        {"$match": {"timestamp": {"$gte": recent_cutoff}}},
        {"$group": {"_id": "$meeting_id"}},
        {"$count": "count"}
    ]
    active_result = await db[MONGO_FUSION_EVENTS_COL].aggregate(active_meetings_pipeline).to_list(length=1)
    active_count = active_result[0]["count"] if active_result else 0

    return {
        "total_meetings": total_meetings,
        "total_participants": unique_participants,
        "active_interviews": active_count,
        "avg_confidence_pct": avg_confidence,
    }

