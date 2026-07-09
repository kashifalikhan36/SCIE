import logging
import time
from typing import List, Dict, Any
from engine.video.schemas import VideoChunk, VisualEvidence
from engine.video.frame_sampler import VideoFrameSampler
from engine.video.face_detector import FaceDetector
from engine.video.face_cropper import FaceCropper
from engine.video.tracker import FaceTracker
from engine.video.recognizer import FaceRecognizer
from engine.video.embedding_store import EmbeddingStore
from engine.video.comparator import EmbeddingComparator
from engine.video.visual_provider import VisualEvidenceProvider
from engine.video.participant_state import ParticipantVisualStateManager
from engine.video.storage import VideoStorageManager

logger = logging.getLogger("SCIE.video_engine.pipeline")

class VideoEnginePipeline:
  """Coordinates the execution of all visual analysis stages from raw chunks to visual evidence."""

  def __init__(self):
    self.sampler = VideoFrameSampler()
    self.detector = FaceDetector()
    self.cropper = FaceCropper()
    self.tracker = FaceTracker()
    self.recognizer = FaceRecognizer()
    self.emb_store = EmbeddingStore()
    self.comparator = EmbeddingComparator()
    
    self.state_manager = ParticipantVisualStateManager()
    self.storage_manager = VideoStorageManager()

  async def process_window(self, meeting_id: str, chunks: List[VideoChunk]) -> List[VisualEvidence]:
    """Processes a window of sequential video chunks through all stages of the pipeline."""
    if not chunks:
      return []

    # Sort chunks by index to preserve order
    chunks = sorted(chunks, key=lambda x: x.chunk_index)
    collected_evidences: List[VisualEvidence] = []

    try:
      # Save/update meeting info in DB
      await self.storage_manager.save_meeting_info(meeting_id, {"status": "active"})

      for chunk in chunks:
        # 1. Decode and sample frames from the chunk
        sampled_frames = self.sampler.sample_frames(chunk)
        if not sampled_frames:
          continue

        for frame_id, ts, frame in sampled_frames:
          # Log decoded frame
          await self.storage_manager.save_video_frame(meeting_id, {
              "frame_id": frame_id,
              "timestamp": ts,
              "shape": list(frame.shape) if frame is not None else None
          })

          # 2. Stage: Face Detection
          detected_faces = self.detector.detect_faces(frame, frame_id, ts)
          
          # 3. Stage: Face Tracking
          diarized_tracks = self.tracker.update(detected_faces, ts)
          
          # Maintain active track IDs to clean up expired cache keys later
          active_track_ids = [t.track_id for t in diarized_tracks]

          # Process each active face track
          for track in diarized_tracks:
            # Save historical track records
            await self.storage_manager.save_face_track(meeting_id, {
                "track_id": track.track_id,
                "frame_id": frame_id,
                "bbox": list(track.bbox),
                "visibility": track.visibility,
                "timestamp": ts
            })

            # Check if this track is currently visible
            if not track.visibility:
              continue

            # Find the detected face that corresponds to this track's bbox
            # (We match by closest bbox overlap)
            matching_face = next(
                (f for f in detected_faces if abs(f.bbox[0] - track.bbox[0]) < 0.1),
                detected_faces[0] if detected_faces else None
            )
            if not matching_face:
              continue

            # 4. Stage: Face Cropping
            cropped_face = self.cropper.crop_face(frame, matching_face)

            # 5. Stage: Face Recognition & Scheduling
            # Fetch the original/base embedding from Redis cache
            base_emb = await self.emb_store.get_cached_embedding(meeting_id, track.track_id)
            
            # Determine if we should refresh and extract a new embedding
            should_refresh = await self.emb_store.should_refresh_embedding(meeting_id, track.track_id, frame_id)
            
            if should_refresh:
              # Perform InsightFace recognition
              embedding, rec_conf = await self.recognizer.generate_embedding(cropped_face, track.track_id)
              # Save embedding to Redis
              await self.emb_store.store_embedding(meeting_id, track.track_id, embedding, frame_id)
              # Save unique embedding history to MongoDB
              await self.storage_manager.save_face_embedding(meeting_id, track.track_id, embedding, ts)
            else:
              # Use the cached embedding
              embedding = base_emb if base_emb else [0.0] * 512
              rec_conf = 0.90 # Standard confidence for cached frames

            # 6. Stage: Embedding Comparator
            # Compare current embedding against base embedding to check tracking consistency
            if base_emb:
              comparison = self.comparator.compare(embedding, base_emb)
              similarity = comparison["similarity_score"]
            else:
              # If first run, similarity is 1.0 (self comparison)
              similarity = 1.0

            # 7. Stage: Visual Evidence assembly
            evidence = VisualEvidenceProvider.assemble_evidence(
                meeting_id=meeting_id,
                track=track,
                face=matching_face,
                embedding=embedding,
                similarity=similarity,
                rec_confidence=rec_conf
            )

            # 8. Stage: Redis cache update (latest state)
            await self.state_manager.update_state(meeting_id, evidence)

            # 9. Stage: MongoDB persist visual evidence
            await self.storage_manager.save_visual_evidence(evidence)
            
            collected_evidences.append(evidence)

          # Expire cached items for tracks that have ended
          await self.emb_store.expire_tracks(meeting_id, active_track_ids)

      return collected_evidences

    except Exception as e:
      logger.error(f"Video Pipeline execution failed: {e}")
      return []
