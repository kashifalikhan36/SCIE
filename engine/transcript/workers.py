import asyncio
import logging
from typing import List, Optional

from engine.transcript.schemas import TranscriptChunk
from engine.transcript.pipeline import TranscriptEnginePipeline
from engine.transcript.config import transcript_config

logger = logging.getLogger("SCIE.transcript_engine.workers")


class TranscriptEngineWorkerManager:
  """Manages background async worker tasks for the Transcript Engine.

  Architecture
  ------------
  - A single ``asyncio.Queue`` is shared across ``WORKER_COUNT`` worker
    coroutines.  Each worker independently pulls tasks and calls the
    pipeline.
  - Graceful shutdown: ``None`` sentinel values are pushed to the queue
    (one per worker) so workers unblock their ``await queue.get()`` and
    exit cleanly.
  - Retry policy: the pipeline is retried up to ``WORKER_RETRY_COUNT``
    times with exponential backoff on failure before the event is dropped.
  - This class is a singleton — always access it via ``get_instance()``.

  Thread safety
  -------------
  All state mutations happen inside the asyncio event loop.  No external
  locking is required.
  """

  _instance: Optional["TranscriptEngineWorkerManager"] = None

  def __init__(self) -> None:
    self.queue: asyncio.Queue = asyncio.Queue(
        maxsize=transcript_config.WORKER_QUEUE_MAXSIZE
    )
    self.pipeline      = TranscriptEnginePipeline()
    self.worker_tasks: List[asyncio.Task] = []
    self.is_running    = False

  @classmethod
  def get_instance(cls) -> "TranscriptEngineWorkerManager":
    """Returns the process-wide singleton instance."""
    if cls._instance is None:
      cls._instance = cls()
    return cls._instance

  def start(self) -> None:
    """Starts the configured number of background worker coroutines.

    Idempotent — calling ``start()`` while already running has no effect.
    """
    if self.is_running:
      logger.debug("TranscriptWorkerManager: Already running — ignoring duplicate start().")
      return

    self.is_running = True
    count = transcript_config.WORKER_COUNT
    logger.info(f"TranscriptWorkerManager: Starting {count} background worker(s)...")

    for i in range(count):
      task = asyncio.create_task(
          self._worker_loop(i),
          name=f"transcript_worker_{i}",
      )
      self.worker_tasks.append(task)

  async def stop(self) -> None:
    """Gracefully shuts down all workers.

    Sends one ``None`` sentinel per worker to unblock pending ``get()``
    calls, then waits up to 5 seconds for all tasks to finish.  Any tasks
    that have not finished within the timeout are cancelled.
    """
    if not self.is_running:
      return

    self.is_running = False
    logger.info("TranscriptWorkerManager: Stopping workers...")

    for _ in self.worker_tasks:
      await self.queue.put(None)

    try:
      await asyncio.wait_for(
          asyncio.gather(*self.worker_tasks, return_exceptions=True),
          timeout=5.0,
      )
    except asyncio.TimeoutError:
      logger.warning(
          "TranscriptWorkerManager: Shutdown timed out — cancelling remaining tasks."
      )
      for task in self.worker_tasks:
        task.cancel()

    self.worker_tasks.clear()
    logger.info("TranscriptWorkerManager: All workers stopped.")

  async def enqueue_event(self, meeting_id: str, raw_event: dict) -> None:
    """Enqueues a raw transcript event for background processing.

    If the workers are not yet running (e.g. called before ``start()``),
    they are started automatically.

    Parameters
    ----------
    meeting_id:
        Meeting scope forwarded to the pipeline.
    raw_event:
        Raw dict from the Audio Engine (Whisper output).
    """
    if not self.is_running:
      logger.warning(
          "TranscriptWorkerManager: enqueue_event called before start() — auto-starting workers."
      )
      self.start()

    try:
      await self.queue.put((meeting_id, raw_event))
      logger.debug(
          f"TranscriptWorkerManager: Enqueued event for meeting={meeting_id}"
      )
    except Exception as exc:
      logger.error(f"TranscriptWorkerManager: Failed to enqueue event: {exc}")

  # ── Internal worker loop ───────────────────────────────────────────────────

  async def _worker_loop(self, worker_id: int) -> None:
    """Background task that dequeues and processes transcript events.

    Each event is retried up to ``WORKER_RETRY_COUNT`` times with
    exponential backoff (``WORKER_RETRY_DELAY_SEC * 2^attempt``).
    """
    logger.info(f"TranscriptWorker[{worker_id}]: Started.")

    while True:
      try:
        task_data = await self.queue.get()

        # Shutdown sentinel
        if task_data is None:
          self.queue.task_done()
          break

        meeting_id, raw_event = task_data

        # ── Retry loop ───────────────────────────────────────────────────
        success = False
        for attempt in range(transcript_config.WORKER_RETRY_COUNT):
          try:
            await self.pipeline.process_chunk(meeting_id, raw_event)
            success = True
            break
          except Exception as pipeline_exc:
            delay = transcript_config.WORKER_RETRY_DELAY_SEC * (2 ** attempt)
            logger.error(
                f"TranscriptWorker[{worker_id}]: Pipeline error "
                f"(attempt {attempt + 1}/{transcript_config.WORKER_RETRY_COUNT}) — "
                f"{pipeline_exc}. Retrying in {delay:.1f}s..."
            )
            await asyncio.sleep(delay)

        if not success:
          logger.error(
              f"TranscriptWorker[{worker_id}]: Dropped event for meeting={meeting_id} "
              f"after {transcript_config.WORKER_RETRY_COUNT} failed attempts."
          )

        self.queue.task_done()

      except asyncio.CancelledError:
        logger.info(f"TranscriptWorker[{worker_id}]: Cancelled.")
        break
      except Exception as exc:
        logger.error(
            f"TranscriptWorker[{worker_id}]: Unexpected error in worker loop — {exc}"
        )
        # Brief sleep to prevent CPU spin on continuous errors
        await asyncio.sleep(0.1)

    logger.info(f"TranscriptWorker[{worker_id}]: Stopped.")


# ── Module-level helper ────────────────────────────────────────────────────────

async def enqueue_transcript_event(meeting_id: str, raw_event: dict) -> None:
  """Convenience function for enqueuing a transcript event from any caller.

  Used by the Audio Engine pipeline after assembling Whisper output.
  """
  manager = TranscriptEngineWorkerManager.get_instance()
  await manager.enqueue_event(meeting_id, raw_event)
