import logging
import time
import inspect
from functools import wraps
from typing import Callable, Any

logger = logging.getLogger("SCIE.association_engine")


def measure_latency(metric_name: str) -> Callable:
  """Decorator that logs processing latency (ms) for async and sync methods.

  Emits structured logs with execution time to assist in performance monitoring
  across long meetings and high participant counts.
  """

  def decorator(func: Callable) -> Callable:
    if inspect.iscoroutinefunction(func):
      @wraps(func)
      async def async_wrapper(*args, **kwargs) -> Any:
        start_time = time.perf_counter()
        try:
          return await func(*args, **kwargs)
        finally:
          duration_ms = (time.perf_counter() - start_time) * 1000.0
          logger.debug(
              f"Latency[{metric_name}]: {func.__name__} completed in {duration_ms:.2f} ms"
          )
      return async_wrapper
    else:
      @wraps(func)
      def sync_wrapper(*args, **kwargs) -> Any:
        start_time = time.perf_counter()
        try:
          return func(*args, **kwargs)
        finally:
          duration_ms = (time.perf_counter() - start_time) * 1000.0
          logger.debug(
              f"Latency[{metric_name}]: {func.__name__} completed in {duration_ms:.2f} ms"
          )
      return sync_wrapper

  return decorator
