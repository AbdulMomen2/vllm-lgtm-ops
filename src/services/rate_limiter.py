import redis.asyncio as redis
from src.core.config import settings
import time

class RateLimiter:
    def __init__(self):
        self.r = redis.from_url(settings.REDIS_URL)

    async def is_rate_limited(self, user_id: str) -> bool:
        # We use a simple 'Fixed Window' counter
        current_minute = int(time.time() // 60)
        key = f"rate_limit:{user_id}:{current_minute}"
        
        count = await self.r.incr(key)
        if count == 1:
            await self.r.expire(key, 59) # Cleanup after a minute
            
        return count > settings.RATE_LIMIT_PER_MINUTE

rate_limiter = RateLimiter()