import asyncio
import logging
from typing import Dict, List
from engine.audio.schemas import AudioChunk
from engine.audio.buffer import AudioBuffer
from engine.audio.pipeline import AudioEnginePipeline
from engine.audio.config import audio_config

logger = logging.getLogger("SCIE.audio_engine.workers")

class AudioEngineWorkerManager:
  """Manages async background worker tasks that dequeue and process audio chunks."""
  _instance = None

  def __init__(self):
    self.queue: asyncio.Queue = asyncio.Queue(maxsize=audio_config.WORKER_QUEUE_MAXSIZE)
    self.buffers: Dict[str, AudioBuffer] = {}
    self.pipeline = AudioEnginePipeline()
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
    num_workers = audio_config.WORKER_COUNT
    logger.info(f"Starting {num_workers} background audio workers...")
    
    for i in range(num_workers):
      task = asyncio.create_task(self._worker_loop(i))
      self.worker_tasks.append(task)

  async def stop(self):
    """Gracefully shuts down all workers, waiting for them to complete current processing."""
    if not self.is_running:
      return

    self.is_running = False
    logger.info("Stopping background audio workers...")
    
    # Send a None sentinel for each worker to unblock the get() call
    for _ in self.worker_tasks:
      await self.queue.put(None)
      
    # Wait for all tasks to finish with a timeout
    try:
      await asyncio.wait_for(asyncio.gather(*self.worker_tasks, return_exceptions=True), timeout=5.0)
    except asyncio.TimeoutError:
      logger.warning("Audio workers shutdown timed out. Cancelling remaining tasks.")
      for task in self.worker_tasks:
        task.cancel()
        
    self.worker_tasks.clear()
    logger.info("Audio workers shut down complete.")

  async def enqueue_chunk(self, chunk: AudioChunk):
    """Enqueues an incoming audio chunk for background processing."""
    if not self.is_running:
      self.start()
    try:
      # Use non-blocking put or wait if full
      await self.queue.put(chunk)
      logger.debug(f"Enqueued chunk {chunk.chunk_index} for meeting {chunk.meeting_id}")
    except Exception as e:
      logger.error(f"Failed to enqueue audio chunk: {e}")

  def _get_buffer(self, meeting_id: str) -> AudioBuffer:
    """Gets or creates the AudioBuffer associated with the meeting."""
    if meeting_id not in self.buffers:
      self.buffers[meeting_id] = AudioBuffer()
    return self.buffers[meeting_id]

  async def _worker_loop(self, worker_id: int):
    """Internal loop for processing chunks from the queue."""
    logger.info(f"Worker {worker_id} started.")
    
    while True:
      try:
        chunk: Optional[AudioChunk] = await self.queue.get()
        
        # Sentinel check for shutdown
        if chunk is None:
          self.queue.task_done()
          break
          
        meeting_id = chunk.meeting_id
        buffer = self._get_buffer(meeting_id)
        
        # Add chunk to reordering stream buffer
        buffer.add_chunk(chunk)
        
        # Pull any ready windows from the buffer
        # This loop pulls multiple windows if backlog was processed
        while True:
          window_chunks = buffer.get_next_window()
          if not window_chunks:
            break
            
          # Run the pipeline processing in a try/except to prevent worker crash
          try:
            await self.pipeline.process_window(meeting_id, window_chunks)
          except Exception as pipeline_err:
            logger.error(f"Worker {worker_id} pipeline error: {pipeline_err}")
            
        self.queue.task_done()
      except asyncio.CancelledError:
        break
      except Exception as e:
        logger.error(f"Worker {worker_id} encountered unexpected error: {e}")
        # Yield control to prevent CPU spin lock in case of continuous error
        await asyncio.sleep(0.1)

    logger.info(f"Worker {worker_id} stopped.")
# Reusable enqueuer helper
async def enqueue_audio_chunk(chunk: AudioChunk):
  manager = AudioEngineWorkerManager.get_instance()
  await manager.enqueue_chunk(chunk)
