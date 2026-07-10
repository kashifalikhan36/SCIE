from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict

class JoinLeaveEvent(BaseModel):
    timestamp: float
    event_type: str  # "join" or "leave"

class WebcamEvent(BaseModel):
    timestamp: float
    event_type: str  # "on" or "off"

class ScreenShareEvent(BaseModel):
    timestamp: float
    event_type: str  # "start" or "stop"

class SpeakingActivity(BaseModel):
    start_time: float
    end_time: float

class ParticipantInfo(BaseModel):
    participant_id: str
    display_name: Optional[str] = None
    join_leave_events: List[JoinLeaveEvent] = Field(default_factory=list)
    webcam_events: List[WebcamEvent] = Field(default_factory=list)
    screen_share_events: List[ScreenShareEvent] = Field(default_factory=list)
    speaking_activity: List[SpeakingActivity] = Field(default_factory=list)
    speaking_duration: float = 0.0

class TranscriptUtterance(BaseModel):
    speaker_id: str
    text: str
    start_time: float
    end_time: float

class ExternalMetadata(BaseModel):
    candidate_name: Optional[str] = None
    candidate_email: Optional[str] = None
    calendar_invite: Optional[str] = None
    interview_schedule: Optional[str] = None
    interviewer_names: List[str] = Field(default_factory=list)

class InterviewMetadata(BaseModel):
    external_metadata: Optional[ExternalMetadata] = None
    # For flexibility, we can accept other structured metadata 
    extra: Dict[str, Any] = Field(default_factory=dict)
