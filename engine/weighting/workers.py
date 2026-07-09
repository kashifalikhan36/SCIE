"""
Async Event-Driven Background Workers for the Dynamic Weighting Engine.

Manages a pool of worker coroutines processing incoming weighting jobs from an
``asyncio.Queue`` with automatic retry and exponential backoff.

(`engine/weighting/workers.py`)
"""
import asyncio
from typing import Dict, Any, Optional, List
from engine.weighting.schemas import EvidencePayloads, DynamicWeightProfile
from engine.weighting.pipeline import WeightingPipeline
from engine.weighting.config import weighting_config
from engine.weighting.logger import logger

_worker_manager: Optional["WeightingWorkerManager"] = None


class WeightingWorkerManager:
  """Pool of async background workers consuming weighting evaluation tasks."""

  def __init__(self, worker_count: int = weighting_config.WORKER_COUNT, pipeline: Optional[WeightingPipeline] = None):
    self.worker_count = worker_count
    self.pipeline = pipeline or WeightingPipeline()
    self.queue: asyncio.Queue = asyncio.Queue(maxsize=weighting_config.WORKER_QUEUE_MAXSIZE)
    self.workers: List[asyncio.Task] = []
    self.is_running = False

  async def start(self):
    """Start the background async worker coroutines."""
    if self.is_running:
      return
    self.is_running = True
    self.workers = [
        asyncio.create_task(self._worker_loop(i), name=f"WeightingWorker-{i}")
        for i in range(self.worker_count)
    ]
    logger.info(f"Started WeightingWorkerManager with {self.worker_count} workers")

  async def stop(self):
    """Gracefully stop background worker coroutines and drain remaining tasks."""
    if not self.is_running:
      return
    await self.queue.join()
    self.is_running = False
    for w in self.workers:
      w.cancel()
    await asyncio.gather(*self.workers, return_exceptions=True)
    self.workers.clear()
    logger.info("Stopped WeightingWorkerManager and drained worker queue")

  async def enqueue_job(
      self,
      meeting_id: str,
      participant_id: str,
      payloads: Optional[EvidencePayloads] = None,
      elapsed_meeting_sec: float = 0.0,
      meeting_tags: Optional[List[str]] = None,
      force_recompute: bool = False
  ) -> bool:
    """Enqueue a weighting evaluation job onto the async worker pool queue."""
    job = {
        "meeting_id": meeting_id,
        "participant_id": participant_id,
        "payloads": payloads,
        "elapsed_meeting_sec": elapsed_meeting_sec,
        "meeting_tags": meeting_tags,
        "force_recompute": force_recompute,
    }
    try:
      self.queue.put_nowait(job)
      return True
    except asyncio.QueueFull:
      logger.warning(f"WeightingWorkerManager queue full! Dropping task for {participant_id}")
      return False

  async def _worker_loop(self, worker_id: int):
    """Main execution loop for an individual background worker coroutine."""
    while self.is_running:
      try:
        job = await self.queue.get()
      except asyncio.CancelledError:
        break

      try:
        await self._process_job_with_retry(job)
      except Exception as e:
        logger.error(f"Worker {worker_id} encountered unhandled exception: {e}", exc_info=True)
      finally:
        self.queue.task_done()

  async def _process_job_with_retry(self, job: Dict[str, Any]):
    """Execute evaluation job with automatic exponential backoff retries."""
    attempts = 0
    max_retries = weighting_config.WORKER_RETRY_COUNT
    delay = weighting_config.WORKER_RETRY_DELAY_SEC

    while attempts <= max_retries:
      try:
        await self.pipeline.process_participant(
            meeting_id=job["meeting_id"],
            participant_id=job["participant_id"],
            payloads=job.get("payloads"),
            elapsed_meeting_sec=job.get("elapsed_meeting_sec", 0.0),
            meeting_tags=job.get("meeting_tags"),
            force_recompute=job.get("force_recompute", False)
        )
        return
      except Exception as e:
        attempts += 1
        if attempts > max_retries:
          logger.error(f"Failed to process weighting job after {max_retries} attempts: {e}")
          break
        logger.warning(f"Weighting job failed (attempt {attempts}/{max_retries}), retrying in {delay}s: {e}")
        await asyncio.sleep(delay)
        delay *= 2.0


def get_worker_manager() -> WeightingWorkerManager:
  """Retrieve or initialize the global singleton WeightingWorkerManager."""
  global _worker_manager
  if _worker_manager is None:
    _worker_manager = WeightingWorkerManager()
  return _worker_manager


async def enqueue_weighting_job(
    meeting_id: str,
    participant_id: str,
    payloads: Optional[EvidencePayloads] = None,
    elapsed_meeting_sec: float = 0.0,
    meeting_tags: Optional[List[str]] = None,
    force_recompute: bool = False
) -> bool:
  """Module entrypoint wrapper to enqueue a weighting job on the global worker pool."""
  wm = get_worker_manager()
  return await wm.enqueue_job(
      meeting_id=meeting_id,
      participant_id=participant_id,
      payloads=payloads,
      elapsed_meeting_sec=elapsed_meeting_sec,
      meeting_tags=meeting_tags,
      force_recompute=force_recompute
  )
