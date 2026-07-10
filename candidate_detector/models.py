from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class JoinLeaveEvent(BaseModel):
    event: str
    timestamp: str
    relative_time: str

class WebcamEvent(BaseModel):
    event: str
    timestamp: str
    relative_time: str

class ScreenShareEvent(BaseModel):
    event: str
    timestamp: str
    relative_time: str
    shared_content: Optional[str] = None

class ParticipantInfo(BaseModel):
    participant_id: str = Field(alias="Participant ID")
    display_name: str = Field(alias="Display name")
    join_leave_events: List[JoinLeaveEvent] = Field(default_factory=list, alias="Join/leave events")
    webcam_events: List[WebcamEvent] = Field(default_factory=list, alias="Webcam on/off")
    screen_share_events: List[ScreenShareEvent] = Field(default_factory=list, alias="Screen share events")

class SpeakingActivity(BaseModel):
    start_time: str
    end_time: str

class AudioStream(BaseModel):
    participant_id: str = Field(alias="Participant ID")
    display_name: str = Field(alias="Display name")
    speaking_duration: str = Field(alias="Speaking duration", default="00:00:00")
    speaking_activity: List[SpeakingActivity] = Field(default_factory=list, alias="Speaking activity")

class AudioData(BaseModel):
    streams: List[AudioStream] = Field(default_factory=list)

class WebcamStream(BaseModel):
    participant_id: str = Field(alias="Participant ID")
    display_name: str = Field(alias="Display name")

class VideoData(BaseModel):
    webcam_streams: List[WebcamStream] = Field(default_factory=list)

class TranscriptLine(BaseModel):
    speaker_name: str = Field(alias="Speaker Name")
    start_time: str
    end_time: str
    text: str

class InterviewSchedule(BaseModel):
    date: str
    start_time: str
    end_time: str
    timezone: str

class ExternalMetadata(BaseModel):
    candidate_name: str = Field(alias="Candidate name")
    candidate_email: Optional[str] = Field(None, alias="Candidate email")
    calendar_invite: Optional[Dict[str, Any]] = Field(None, alias="Calendar invite")
    interview_schedule: Optional[InterviewSchedule] = Field(None, alias="Interview schedule")
    interviewer_names: List[str] = Field(default_factory=list, alias="Interviewer names")

class InterviewData(BaseModel):
    participant_information: List[ParticipantInfo] = Field(default_factory=list, alias="Participant Information")
    audio: Optional[AudioData] = Field(None, alias="Audio")
    video: Optional[VideoData] = Field(None, alias="Video")
    transcript: List[TranscriptLine] = Field(default_factory=list, alias="Transcript")
    external_metadata: ExternalMetadata = Field(alias="External Metadata")
