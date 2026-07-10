import asyncio
import logging
from typing import List, Optional

from engine.identity.pipeline import IdentityPipeline
from engine.identity.config import identity_config
from engine.identity.schemas import MeetingMetadata, ParticipantMetadata

logger = logging.getLogger("SCIE.identity_engine.workers")


class IdentityWorkerManager:
  """Manages background async worker coroutines for the Identity Engine.

  Architecture:
  - Shared asyncio.Queue across WORKER_COUNT coroutines.
  - Graceful shutdown via None sentinel injection.
  - Exponential backoff retry policy on transient failures.
  - Process-wide singleton via get_instance().
  - Loop-resilient start: detects stale tasks and re-creates workers safely.
  """

  _instance: Optional["IdentityWorkerManager"] = None

  def __init__(self) -> None:
    self.queue: asyncio.Queue = asyncio.Queue(
        maxsize=identity_config.WORKER_QUEUE_MAXSIZE
    )
    self.pipeline = IdentityPipeline()
    self.worker_tasks: List[asyncio.Task] = []
    self.is_running = False

  @classmethod
  def get_instance(cls) -> "IdentityWorkerManager":
    """Returns the process-wide singleton, creating it if necessary."""
    if cls._instance is None:
      cls._instance = cls()
    return cls._instance

  def start(self) -> None:
    """Starts background worker coroutines.

    Idempotent: calling start() when workers are already running is a no-op.
    """
    if self.is_running and self.worker_tasks and not all(t.done() for t in self.worker_tasks):
      logger.debug("IdentityWorkerManager: Already running.")
      return

    self.is_running = True
    self.worker_tasks.clear()
    self.queue = asyncio.Queue(maxsize=identity_config.WORKER_QUEUE_MAXSIZE)
    count = identity_config.WORKER_COUNT
    logger.info(f"IdentityWorkerManager: Starting {count} background workers.")

    for i in range(count):
      task = asyncio.create_task(
          self._worker_loop(i),
          name=f"identity_worker_{i}",
      )
      self.worker_tasks.append(task)

  async def stop(self) -> None:
    """Gracefully shuts down all background workers.

    Injects None sentinel items to unblock each worker's queue.get().
    Waits up to 5 seconds before force-cancelling.
    """
    if not self.is_running:
      return

    self.is_running = False
    logger.info("IdentityWorkerManager: Stopping workers...")

    for _ in self.worker_tasks:
      await self.queue.put(None)

    try:
      await asyncio.wait_for(
          asyncio.gather(*self.worker_tasks, return_exceptions=True),
          timeout=5.0,
      )
    except asyncio.TimeoutError:
      logger.warning("IdentityWorkerManager: Shutdown timed out — force-cancelling tasks.")
      for task in self.worker_tasks:
        task.cancel()

    self.worker_tasks.clear()
    logger.info("IdentityWorkerManager: All workers stopped.")

  async def enqueue(
      self,
      meeting_metadata: MeetingMetadata,
      participant_metadata: ParticipantMetadata,
  ) -> None:
    """Enqueues an identity processing request.

    Args:
        meeting_metadata: Meeting-level metadata with candidate profile.
        participant_metadata: Observed participant metadata.
    """
    if not self.is_running:
      logger.warning("IdentityWorkerManager: Auto-starting workers on first enqueue.")
      self.start()
    try:
      await self.queue.put((meeting_metadata, participant_metadata))
      logger.debug(
          f"IdentityWorkerManager: Enqueued identity request for "
          f"participant={participant_metadata.participant_id}"
      )
    except Exception as exc:
      logger.error(f"IdentityWorkerManager: Failed to enqueue request: {exc}")

  async def _worker_loop(self, worker_id: int) -> None:
    """Background coroutine that consumes and processes identity requests.

    Args:
        worker_id: Zero-indexed worker identifier (for logging).
    """
    logger.info(f"IdentityWorker[{worker_id}]: Started.")

    while True:
      try:
        task_data = await self.queue.get()
        if task_data is None:
          self.queue.task_done()
          break

        meeting_metadata, participant_metadata = task_data
        success = False

        for attempt in range(identity_config.WORKER_RETRY_COUNT):
          try:
            evidence = await self.pipeline.process(meeting_metadata, participant_metadata)
            if evidence:
                try:
                    from engine.fusion.workers import enqueue_fusion_evidence
                    from engine.fusion.constants import DOMAIN_IDENTITY
                    await enqueue_fusion_evidence(
                        evidence_obj=evidence,
                        source_type=DOMAIN_IDENTITY,
                        participant_id=evidence.participant_id,
                        score=evidence.overall_identity_score,
                        reliability=evidence.confidence
                    )
                except Exception as fe:
                    logger.error(f"IdentityWorker[{worker_id}]: Failed to enqueue to FusionEngine: {fe}")
            success = True
            break
          except Exception as exc:
            delay = identity_config.WORKER_RETRY_DELAY_SEC * (2 ** attempt)
            logger.error(
                f"IdentityWorker[{worker_id}]: Error on attempt "
                f"{attempt + 1}/{identity_config.WORKER_RETRY_COUNT}: {exc}. "
                f"Retrying in {delay:.1f}s..."
            )
            await asyncio.sleep(delay)

        if not success:
          logger.error(
              f"IdentityWorker[{worker_id}]: Dropped request for participant="
              f"{participant_metadata.participant_id} after "
              f"{identity_config.WORKER_RETRY_COUNT} attempts."
          )

        self.queue.task_done()

      except asyncio.CancelledError:
        logger.info(f"IdentityWorker[{worker_id}]: Cancelled.")
        break
      except Exception as exc:
        logger.error(f"IdentityWorker[{worker_id}]: Unexpected error: {exc}")
        await asyncio.sleep(0.1)

    logger.info(f"IdentityWorker[{worker_id}]: Stopped.")


async def enqueue_identity_request(
    meeting_metadata: MeetingMetadata,
    participant_metadata: ParticipantMetadata,
) -> None:
  """Convenience helper for enqueuing identity processing requests.

  Args:
      meeting_metadata: Meeting-level metadata with candidate profile.
      participant_metadata: Observed participant metadata.
  """
  manager = IdentityWorkerManager.get_instance()
  await manager.enqueue(meeting_metadata, participant_metadata)
