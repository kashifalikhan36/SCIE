import asyncio
import os
import time
import json
import tempfile
import subprocess
from typing import Dict, Any, List, Optional
from pathlib import Path
import imageio_ffmpeg

from database.mongodb import get_mongo_db
from engine.fusion.logger import logger
from engine.audio.workers import enqueue_audio_chunk
from engine.video.workers import enqueue_video_chunk
from engine.audio.schemas import AudioChunk
from engine.video.schemas import VideoChunk
from schemas.interview import InterviewMetadata, ParticipantInfo, TranscriptUtterance

# In-memory status store for simplicity, could be Redis or MongoDB
PROCESSING_STATUS = {}

class OfflineVideoProcessor:
    def __init__(
        self, 
        meeting_id: str, 
        filepath: str, 
        metadata: Optional[InterviewMetadata] = None,
        participants: Optional[List[ParticipantInfo]] = None,
        transcript: Optional[List[TranscriptUtterance]] = None
    ):
        self.meeting_id = meeting_id
        self.filepath = filepath
        self.metadata = metadata
        self.participants = participants or []
        self.transcript = transcript or []
        self.logs = []
        self.start_time = time.time()
        
    async def process(self):
        try:
            self._log_info(f"Starting offline processing for {self.meeting_id}")
            await self._update_status("Initializing", 0.0)
            
            # Save metadata to db
            db = get_mongo_db()
            
            meta_dict = self.metadata.model_dump() if self.metadata else {}
            part_list = [p.model_dump() for p in self.participants]
            trans_list = [t.model_dump() for t in self.transcript]
            
            await db.meetings.update_one(
                {"meeting_id": self.meeting_id},
                {"$set": {
                    "meeting_id": self.meeting_id,
                    "extra_data": meta_dict,
                    "participants_data": part_list,
                    "transcript_data": trans_list,
                    "created_at": time.time(),
                    "status": "processing",
                    "source": "offline_upload"
                }},
                upsert=True
            )
            
            # Extract duration using ffprobe
            duration = self._get_duration()
            if not duration:
                self._log_error("Could not determine video duration.")
                await self._update_status("Error: Invalid video file", 100.0)
                return
                
            await self._update_status("Extracting Audio & Video chunks", 10.0)
            
            # Create a temporary directory for chunks
            with tempfile.TemporaryDirectory() as temp_dir:
                audio_dir = Path(temp_dir) / "audio"
                video_dir = Path(temp_dir) / "video"
                audio_dir.mkdir()
                video_dir.mkdir()
                
                ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
                # Split video into 1s chunks
                # WebM with VP8
                vid_cmd = [
                    ffmpeg_exe, "-y", "-i", self.filepath,
                    "-c:v", "libvpx", "-an", "-f", "segment",
                    "-segment_time", "1", "-segment_format", "webm",
                    "-reset_timestamps", "1",
                    str(video_dir / "%06d.webm")
                ]
                # Split audio into 0.5s chunks
                aud_cmd = [
                    ffmpeg_exe, "-y", "-i", self.filepath,
                    "-c:a", "libopus", "-vn", "-f", "segment",
                    "-segment_time", "0.5", "-segment_format", "webm",
                    "-reset_timestamps", "1",
                    str(audio_dir / "%06d.webm")
                ]
                kwargs = {}
                if os.name == 'nt':
                    kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
                
                self._log_info(f"[{self.meeting_id}] Running ffmpeg for video chunks...")
                await asyncio.to_thread(
                    subprocess.run,
                    vid_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True,
                    **kwargs
                )
                
                self._log_info(f"[{self.meeting_id}] Running ffmpeg for audio chunks...")
                await asyncio.to_thread(
                    subprocess.run,
                    aud_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True,
                    **kwargs
                )
                
                await self._update_status("Processing Chunks in Pipelines", 30.0)
                
                # Read chunks and push them
                audio_files = sorted(list(audio_dir.glob("*.webm")))
                video_files = sorted(list(video_dir.glob("*.webm")))
                
                total_files = len(audio_files) + len(video_files)
                processed_files = 0
                
                start_ts = int(time.time() * 1000)
                
                for idx, af in enumerate(audio_files):
                    with open(af, "rb") as f:
                        data = f.read()
                    chunk = AudioChunk(
                        meeting_id=self.meeting_id,
                        timestamp=start_ts + int(idx * 500),
                        chunk_index=idx,
                        data=data,
                        file_path=str(af),
                        chunk_type="audio"
                    )
                    await enqueue_audio_chunk(chunk)
                    processed_files += 1
                    await self._update_status("Processing Audio", 30.0 + (processed_files / total_files) * 60.0)
                    await asyncio.sleep(0.01) # Yield to event loop
                    
                for idx, vf in enumerate(video_files):
                    with open(vf, "rb") as f:
                        data = f.read()
                    chunk = VideoChunk(
                        meeting_id=self.meeting_id,
                        timestamp=start_ts + int(idx * 1000),
                        chunk_index=idx,
                        data=data,
                        file_path=str(vf)
                    )
                    await enqueue_video_chunk(chunk)
                    processed_files += 1
                    await self._update_status("Processing Video", 30.0 + (processed_files / total_files) * 60.0)
                    await asyncio.sleep(0.01)
                
            await self._update_status("Finalizing Engines", 95.0)
            # Give engines a bit of time to flush their queues
            await asyncio.sleep(10)
            
            # Generate GPT-5.5 Reasoning Report
            await self._update_status("Generating Reasoning Report", 97.0)
            from engine.reasoning.pipeline import reasoning_pipeline
            await reasoning_pipeline.generate_reasoning(self.meeting_id)
            
            db = get_mongo_db()
            await db.meetings.update_one(
                {"meeting_id": self.meeting_id},
                {"$set": {"status": "completed"}}
            )
                
            await self._update_status("Completed", 100.0)
            self._log_success("Completed processing successfully!")
            self._log_info(f"Finished offline processing for {self.meeting_id}")
            
        except subprocess.CalledProcessError as e:
            err_output = e.stderr.decode('utf-8', errors='ignore') if e.stderr else "No stderr"
            self._log_error(f"FFmpeg failed with {e.returncode}: {err_output}")
            await self._update_status(f"Error: FFmpeg failed", 100.0)
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            self._log_error(f"Error processing offline video {self.meeting_id}: {e}\n{tb}")
            await self._update_status(f"Error: {str(e) or type(e).__name__}", 100.0)
            
    def _log_info(self, msg: str):
        logger.info(msg)
        self.logs.append(f"[INFO] {msg}")

    def _log_error(self, msg: str):
        logger.error(msg)
        self.logs.append(f"[ERROR] {msg}")

    def _log_success(self, msg: str):
        logger.info(msg)
        self.logs.append(f"[SUCCESS] {msg}")

    async def _update_status(self, status: str, progress: float):
        from database.redis import get_redis
        redis_client = await get_redis()
        
        elapsed = time.time() - self.start_time
        if progress > 0 and progress < 100:
            total_est = (elapsed / progress) * 100
            rem_sec = max(0, total_est - elapsed)
            mins = int(rem_sec // 60)
            secs = int(rem_sec % 60)
            est_str = f"{mins}m {secs}s"
        elif progress >= 100:
            est_str = "0m 0s"
        else:
            est_str = "Calculating..."
            
        data = {
            "status": status,
            "progress": progress,
            "estimated_time_remaining": est_str,
            "logs": self.logs[-50:], # keep last 50
            "stats": {
                "faces_detected": 0, # Could be fetched from DB in a real impl
                "speakers_detected": 0,
                "evidence_count": 0,
                "confidence": 0
            },
            "updated_at": time.time()
        }
        await redis_client.set(f"offline_status:{self.meeting_id}", json.dumps(data), ex=3600)
        
    def _get_duration(self) -> float:
        import imageio_ffmpeg
        import re
        try:
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            cmd = [ffmpeg_exe, "-i", os.path.abspath(self.filepath)]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            match = re.search(r"Duration: (\d{2}):(\d{2}):(\d{2}\.\d+)", result.stderr)
            if match:
                hours, minutes, seconds = map(float, match.groups())
                return hours * 3600 + minutes * 60 + seconds
            return 0.0
        except Exception as e:
            logger.error(f"Error getting duration: {e}")
            return 0.0
