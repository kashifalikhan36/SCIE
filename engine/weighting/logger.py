"""
Structured logging module and sub-millisecond latency decorator for the Dynamic Weighting Engine.

(`engine/weighting/logger.py`)
"""
import logging
import time
import inspect
from functools import wraps
from typing import Callable, Any

logger = logging.getLogger("SCIE.weighting_engine")


def measure_latency(metric_name: str) -> Callable:
  """Decorator that logs processing latency (ms) for async and sync methods.

  Uses ``inspect.iscoroutinefunction`` so it is safe and deprecation-warning-free
  on Python 3.14+.
  """

  def decorator(func: Callable) -> Callable:
    if inspect.iscoroutinefunction(func):
      @wraps(func)
      async def async_wrapper(*args, **kwargs) -> Any:
        start = time.perf_counter()
        try:
          return await func(*args, **kwargs)
        finally:
          ms = (time.perf_counter() - start) * 1000.0
          logger.debug(f"Latency[{metric_name}]: {func.__name__} completed in {ms:.2f} ms")
      return async_wrapper
    else:
      @wraps(func)
      def sync_wrapper(*args, **kwargs) -> Any:
        start = time.perf_counter()
        try:
          return func(*args, **kwargs)
        finally:
          ms = (time.perf_counter() - start) * 1000.0
          logger.debug(f"Latency[{metric_name}]: {func.__name__} completed in {ms:.2f} ms")
      return sync_wrapper

  return decorator
