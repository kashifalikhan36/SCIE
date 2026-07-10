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
from engine.audio.schemas import AudioChunk
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
        transcript: Optional[List[TranscriptUtterance]] = None,
        raw_metadata: Optional[Dict[str, Any]] = None,  # raw dict before Pydantic parsing
    ):
        self.meeting_id = meeting_id
        self.filepath = filepath
        self.metadata = metadata
        self.participants = participants or []
        self.transcript = transcript or []
        self.raw_metadata = raw_metadata or {}  # preserves all fields incl. "candidate"
        self.logs = []
        self.start_time = time.time()
        
    async def process(self):
        try:
            self._log_info(f"Starting offline processing for {self.meeting_id}")
            await self._update_status("Initializing", 0.0)
            
            db = get_mongo_db()
            
            # Preserve the raw metadata dict — this retains all fields the upload form sent
            # (e.g., "candidate", "candidate_email", "interviewers") without Pydantic filtering them out.
            meta_dict = self.metadata.model_dump() if self.metadata else {}
            part_list = [p.model_dump() for p in self.participants]
            trans_list = [t.model_dump() for t in self.transcript]
            
            # Extract flat candidate name — check raw dict first, then Pydantic fields
            candidate_name = (
                self.raw_metadata.get("candidate")
                or self.raw_metadata.get("candidate_name")
                or (meta_dict.get("external_metadata") or {}).get("candidate_name")
                or meta_dict.get("extra", {}).get("candidate")
            )
            candidate_email = (
                self.raw_metadata.get("candidate_email")
                or (meta_dict.get("external_metadata") or {}).get("candidate_email")
            )
            interviewers = (
                self.raw_metadata.get("interviewers", [])
                or (meta_dict.get("external_metadata") or {}).get("interviewer_names", [])
            )
            
            await db.meetings.update_one(
                {"meeting_id": self.meeting_id},
                {"$set": {
                    "meeting_id": self.meeting_id,
                    # Store both the Pydantic dump AND the raw dict so nothing is lost
                    "extra_data": {
                        **meta_dict,
                        **self.raw_metadata,         # raw dict overlays Pydantic result
                        "candidate": candidate_name, # flat top-level field for UI
                        "candidate_email": candidate_email,
                        "interviewers": interviewers,
                    },
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
                
            await self._update_status("Extracting audio (fast mode)", 10.0)
            
            # Create a temporary directory for chunks
            with tempfile.TemporaryDirectory() as temp_dir:
                audio_dir = Path(temp_dir) / "audio"
                audio_dir.mkdir()
                
                ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
                
                # ── Audio only: fast Opus re-encode into 30s segments ──
                # libopus is fast; 39min → ~79 segments, done in ~5s.
                aud_cmd = [
                    ffmpeg_exe, "-y", "-i", self.filepath,
                    "-vn",                         # drop video stream
                    "-c:a", "libopus",
                    "-b:a", "64k",
                    "-f", "segment",
                    "-segment_time", "30",          # 30s chunks
                    "-segment_format", "webm",
                    "-reset_timestamps", "1",
                    str(audio_dir / "%06d.webm")
                ]
                
                kwargs = {}
                if os.name == 'nt':
                    kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
                
                self._log_info(f"[{self.meeting_id}] Extracting audio chunks (30s segments)...")
                await self._update_status("Extracting audio segments", 15.0)
                await asyncio.to_thread(
                    subprocess.run,
                    aud_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True,
                    **kwargs
                )
                
                audio_files = sorted(list(audio_dir.glob("*.webm")))
                total_audio = len(audio_files)
                self._log_info(f"[{self.meeting_id}] Extracted {total_audio} audio segments.")
                
                await self._update_status("Processing Audio through AI Pipeline", 30.0)
                
                start_ts = int(time.time() * 1000)
                
                # Enqueue audio chunks (30s each)
                for idx, af in enumerate(audio_files):
                    with open(af, "rb") as f:
                        data = f.read()
                    chunk = AudioChunk(
                        meeting_id=self.meeting_id,
                        timestamp=start_ts + int(idx * 30000),  # 30s per chunk
                        chunk_index=idx,
                        data=data,
                        file_path=str(af),
                        chunk_type="audio"
                    )
                    await enqueue_audio_chunk(chunk)
                    progress = 30.0 + ((idx + 1) / total_audio) * 50.0
                    await self._update_status(
                        f"Queued audio segment {idx+1}/{total_audio}",
                        progress
                    )
                    self._log_info(f"[{self.meeting_id}] Queued audio segment {idx+1}/{total_audio}")
                    await asyncio.sleep(0.05)  # Yield to event loop
                
            # ── Candidate Identification (Sherlock Identity Engine) ──
            await self._update_status("Running Candidate Identification", 82.0)
            await self._run_identity_pipeline(candidate_name, candidate_email, interviewers)

            await self._update_status("Finalizing Engines", 90.0)
            # Give audio workers time to flush their queues
            await asyncio.sleep(10)
            
            # ── Generate Reasoning Report ──
            await self._update_status("Generating Analysis Report", 96.0)
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

    async def _run_identity_pipeline(
        self,
        candidate_name: Optional[str],
        candidate_email: Optional[str],
        interviewers: List[str],
    ):
        """Run the Sherlock Identity Engine against all known and auto-detected participants."""
        if not candidate_name:
            self._log_info(f"[{self.meeting_id}] Identity pipeline skipped — no candidate name provided.")
            return

        try:
            from engine.identity.pipeline import IdentityPipeline
            from engine.identity.schemas import MeetingMetadata, ParticipantMetadata

            identity_pipeline = IdentityPipeline()

            meeting_meta = MeetingMetadata(
                meeting_id=self.meeting_id,
                candidate_name=candidate_name,
                candidate_email=candidate_email,
                interviewer_names=interviewers,
            )

            # ── Collect participants to evaluate ──
            # 1. Registered participants from upload form (may be empty now)
            participants_to_check: List[ParticipantMetadata] = []
            for p in self.participants:
                participants_to_check.append(ParticipantMetadata(
                    participant_id=p.participant_id,
                    display_name=p.display_name,
                ))

            # 2. Auto-detected speakers from the audio diarization pipeline
            db = get_mongo_db()
            diarized_speakers = await db.transcript_segments.distinct(
                "speaker_id", {"meeting_id": self.meeting_id}
            )
            for speaker_id in diarized_speakers:
                # Only add if not already in the list
                existing_ids = {p.participant_id for p in participants_to_check}
                if speaker_id not in existing_ids:
                    # Get any transcript text for this speaker to use as display name hint
                    sample = await db.transcript_segments.find_one(
                        {"meeting_id": self.meeting_id, "speaker_id": speaker_id}
                    )
                    participants_to_check.append(ParticipantMetadata(
                        participant_id=speaker_id,
                        display_name=speaker_id,  # e.g. "SPEAKER_00"
                        extra_metadata={
                            "auto_detected": True,
                            "sample_text": (sample or {}).get("text", "")
                        }
                    ))

            if not participants_to_check:
                # No participants yet — synthesize placeholders so identity pipeline still runs
                # (they'll be enriched later as diarization completes)
                self._log_info(f"[{self.meeting_id}] No participants yet — creating placeholder for candidate.")
                participants_to_check.append(ParticipantMetadata(
                    participant_id="candidate_placeholder",
                    display_name=candidate_name,
                ))

            self._log_info(f"[{self.meeting_id}] Running identity pipeline for {len(participants_to_check)} participant(s)...")

            best_match = None
            best_score = 0.0

            for participant in participants_to_check:
                evidence = await identity_pipeline.process(meeting_meta, participant)
                if evidence:
                    score = evidence.overall_identity_score
                    self._log_info(
                        f"[{self.meeting_id}] Identity: {participant.participant_id} → "
                        f"score={score:.3f}, conf={evidence.confidence:.3f}"
                    )
                    if score > best_score:
                        best_score = score
                        best_match = (participant.participant_id, participant.display_name, score, evidence.confidence)

            if best_match:
                pid, pname, score, conf = best_match
                self._log_success(
                    f"[{self.meeting_id}] Sherlock identified candidate: '{pname}' "
                    f"as '{candidate_name}' (score={score:.2f}, conf={conf:.2f})"
                )
                # Store the identification result in the meeting document
                await db.meetings.update_one(
                    {"meeting_id": self.meeting_id},
                    {"$set": {
                        "identity_result": {
                            "identified_participant_id": pid,
                            "identified_display_name": pname,
                            "candidate_name": candidate_name,
                            "score": score,
                            "confidence": conf,
                        }
                    }}
                )
            else:
                self._log_info(f"[{self.meeting_id}] Identity pipeline: no high-confidence match found.")

        except Exception as e:
            import traceback
            self._log_error(f"Identity pipeline error: {e}\n{traceback.format_exc()}")

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
            "logs": self.logs[-50:],  # keep last 50 log entries
            "stats": {
                "faces_detected": 0,
                "speakers_detected": 0,
                "evidence_count": 0,
                "confidence": 0
            },
            "updated_at": time.time()
        }
        await redis_client.set(f"offline_status:{self.meeting_id}", json.dumps(data), ex=3600)
        
    def _get_duration(self) -> float:
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
