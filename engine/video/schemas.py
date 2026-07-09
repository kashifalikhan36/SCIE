from pydantic import BaseModel, Field
from typing import List, Optional, Tuple, Dict, Any

class VideoChunk(BaseModel):
  """Representation of an incoming video packet chunk."""
  meeting_id: str
  timestamp: int
  chunk_index: int
  data: bytes
  file_path: Optional[str] = None

class DetectedFace(BaseModel):
  """Object representing a face detected in a specific video frame."""
  bbox: Tuple[float, float, float, float] = Field(..., description="[xmin, ymin, width, height] normalized relative to frame dimensions")
  confidence: float
  landmarks: Optional[List[Tuple[float, float]]] = None
  frame_id: int
  timestamp: int

class DiarizedTrack(BaseModel):
  """Object representing a face track assigned a persistent tracker identifier."""
  track_id: str
  bbox: Tuple[float, float, float, float]
  age: int
  last_seen: int
  visibility: bool
  confidence: float

class VisualEvidence(BaseModel):
  """Object representing visual identity evidence for downstream fusion analysis."""
  meeting_id: str
  track_id: str
  frame_id: int
  face_embedding: List[float]
  face_similarity: float
  recognition_confidence: float
  detection_confidence: float
  tracking_confidence: float
  visibility: bool
  timestamp: int

class ParticipantVisualState(BaseModel):
  """Live participant identity state cached in Redis."""
  track_id: str
  latest_embedding: List[float]
  latest_similarity: float
  last_seen: int
  face_visible: bool
  tracking_confidence: float
  recognition_confidence: float
  timestamp: int
