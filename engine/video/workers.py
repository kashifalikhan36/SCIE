import asyncio
import logging
from typing import Dict, List, Optional
from engine.video.schemas import VideoChunk
from engine.video.frame_buffer import VideoFrameBuffer
from engine.video.pipeline import VideoEnginePipeline
from engine.video.config import video_config

logger = logging.getLogger("SCIE.video_engine.workers")

class VideoEngineWorkerManager:
  """Manages background async worker tasks that dequeue and process video chunks."""
  _instance = None

  def __init__(self):
    self.queue: asyncio.Queue = asyncio.Queue(maxsize=video_config.WORKER_QUEUE_MAXSIZE)
    self.buffers: Dict[str, VideoFrameBuffer] = {}
    self.pipeline = VideoEnginePipeline()
    self.worker_tasks: List[asyncio.Task] = []
    self.is_running = False

  @classmethod
  def get_instance(cls):
    if cls._instance is None:
      cls._instance = cls()
    return cls._instance

  def start(self):
    """Starts the background worker tasks."""
    if self.is_running:
      return
      
    self.is_running = True
    num_workers = video_config.WORKER_COUNT
    logger.info(f"Starting {num_workers} background video workers...")
    
    for i in range(num_workers):
      task = asyncio.create_task(self._worker_loop(i))
      self.worker_tasks.append(task)

  async def stop(self):
    """Gracefully shuts down all workers, waiting for current processing to complete."""
    if not self.is_running:
      return

    self.is_running = False
    logger.info("Stopping background video workers...")
    
    # Send None sentinel to unblock workers
    for _ in self.worker_tasks:
      await self.queue.put(None)

    try:
      await asyncio.wait_for(asyncio.gather(*self.worker_tasks, return_exceptions=True), timeout=5.0)
    except asyncio.TimeoutError:
      logger.warning("Video workers shutdown timed out. Cancelling remaining tasks.")
      for task in self.worker_tasks:
        task.cancel()

    self.worker_tasks.clear()
    logger.info("Video workers shut down complete.")

  async def enqueue_chunk(self, chunk: VideoChunk):
    """Enqueues an incoming video chunk for background processing."""
    if not self.is_running:
      self.start()
    try:
      await self.queue.put(chunk)
      logger.debug(f"Enqueued video chunk {chunk.chunk_index} for meeting {chunk.meeting_id}")
    except Exception as e:
      logger.error(f"Failed to enqueue video chunk: {e}")

  def _get_buffer(self, meeting_id: str) -> VideoFrameBuffer:
    """Gets or creates the VideoFrameBuffer associated with the meeting."""
    if meeting_id not in self.buffers:
      self.buffers[meeting_id] = VideoFrameBuffer()
    return self.buffers[meeting_id]

  async def _worker_loop(self, worker_id: int):
    """Internal loop processing chunk tasks from the queue."""
    logger.info(f"Video Worker {worker_id} started.")
    
    while True:
      try:
        chunk: Optional[VideoChunk] = await self.queue.get()
        if chunk is None:
          self.queue.task_done()
          break
          
        meeting_id = chunk.meeting_id
        buffer = self._get_buffer(meeting_id)
        
        # Add chunk to stream buffer
        buffer.add_chunk(chunk)
        
        # Pull any ready windows from the buffer
        while True:
          window_chunks = buffer.get_next_window()
          if not window_chunks:
            break
            
          try:
            await self.pipeline.process_window(meeting_id, window_chunks)
          except Exception as pipeline_err:
            logger.error(f"Video Worker {worker_id} pipeline error: {pipeline_err}")

        self.queue.task_done()
      except asyncio.CancelledError:
        break
      except Exception as e:
        logger.error(f"Video Worker {worker_id} encountered unexpected error: {e}")
        await asyncio.sleep(0.1)

    logger.info(f"Video Worker {worker_id} stopped.")

# Reusable enqueuer helper
async def enqueue_video_chunk(chunk: VideoChunk):
  manager = VideoEngineWorkerManager.get_instance()
  await manager.enqueue_chunk(chunk)
