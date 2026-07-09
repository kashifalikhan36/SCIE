import os
import logging
from pathlib import Path
from typing import List, Set, Dict
from engine.video.schemas import VideoChunk
from engine.video.exceptions import VideoReaderError

logger = logging.getLogger("SCIE.video_engine.reader")

class VideoReader:
  """Discovers and reads new sequential video chunks from disk."""

  def __init__(self, base_dir: str = "temp-saved-data/meetings"):
    self.base_path = Path(base_dir)
    # Track processed chunk indices per meeting to avoid double processing
    self.processed_chunks: Dict[str, Set[int]] = {}

  def scan_meetings(self) -> List[str]:
    """Scans the storage directory to discover active meeting IDs."""
    if not self.base_path.exists():
      return []
    try:
      return [d.name for d in self.base_path.iterdir() if d.is_dir()]
    except Exception as e:
      logger.error(f"Failed to scan meetings directory: {e}")
      return []

  async def read_new_chunks(self, meeting_id: str) -> List[VideoChunk]:
    """Discovers and returns any new, unprocessed video chunks for the meeting."""
    video_dir = self.base_path / meeting_id / "video"
    if not video_dir.exists():
      return []

    if meeting_id not in self.processed_chunks:
      self.processed_chunks[meeting_id] = set()

    new_chunks: List[VideoChunk] = []

    try:
      # Find all webm video chunks
      chunk_files = list(video_dir.glob("*.webm"))
      for file_path in chunk_files:
        try:
          # Extract chunk index from filename (e.g. '000001.webm' -> 1)
          idx = int(file_path.stem)
        except ValueError:
          logger.warning(f"Skipping video file with non-integer filename: {file_path.name}")
          continue

        if idx not in self.processed_chunks[meeting_id]:
          try:
            # Read binary chunk payload
            with open(file_path, "rb") as f:
              data = f.read()

            # The timestamp is typically metadata on file creation or encoded.
            # We can use file modification time or approximate based on index.
            # In a real environment, this matches the websocket header timestamp.
            timestamp = int(file_path.stat().st_mtime * 1000)

            chunk = VideoChunk(
                meeting_id=meeting_id,
                timestamp=timestamp,
                chunk_index=idx,
                data=data,
                file_path=str(file_path)
            )
            new_chunks.append(chunk)
            self.processed_chunks[meeting_id].add(idx)
            logger.debug(f"Reader: Read new video chunk {idx} for meeting {meeting_id}")
          except Exception as read_err:
            logger.error(f"Failed to read video chunk {file_path.name}: {read_err}")

      # Sort chunks sequentially by index before returning
      new_chunks.sort(key=lambda x: x.chunk_index)
      return new_chunks

    except Exception as e:
      raise VideoReaderError(f"Error scanning video chunks for meeting {meeting_id}: {e}")
