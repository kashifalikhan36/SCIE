"""
Background Async Worker Manager for the Conversation Reasoning Engine.

Responsibilities:
- Manage shared asyncio.Queue across WORKER_COUNT coroutines.
- Process conversation reasoning requests asynchronously without blocking ingestion pipelines.
- Implement exponential backoff retry on transient failures.
"""
import asyncio
from typing import List, Optional
from engine.transcript.schemas import ConversationTurn
from engine.conversation.pipeline import ConversationPipeline
from engine.conversation.config import conversation_config
from engine.conversation.logger import logger


class ConversationWorkerManager:
  """Manages background async worker coroutines for the Conversation Reasoning Engine."""

  _instance: Optional["ConversationWorkerManager"] = None

  def __init__(self) -> None:
    self.queue: asyncio.Queue = asyncio.Queue(maxsize=conversation_config.WORKER_QUEUE_MAXSIZE)
    self.pipeline = ConversationPipeline()
    self.worker_tasks: List[asyncio.Task] = []
    self.is_running = False

  @classmethod
  def get_instance(cls) -> "ConversationWorkerManager":
    """Returns the process-wide singleton, creating it if necessary."""
    if cls._instance is None:
      cls._instance = cls()
    return cls._instance

  def start(self) -> None:
    """Starts background worker coroutines. Idempotent."""
    if self.is_running and self.worker_tasks and not all(t.done() for t in self.worker_tasks):
      logger.debug("ConversationWorkerManager: Already running.")
      return

    self.is_running = True
    self.worker_tasks.clear()
    self.queue = asyncio.Queue(maxsize=conversation_config.WORKER_QUEUE_MAXSIZE)
    count = conversation_config.WORKER_COUNT
    logger.info(f"ConversationWorkerManager: Starting {count} background workers.")

    for i in range(count):
      task = asyncio.create_task(self._worker_loop(i), name=f"conversation_worker_{i}")
      self.worker_tasks.append(task)

  async def stop(self) -> None:
    """Stops all background worker coroutines gracefully via None sentinels."""
    if not self.is_running:
      return

    logger.info("ConversationWorkerManager: Initiating graceful shutdown.")
    self.is_running = False

    for _ in self.worker_tasks:
      await self.queue.put(None)

    if self.worker_tasks:
      await asyncio.gather(*self.worker_tasks, return_exceptions=True)
    self.worker_tasks.clear()
    logger.info("ConversationWorkerManager: All workers stopped.")

  async def enqueue(
      self,
      meeting_id: str,
      turns: Optional[List[ConversationTurn]] = None,
      prompt_types: Optional[List[str]] = None
  ) -> None:
    """Push a meeting reasoning request onto the processing queue."""
    if not self.is_running:
      self.start()

    item = (meeting_id, turns, prompt_types)
    try:
      self.queue.put_nowait(item)
    except asyncio.QueueFull:
      logger.warning("ConversationWorkerManager: Queue full! Awaiting slot...")
      await self.queue.put(item)

  async def _worker_loop(self, worker_id: int) -> None:
    """Individual worker coroutine loop consuming reasoning requests."""
    logger.debug(f"ConversationWorker [{worker_id}]: Loop started.")
    while self.is_running:
      try:
        item = await self.queue.get()
        if item is None:
          logger.debug(f"ConversationWorker [{worker_id}]: Received sentinel, exiting.")
          self.queue.task_done()
          break

        meeting_id, turns, prompt_types = item
        await self._process_with_retry(meeting_id, turns, prompt_types, worker_id)
        self.queue.task_done()

      except asyncio.CancelledError:
        logger.debug(f"ConversationWorker [{worker_id}]: Cancelled.")
        break
      except Exception as exc:
        logger.error(f"ConversationWorker [{worker_id}]: Unexpected loop error: {exc}", exc_info=True)

  async def _process_with_retry(
      self,
      meeting_id: str,
      turns: Optional[List[ConversationTurn]],
      prompt_types: Optional[List[str]],
      worker_id: int
  ) -> None:
    """Executes pipeline.process() with retry and exponential backoff."""
    retries = conversation_config.RETRY_COUNT
    delay = conversation_config.RETRY_DELAY_SEC

    for attempt in range(1, retries + 1):
      try:
        await self.pipeline.process(meeting_id, turns=turns, prompt_types=prompt_types)
        return
      except Exception as exc:
        if attempt == retries:
          logger.error(f"ConversationWorker [{worker_id}]: Final retry ({attempt}/{retries}) failed for {meeting_id}: {exc}")
        else:
          logger.warning(f"ConversationWorker [{worker_id}]: Attempt {attempt}/{retries} failed for {meeting_id}: {exc}. Retrying in {delay}s...")
          await asyncio.sleep(delay)
          delay *= 2.0


async def enqueue_conversation_reasoning(
    meeting_id: str,
    turns: Optional[List[ConversationTurn]] = None,
    prompt_types: Optional[List[str]] = None
) -> None:
  """Convenience entrypoint for pushing a meeting to the background Conversation Reasoning Engine workers."""
  manager = ConversationWorkerManager.get_instance()
  await manager.enqueue(meeting_id, turns=turns, prompt_types=prompt_types)
