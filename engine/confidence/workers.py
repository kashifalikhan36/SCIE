"""
Event-Driven Async Background Workers for the SCIE Confidence Engine (`engine/confidence/workers.py`).

Provides an asynchronous worker pool (`ConfidenceWorkerManager`) processing evidence jobs from an
`asyncio.Queue` (`WORKER_QUEUE_MAXSIZE`) with automatic exponential backoff retries (`WORKER_RETRY_COUNT`).
Ensures zero race conditions and clean queue drainage upon termination (`stop()`).
"""
import asyncio
from typing import Dict, List, Optional, Any, Union
from engine.confidence.config import confidence_config
from engine.confidence.schemas import Evidence, ConfidenceResult
from engine.confidence.pipeline import ConfidencePipeline
from engine.confidence.logger import logger, measure_latency


class ConfidenceWorkerManager:
  """Manages concurrent background worker coroutines processing confidence evaluation jobs."""

  def __init__(self, worker_count: int = confidence_config.WORKER_COUNT, pipeline: Optional[ConfidencePipeline] = None):
    self.worker_count = worker_count
    self.pipeline = pipeline or ConfidencePipeline()
    self.queue: asyncio.Queue = asyncio.Queue(maxsize=confidence_config.WORKER_QUEUE_MAXSIZE)
    self.workers: List[asyncio.Task] = []
    self.is_running = False

  async def start(self) -> None:
    """Start background async worker coroutines."""
    if self.is_running:
      return
    self.is_running = True
    self.workers = [
        asyncio.create_task(self._worker_loop(i), name=f"ConfidenceWorker-{i}")
        for i in range(self.worker_count)
    ]
    logger.info(f"Started ConfidenceWorkerManager with {self.worker_count} workers")

  async def stop(self) -> None:
    """Gracefully stop background worker coroutines and drain remaining queue tasks first."""
    if not self.is_running:
      return
    # Drain remaining tasks before marking is_running = False so workers don't abort midway
    await self.queue.join()
    self.is_running = False
    for w in self.workers:
      w.cancel()
    await asyncio.gather(*self.workers, return_exceptions=True)
    self.workers.clear()
    logger.info("Stopped ConfidenceWorkerManager and drained worker queue")

  async def enqueue_evidence_job(
      self,
      meeting_id: str,
      raw_evidence: Union[Evidence, Dict[str, Any]],
      calculation_strategy: Optional[str] = None
  ) -> bool:
    """Enqueue an incoming evidence evaluation task into the background worker queue."""
    if not self.is_running:
      logger.warning("ConfidenceWorkerManager is not running; starting automatically")
      await self.start()

    job = {
        "meeting_id": meeting_id,
        "raw_evidence": raw_evidence,
        "calculation_strategy": calculation_strategy,
        "attempts": 0
    }

    try:
      self.queue.put_nowait(job)
      logger.debug(f"Enqueued confidence job for meeting {meeting_id}")
      return True
    except asyncio.QueueFull:
      logger.error(f"Worker queue full ({confidence_config.WORKER_QUEUE_MAXSIZE}); dropping confidence job for {meeting_id}")
      return False

  async def _worker_loop(self, worker_id: int) -> None:
    while self.is_running:
      try:
        job = await self.queue.get()
      except asyncio.CancelledError:
        break

      try:
        await self._process_job_with_retry(job)
      except Exception as e:
        logger.error(f"Worker {worker_id} encountered unhandled exception processing job: {e}", exc_info=True)
      finally:
        self.queue.task_done()

  async def _process_job_with_retry(self, job: Dict[str, Any]) -> Optional[ConfidenceResult]:
    max_retries = confidence_config.WORKER_RETRY_COUNT
    meeting_id = job["meeting_id"]
    raw_ev = job["raw_evidence"]
    strat = job["calculation_strategy"]

    while job["attempts"] <= max_retries:
      job["attempts"] += 1
      try:
        res = await self.pipeline.process_evidence(meeting_id, raw_ev, calculation_strategy=strat)
        return res
      except Exception as e:
        if job["attempts"] > max_retries:
          logger.error(f"Confidence job for meeting {meeting_id} failed permanently after {max_retries} attempts: {e}")
          return None
        delay = 0.1 * (2 ** (job["attempts"] - 1))
        logger.warning(f"Confidence job failed ({e}); retrying in {delay:.2f}s (Attempt {job['attempts']}/{max_retries})")
        await asyncio.sleep(delay)
    return None


# Global singleton instance
_worker_manager: Optional[ConfidenceWorkerManager] = None


def get_confidence_worker_manager() -> ConfidenceWorkerManager:
  """Get or create the global `ConfidenceWorkerManager` singleton."""
  global _worker_manager
  if _worker_manager is None:
    _worker_manager = ConfidenceWorkerManager()
  return _worker_manager
