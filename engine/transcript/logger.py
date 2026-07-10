import time
import logging
from functools import wraps

logger = logging.getLogger("SCIE.transcript_engine")

def measure_latency(stage_name: str):
  """Decorator to measure and log the latency of a transcript pipeline stage."""
  def decorator(func):
    @wraps(func)
    async def async_wrapper(*args, **kwargs):
      start_time = time.perf_counter()
      try:
        result = await func(*args, **kwargs)
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.debug(f"[LATENCY] Stage '{stage_name}' executed in {duration_ms:.2f}ms")
        return result
      except Exception as e:
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.error(f"[LATENCY] Stage '{stage_name}' failed after {duration_ms:.2f}ms: {e}")
        raise

    @wraps(func)
    def sync_wrapper(*args, **kwargs):
      start_time = time.perf_counter()
      try:
        result = func(*args, **kwargs)
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.debug(f"[LATENCY] Stage '{stage_name}' executed in {duration_ms:.2f}ms")
        return result
      except Exception as e:
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.error(f"[LATENCY] Stage '{stage_name}' failed after {duration_ms:.2f}ms: {e}")
        raise

    import inspect
    if inspect.iscoroutinefunction(func):
      return async_wrapper
    return sync_wrapper
  return decorator
