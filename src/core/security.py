import json
import logging
from fastapi import Security, HTTPException
from fastapi.security.api_key import APIKeyHeader
from src.core.config import settings
from src.services.rate_limiter import rate_limiter

API_KEY_NAME = "X-API-KEY"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

try:
    CONFIG_KEYS = json.loads(settings.API_KEYS)
except Exception:
    CONFIG_KEYS = {"team-alpha-123": "Alpha_Team", "team-beta-456": "Beta_Team"}


async def validate_user(api_key: str = Security(api_key_header)):
    if not api_key:
        raise HTTPException(status_code=403, detail="Forbidden: Missing API Key")

    # 1. Dynamic Check: Try looking up from Redis HASH 'api_keys' first.
    # This allows adding/revoking keys live in production with no restarts!
    try:
        team_name = await rate_limiter.r.hget("api_keys", api_key)
        if team_name:
            return team_name.decode("utf-8") if isinstance(team_name, bytes) else team_name
    except Exception as e:
        logging.warning(f"Failed to query Redis for api_keys: {e}")

    # 2. Config/Environment Fallback
    if api_key in CONFIG_KEYS:
        # Lazily sync this key to Redis so it's cached/available there too
        try:
            await rate_limiter.r.hset("api_keys", api_key, CONFIG_KEYS[api_key])
        except Exception:
            pass
        return CONFIG_KEYS[api_key]

    raise HTTPException(status_code=403, detail="Forbidden: Invalid API Key")