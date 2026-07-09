import asyncio
import logging
from typing import List, Optional, Any

from engine.association.pipeline import ParticipantAssociationPipeline
from engine.association.config import association_config
from engine.association.schemas import MeetingMetadata

logger = logging.getLogger("SCIE.association_engine.workers")


class ParticipantAssociationWorkerManager:
  """Manages background async worker coroutines for the Participant Association Engine.

  Architecture:
  - Shared asyncio.Queue across WORKER_COUNT coroutines.
  - Graceful shutdown via None sentinel injection.
  - Exponential backoff retry policy on transient failures.
  - Process-wide singleton via get_instance().
  """

  _instance: Optional["ParticipantAssociationWorkerManager"] = None

  def __init__(self):
    self.queue: asyncio.Queue = asyncio.Queue(
        maxsize=association_config.WORKER_QUEUE_MAXSIZE
    )
    self.pipeline = ParticipantAssociationPipeline()
    self.worker_tasks: List[asyncio.Task] = []
    self.is_running = False

  @classmethod
  def get_instance(cls) -> "ParticipantAssociationWorkerManager":
    if cls._instance is None:
      cls._instance = cls()
    return cls._instance

  def start(self) -> None:
    """Starts background worker loops."""
    if self.is_running and self.worker_tasks and not all(t.done() for t in self.worker_tasks):
      logger.debug("AssociationWorkerManager: Already running.")
      return

    self.is_running = True
    self.worker_tasks.clear()
    self.queue = asyncio.Queue(maxsize=association_config.WORKER_QUEUE_MAXSIZE)
    count = association_config.WORKER_COUNT
    logger.info(f"AssociationWorkerManager: Starting {count} background workers...")

    for i in range(count):
      task = asyncio.create_task(
          self._worker_loop(i),
          name=f"association_worker_{i}",
      )
      self.worker_tasks.append(task)

  async def stop(self) -> None:
    """Gracefully shuts down all background workers."""
    if not self.is_running:
      return

    self.is_running = False
    logger.info("AssociationWorkerManager: Stopping workers...")

    for _ in self.worker_tasks:
      await self.queue.put(None)

    try:
      await asyncio.wait_for(
          asyncio.gather(*self.worker_tasks, return_exceptions=True),
          timeout=5.0,
      )
    except asyncio.TimeoutError:
      logger.warning("AssociationWorkerManager: Shutdown timed out — cancelling tasks.")
      for task in self.worker_tasks:
        task.cancel()

    self.worker_tasks.clear()
    logger.info("AssociationWorkerManager: All workers stopped.")

  async def enqueue_event(
      self,
      meeting_id: str,
      event_data: Any,
      metadata_context: Optional[MeetingMetadata] = None,
  ) -> None:
    """Enqueues an event for background association processing."""
    if not self.is_running:
      logger.warning("AssociationWorkerManager: enqueue_event called before start() — auto-starting workers.")
      self.start()

    try:
      await self.queue.put((meeting_id, event_data, metadata_context))
      logger.debug(f"AssociationWorkerManager: Enqueued event for meeting={meeting_id}")
    except Exception as exc:
      logger.error(f"AssociationWorkerManager: Failed to enqueue event: {exc}")

  async def _worker_loop(self, worker_id: int) -> None:
    """Background coroutine processing items from the event queue."""
    logger.info(f"AssociationWorker[{worker_id}]: Started.")

    while True:
      try:
        task_data = await self.queue.get()
        if task_data is None:
          self.queue.task_done()
          break

        meeting_id, event_data, metadata_context = task_data

        success = False
        for attempt in range(association_config.WORKER_RETRY_COUNT):
          try:
            await self.pipeline.process_event(meeting_id, event_data, metadata_context)
            success = True
            break
          except Exception as exc:
            delay = association_config.WORKER_RETRY_DELAY_SEC * (2 ** attempt)
            logger.error(
                f"AssociationWorker[{worker_id}]: Error processing event "
                f"(attempt {attempt + 1}/{association_config.WORKER_RETRY_COUNT}) — {exc}. "
                f"Retrying in {delay:.1f}s..."
            )
            await asyncio.sleep(delay)

        if not success:
          logger.error(
              f"AssociationWorker[{worker_id}]: Dropped event for meeting={meeting_id} "
              f"after {association_config.WORKER_RETRY_COUNT} attempts."
          )

        self.queue.task_done()

      except asyncio.CancelledError:
        logger.info(f"AssociationWorker[{worker_id}]: Cancelled.")
        break
      except Exception as exc:
        logger.error(f"AssociationWorker[{worker_id}]: Unexpected worker loop error: {exc}")
        await asyncio.sleep(0.1)

    logger.info(f"AssociationWorker[{worker_id}]: Stopped.")


async def enqueue_association_event(
    meeting_id: str,
    event_data: Any,
    metadata_context: Optional[MeetingMetadata] = None,
) -> None:
  """Convenience helper for enqueuing association trigger events."""
  manager = ParticipantAssociationWorkerManager.get_instance()
  await manager.enqueue_event(meeting_id, event_data, metadata_context)
