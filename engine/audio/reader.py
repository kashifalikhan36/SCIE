import os
import logging
from pathlib import Path
from typing import Dict, List, Set, Tuple
from core.config import settings
from engine.audio.schemas import AudioChunk
from engine.audio.exceptions import AudioReaderError

logger = logging.getLogger("SCIE.audio_engine.reader")

class AudioReader:
  """Monitors the temp-saved-data directory for new audio chunks across multiple meetings."""
  
  def __init__(self, base_dir: str = settings.SAVE_DIR):
    self.base_dir = Path(base_dir)
    self.meetings_dir = self.base_dir / "meetings"
    # Keep track of processed chunk indices per meeting: {meeting_id: {1, 2, 3}}
    self._processed_indices: Dict[str, Set[int]] = {}

  def discover_active_meetings(self) -> List[str]:
    """Finds all active meeting directories in temp-saved-data/meetings/."""
    if not self.meetings_dir.exists():
      return []
    try:
      return [
          d.name for d in self.meetings_dir.iterdir() 
          if d.is_dir() and (d / "audio").exists()
      ]
    except Exception as e:
      logger.error(f"Error discovering active meetings: {e}")
      return []

  def get_new_chunks(self, meeting_id: str) -> List[AudioChunk]:
    """Scans the audio directory for a meeting and returns any newly arrived chunks."""
    audio_dir = self.meetings_dir / meeting_id / "audio"
    if not audio_dir.exists():
      return []

    if meeting_id not in self._processed_indices:
      self._processed_indices[meeting_id] = set()

    processed = self._processed_indices[meeting_id]
    new_chunks: List[AudioChunk] = []

    try:
      # Find all webm files in the audio folder
      audio_files = list(audio_dir.glob("*.webm"))
      
      # Parse filenames to find chunk indices
      parsed_files: List[Tuple[int, Path]] = []
      for file_path in audio_files:
        try:
          index = int(file_path.stem)
          parsed_files.append((index, file_path))
        except ValueError:
          # Ignore malformed filenames that aren't digits
          continue
      
      # Sort sequentially by chunk index
      parsed_files.sort(key=lambda x: x[0])

      for index, file_path in parsed_files:
        if index not in processed:
          try:
            # Read chunk binary data
            with open(file_path, "rb") as f:
              data = f.read()
              
            # Get file modification time as approximate timestamp if needed
            timestamp = int(file_path.stat().st_mtime * 1000)

            chunk = AudioChunk(
                meeting_id=meeting_id,
                timestamp=timestamp,
                chunk_index=index,
                data=data,
                file_path=str(file_path)
            )
            new_chunks.append(chunk)
            
            # Mark as processed
            processed.add(index)
            logger.info(f"Detected new chunk {index:06d}.webm for meeting {meeting_id}")
          except IOError as e:
            # Skip reading for now if file is locked (currently being written)
            logger.debug(f"Chunk file {file_path.name} is locked/unreadable: {e}")
            continue

    except Exception as e:
      raise AudioReaderError(f"Failed to scan audio chunks for meeting {meeting_id}: {e}")

    return new_chunks

  def clear_processed_cache(self, meeting_id: str):
    """Resets the processed chunk cache for a meeting (useful if restarting stream)."""
    if meeting_id in self._processed_indices:
      self._processed_indices[meeting_id].clear()
      logger.info(f"Cleared chunk cache for meeting {meeting_id}")
