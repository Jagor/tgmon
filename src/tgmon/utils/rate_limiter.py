"""Rate limiter for message sending."""

import asyncio
import random
import time


class RateLimiter:
    """AsyncIO-based rate limiter with random delay."""

    def __init__(self, min_delay: float = 0.2, max_delay: float = 0.3) -> None:
        """Initialize rate limiter.

        Args:
            min_delay: Minimum delay between operations in seconds.
            max_delay: Maximum delay between operations in seconds.
        """
        self.min_delay = min_delay
        self.max_delay = max_delay
        self._last_call: float = 0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        """Wait until rate limit allows next operation."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call

            # Random delay between min and max
            delay = random.uniform(self.min_delay, self.max_delay)

            if elapsed < delay:
                await asyncio.sleep(delay - elapsed)

            self._last_call = time.monotonic()
