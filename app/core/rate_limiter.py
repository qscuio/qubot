import asyncio
import time
from app.core.config import settings
from app.core.logger import Logger

logger = Logger("RateLimiter")


class RateLimiter:
    """Token bucket rate limiter for Telegram API calls."""

    def __init__(self, rate_limit_ms: int = None):
        self.rate_limit_ms = rate_limit_ms or settings.RATE_LIMIT_MS or 30000
        self.rate_limit_seconds = self.rate_limit_ms / 1000
        self._last_call: float = 0
        self._lock = asyncio.Lock()

    async def acquire(self):
        """Wait until we're allowed to make another API call."""
        async with self._lock:
            now = time.time()
            elapsed = now - self._last_call
            
            if elapsed < self.rate_limit_seconds:
                wait_time = self.rate_limit_seconds - elapsed
                await asyncio.sleep(wait_time)
            
            self._last_call = time.time()

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


rate_limiter = RateLimiter()
