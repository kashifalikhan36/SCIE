"""
Structured Logging & Latency Measurement for the SCIE Confidence Engine (`engine/confidence/`).

Enforces sub-millisecond execution monitoring (`@measure_latency`) and structured logs.
Never uses `print()`. Compatible with Python 3.14+ via `inspect.iscoroutinefunction`.
(`engine/confidence/logger.py`)
"""
import logging
import time
import inspect
from functools import wraps
from typing import Callable, Any

logger = logging.getLogger("scie.engine.confidence")
if not logger.handlers:
  handler = logging.StreamHandler()
  formatter = logging.Formatter(
      fmt="%(asctime)s | %(levelname)-8s | [%(name)s] | %(message)s",
      datefmt="%Y-%m-%dT%H:%M:%S%z"
  )
  handler.setFormatter(formatter)
  logger.addHandler(handler)
logger.setLevel(logging.INFO)


def measure_latency(func: Callable[..., Any]) -> Callable[..., Any]:
  """Sub-millisecond execution latency tracking decorator for sync/async functions."""
  if inspect.iscoroutinefunction(func):
    @wraps(func)
    async def async_wrapper(*args, **kwargs):
      start_t = time.perf_counter()
      try:
        return await func(*args, **kwargs)
      finally:
        elapsed_ms = (time.perf_counter() - start_t) * 1000.0
        logger.debug(f"[LATENCY] {func.__qualname__} completed in {elapsed_ms:.3f} ms")
    return async_wrapper
  else:
    @wraps(func)
    def sync_wrapper(*args, **kwargs):
      start_t = time.perf_counter()
      try:
        return func(*args, **kwargs)
      finally:
        elapsed_ms = (time.perf_counter() - start_t) * 1000.0
        logger.debug(f"[LATENCY] {func.__qualname__} completed in {elapsed_ms:.3f} ms")
    return sync_wrapper
