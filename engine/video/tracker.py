import logging
import uuid
from typing import List, Dict, Tuple
from engine.video.schemas import DetectedFace, DiarizedTrack
from engine.video.config import video_config

logger = logging.getLogger("SCIE.video_engine.tracker")

class FaceTracker:
  """Implements a pure-Python multi-object face tracker matching faces across frames via IoU."""

  def __init__(self):
    # Dictionary mapping track_id to track state dictionary
    self.tracks: Dict[str, Dict] = {}
    self.track_counter = 1

  def _calculate_iou(self, box_a: Tuple[float, float, float, float], box_b: Tuple[float, float, float, float]) -> float:
    """Calculates Intersection-over-Union (IoU) between two bounding boxes [xmin, ymin, w, h]."""
    ax1, ay1, aw, ah = box_a
    bx1, by1, bw, bh = box_b
    
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh

    # Intersection coordinates
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    intersection_w = max(0.0, ix2 - ix1)
    intersection_h = max(0.0, iy2 - iy1)
    intersection_area = intersection_w * intersection_h

    # Union area
    area_a = aw * ah
    area_b = bw * bh
    union_area = area_a + area_b - intersection_area

    if union_area <= 0.0:
      return 0.0
      
    return intersection_area / union_area

  def update(self, detected_faces: List[DetectedFace], timestamp: int) -> List[DiarizedTrack]:
    """Associates detections with active tracks and yields diarized tracks for this frame."""
    
    # 1. Compute IoU matrix between existing tracks and new detections
    track_ids = list(self.tracks.keys())
    matched_detections = set()
    matched_tracks = set()

    associations: List[Tuple[float, str, int]] = [] # list of (iou, track_id, detection_idx)

    for detection_idx, face in enumerate(detected_faces):
      for track_id in track_ids:
        track_box = self.tracks[track_id]["bbox"]
        iou = self._calculate_iou(track_box, face.bbox)
        if iou >= 0.30: # IoU threshold to associate
          associations.append((iou, track_id, detection_idx))

    # Sort associations by highest IoU first
    associations.sort(key=lambda x: x[0], reverse=True)

    # Greedy matching
    for iou, track_id, detection_idx in associations:
      if track_id not in matched_tracks and detection_idx not in matched_detections:
        matched_tracks.add(track_id)
        matched_detections.add(detection_idx)
        
        # Update existing track state
        track = self.tracks[track_id]
        track["bbox"] = detected_faces[detection_idx].bbox
        track["age"] = 0 # reset missed count
        track["last_seen"] = timestamp
        track["visibility"] = True
        track["confidence"] = detected_faces[detection_idx].confidence
        track["seen_count"] += 1

    # 2. Handle unmatched tracks (tracks not seen in this frame)
    unmatched_tracks = set(track_ids) - matched_tracks
    for track_id in unmatched_tracks:
      track = self.tracks[track_id]
      track["age"] += 1
      track["visibility"] = False
      
      # If track has been missing for too long, delete it
      if track["age"] > video_config.TRACK_MAX_AGE_FRAMES:
        logger.info(f"Tracker: Removing stale track {track_id} (inactive for {track['age']} frames)")
        del self.tracks[track_id]

    # 3. Handle unmatched detections (create new tracks)
    for idx, face in enumerate(detected_faces):
      if idx not in matched_detections:
        new_track_id = f"Track_{self.track_counter}"
        self.track_counter += 1
        
        self.tracks[new_track_id] = {
            "bbox": face.bbox,
            "age": 0,
            "last_seen": timestamp,
            "visibility": True,
            "confidence": face.confidence,
            "seen_count": 1
        }
        logger.info(f"Tracker: Created new track {new_track_id} with confidence {face.confidence:.2f}")

    # 4. Assemble the output list of active diarized tracks
    active_diarized_tracks: List[DiarizedTrack] = []
    for track_id, track in self.tracks.items():
      # Only output if the track is visible or was seen recently
      active_diarized_tracks.append(
          DiarizedTrack(
              track_id=track_id,
              bbox=track["bbox"],
              age=track["seen_count"],
              last_seen=track["last_seen"],
              visibility=track["visibility"],
              confidence=track["confidence"]
          )
      )

    return active_diarized_tracks
