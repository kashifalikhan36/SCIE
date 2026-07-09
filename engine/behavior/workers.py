import asyncio
from typing import List, Optional, Union
from engine.behavior.pipeline import BehaviorPipeline
from engine.behavior.config import behavior_config
from engine.behavior.schemas import (
    VideoObservation, AudioObservation, TranscriptObservation, MetadataObservation
)
from engine.behavior.logger import logger


class BehaviorWorkerManager:
  """Manages background async worker coroutines for the Behavior Engine.

  Architecture:
  - Shared asyncio.Queue across WORKER_COUNT coroutines.
  - Graceful shutdown via None sentinel injection.
  - Exponential backoff retry policy on transient failures.
  - Process-wide singleton via get_instance().
  """

  _instance: Optional["BehaviorWorkerManager"] = None

  def __init__(self) -> None:
    self.queue: asyncio.Queue = asyncio.Queue(
        maxsize=behavior_config.WORKER_QUEUE_MAXSIZE
    )
    self.pipeline = BehaviorPipeline()
    self.worker_tasks: List[asyncio.Task] = []
    self.is_running = False

  @classmethod
  def get_instance(cls) -> "BehaviorWorkerManager":
    """Returns the process-wide singleton, creating it if necessary."""
    if cls._instance is None:
      cls._instance = cls()
    return cls._instance

  def start(self) -> None:
    """Starts background worker coroutines. Idempotent."""
    if self.is_running and self.worker_tasks and not all(t.done() for t in self.worker_tasks):
      logger.debug("BehaviorWorkerManager: Already running.")
      return

    self.is_running = True
    self.worker_tasks.clear()
    self.queue = asyncio.Queue(maxsize=behavior_config.WORKER_QUEUE_MAXSIZE)
    count = behavior_config.WORKER_COUNT
    logger.info(f"BehaviorWorkerManager: Starting {count} background workers.")

    for i in range(count):
      task = asyncio.create_task(
          self._worker_loop(i),
          name=f"behavior_worker_{i}",
      )
      self.worker_tasks.append(task)

  async def stop(self) -> None:
    """Stops all background worker coroutines gracefully via None sentinels."""
    if not self.is_running:
      return

    logger.info("BehaviorWorkerManager: Initiating graceful shutdown.")
    self.is_running = False

    for _ in self.worker_tasks:
      await self.queue.put(None)

    if self.worker_tasks:
      await asyncio.gather(*self.worker_tasks, return_exceptions=True)
    self.worker_tasks.clear()
    logger.info("BehaviorWorkerManager: All workers stopped.")

  async def enqueue(
      self,
      observation: Union[VideoObservation, AudioObservation, TranscriptObservation, MetadataObservation],
      meeting_duration_sec: float = 3600.0
  ) -> None:
    """Push an observation onto the processing queue."""
    if not self.is_running:
      self.start()

    item = (observation, meeting_duration_sec)
    try:
      self.queue.put_nowait(item)
    except asyncio.QueueFull:
      logger.warning("BehaviorWorkerManager: Queue full! Awaiting slot...")
      await self.queue.put(item)

  async def _worker_loop(self, worker_id: int) -> None:
    """Individual worker coroutine loop consuming observations from the queue."""
    logger.debug(f"BehaviorWorker [{worker_id}]: Loop started.")
    while self.is_running:
      try:
        item = await self.queue.get()
        if item is None:
          logger.debug(f"BehaviorWorker [{worker_id}]: Received sentinel, exiting.")
          self.queue.task_done()
          break

        obs, duration_sec = item
        await self._process_with_retry(obs, duration_sec, worker_id)
        self.queue.task_done()

      except asyncio.CancelledError:
        logger.debug(f"BehaviorWorker [{worker_id}]: Cancelled.")
        break
      except Exception as exc:
        logger.error(f"BehaviorWorker [{worker_id}]: Unexpected loop error: {exc}", exc_info=True)

  async def _process_with_retry(
      self,
      observation: Union[VideoObservation, AudioObservation, TranscriptObservation, MetadataObservation],
      meeting_duration_sec: float,
      worker_id: int
  ) -> None:
    """Executes pipeline.process() with retry and exponential backoff."""
    retries = behavior_config.WORKER_RETRY_COUNT
    delay = behavior_config.WORKER_RETRY_DELAY_SEC

    for attempt in range(1, retries + 1):
      try:
        await self.pipeline.process(observation, meeting_duration_sec)
        return
      except Exception as exc:
        if attempt == retries:
          logger.error(f"BehaviorWorker [{worker_id}]: Final retry ({attempt}/{retries}) failed: {exc}")
        else:
          logger.warning(f"BehaviorWorker [{worker_id}]: Attempt {attempt}/{retries} failed: {exc}. Retrying in {delay}s...")
          await asyncio.sleep(delay)
          delay *= 2.0


async def enqueue_behavior_observation(
    observation: Union[VideoObservation, AudioObservation, TranscriptObservation, MetadataObservation],
    meeting_duration_sec: float = 3600.0
) -> None:
  """Convenience entrypoint for pushing an observation to the background Behavior Engine workers."""
  manager = BehaviorWorkerManager.get_instance()
  await manager.enqueue(observation, meeting_duration_sec)
