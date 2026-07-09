"""
Background Async Worker Pool for the Evidence Fusion Engine (`engine/fusion/`).

Manages event-driven worker coroutines consuming from a shared `asyncio.Queue`.
Enables real-time continuous fusion updates without continuous polling or blocking upstream engines.
Includes exponential backoff retry and graceful shutdown via sentinel injection.
"""
import asyncio
from typing import List, Optional, Any
from engine.fusion.pipeline import fusion_pipeline, FusionPipeline
from engine.fusion.schemas import IncomingEvidence
from engine.fusion.config import fusion_config
from engine.fusion.logger import logger


class FusionWorkerManager:
  """Singleton async worker manager for the Evidence Fusion Engine."""

  _instance: Optional["FusionWorkerManager"] = None

  def __init__(self) -> None:
    self.queue: asyncio.Queue = asyncio.Queue(maxsize=fusion_config.WORKER_QUEUE_MAXSIZE)
    self.pipeline: FusionPipeline = fusion_pipeline
    self.worker_tasks: List[asyncio.Task] = []
    self.is_running = False

  @classmethod
  def get_instance(cls) -> "FusionWorkerManager":
    """Returns the process-wide singleton, creating it if necessary."""
    if cls._instance is None:
      cls._instance = cls()
    return cls._instance

  def start(self) -> None:
    """Starts background worker coroutines. Idempotent."""
    if self.is_running and self.worker_tasks and not all(t.done() for t in self.worker_tasks):
      logger.debug("FusionWorkerManager: Already running.")
      return

    self.is_running = True
    self.worker_tasks.clear()
    self.queue = asyncio.Queue(maxsize=fusion_config.WORKER_QUEUE_MAXSIZE)
    count = fusion_config.WORKER_COUNT
    logger.info(f"FusionWorkerManager: Starting {count} background workers.")

    for i in range(count):
      task = asyncio.create_task(
          self._worker_loop(i),
          name=f"fusion_worker_{i}"
      )
      self.worker_tasks.append(task)

  async def stop(self) -> None:
    """Stops all background worker coroutines gracefully via None sentinels."""
    if not self.is_running:
      return

    logger.info("FusionWorkerManager: Initiating graceful shutdown.")
    self.is_running = False

    for _ in self.worker_tasks:
      await self.queue.put(None)

    if self.worker_tasks:
      await asyncio.gather(*self.worker_tasks, return_exceptions=True)
    self.worker_tasks.clear()
    logger.info("FusionWorkerManager: All workers stopped.")

  async def enqueue(self, evidence: IncomingEvidence) -> None:
    """Push an IncomingEvidence item onto the processing queue."""
    if not self.is_running:
      self.start()

    try:
      self.queue.put_nowait(evidence)
    except asyncio.QueueFull:
      logger.warning("FusionWorkerManager: Queue full! Awaiting slot...")
      await self.queue.put(evidence)

  async def _worker_loop(self, worker_id: int) -> None:
    """Individual worker coroutine loop consuming items from the queue."""
    logger.debug(f"FusionWorker [{worker_id}]: Loop started.")
    while self.is_running:
      try:
        item = await self.queue.get()
        if item is None:
          logger.debug(f"FusionWorker [{worker_id}]: Received sentinel, exiting.")
          self.queue.task_done()
          break

        await self._process_with_retry(item, worker_id)
        self.queue.task_done()

      except asyncio.CancelledError:
        logger.debug(f"FusionWorker [{worker_id}]: Cancelled.")
        break
      except Exception as exc:
        logger.error(f"FusionWorker [{worker_id}]: Unexpected loop error: {exc}", exc_info=True)

  async def _process_with_retry(self, evidence: IncomingEvidence, worker_id: int) -> None:
    """Executes pipeline.process_evidence() with retry and exponential backoff."""
    retries = fusion_config.WORKER_RETRY_COUNT
    delay = fusion_config.WORKER_RETRY_DELAY_SEC

    for attempt in range(1, retries + 1):
      try:
        await self.pipeline.process_evidence(evidence)
        return
      except Exception as exc:
        if attempt == retries:
          logger.error(f"FusionWorker [{worker_id}]: Final retry ({attempt}/{retries}) failed for {evidence.evidence_id}: {exc}")
        else:
          logger.warning(
              f"FusionWorker [{worker_id}]: Attempt {attempt}/{retries} failed for {evidence.evidence_id}: {exc}. "
              f"Retrying in {delay:.1f}s..."
          )
          await asyncio.sleep(delay)
          delay *= 2.0


async def enqueue_fusion_evidence(
    evidence_obj: Any,
    source_type: str,
    participant_id: Optional[str] = None,
    track_id: Optional[str] = None,
    speaker_id: Optional[str] = None,
    score: Optional[float] = None,
    reliability: Optional[float] = None
) -> None:
  """Convenience entrypoint for publishing evidence from upstream engines to the Evidence Fusion Engine queue."""
  if isinstance(evidence_obj, IncomingEvidence):
    item = evidence_obj
  else:
    item = IncomingEvidence.from_evidence(
        evidence_obj=evidence_obj,
        source_type=source_type,
        participant_id=participant_id,
        track_id=track_id,
        speaker_id=speaker_id,
        score=score,
        reliability=reliability
    )
  manager = FusionWorkerManager.get_instance()
  await manager.enqueue(item)
