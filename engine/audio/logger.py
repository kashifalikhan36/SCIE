import logging
import time
from functools import wraps

# Setup structured logger
logger = logging.getLogger("SCIE.audio_engine")
logger.setLevel(logging.INFO)

# Make sure logger has at least one handler if not configured elsewhere
if not logger.handlers:
  handler = logging.StreamHandler()
  formatter = logging.Formatter(
      "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
  )
  handler.setFormatter(formatter)
  logger.addHandler(handler)

def log_duration(activity_name: str):
  """Decorator to measure and log the execution time of functions/methods."""
  def decorator(func):
    @wraps(func)
    async def async_wrapper(*args, **kwargs):
      start_time = time.perf_counter()
      try:
        result = await func(*args, **kwargs)
        duration = time.perf_counter() - start_time
        logger.info(f"{activity_name} completed in {duration:.4f}s")
        return result
      except Exception as e:
        duration = time.perf_counter() - start_time
        logger.error(f"{activity_name} failed after {duration:.4f}s with error: {e}")
        raise

    @wraps(func)
    def sync_wrapper(*args, **kwargs):
      start_time = time.perf_counter()
      try:
        result = func(*args, **kwargs)
        duration = time.perf_counter() - start_time
        logger.info(f"{activity_name} completed in {duration:.4f}s")
        return result
      except Exception as e:
        duration = time.perf_counter() - start_time
        logger.error(f"{activity_name} failed after {duration:.4f}s with error: {e}")
        raise

      import inspect
      if inspect.iscoroutinefunction(func):
        return async_wrapper(*args, **kwargs)
      return sync_wrapper(*args, **kwargs)

    # Let's inspect signature to choose correct wrapper dynamically
    import inspect
    if inspect.iscoroutinefunction(func):
      return async_wrapper
    return sync_wrapper

  return decorator
