"""Legacy retry behavior extracted without changing data policies."""

import functools
import logging
import random
import time

def with_retry(max_attempts: int = 3, base_delay: float = 2.0, exceptions=(Exception,)):
    """
    Retries a function with exponential backoff + jitter on the given
    exception types. Use narrow exception tuples -- retrying on everything
    (including e.g. NotFound) just wastes time re-requesting things that
    will never succeed.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            logger = logging.getLogger(func.__module__)
            last_exc = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt == max_attempts:
                        break
                    sleep_for = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                    logger.warning(
                        f"{func.__name__} failed (attempt {attempt}/{max_attempts}): "
                        f"{type(e).__name__}: {e}. Retrying in {sleep_for:.1f}s"
                    )
                    time.sleep(sleep_for)
            raise last_exc
        return wrapper
    return decorator
