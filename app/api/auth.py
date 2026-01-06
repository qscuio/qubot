from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyHeader
from app.core.config import settings
from app.core.logger import Logger

logger = Logger("APIAuth")

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def parse_api_keys() -> dict:
    """Parse API_KEYS env var into {key: userId} mapping."""
    keys = {}
    if not settings.API_KEYS:
        return keys
    
    for pair in settings.API_KEYS.split(","):
        if ":" in pair:
            key, user_id = pair.strip().split(":", 1)
            keys[key.strip()] = user_id.strip()
    
    return keys


async def verify_api_key(request: Request, api_key: str = Depends(api_key_header)) -> str:
    """Verify API key and return user ID."""
    api_keys = parse_api_keys()
    
    # If no keys configured, allow all (for dev)
    if not api_keys:
        return "anonymous"
    
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required")
    
    if api_key not in api_keys:
        logger.warn(f"Invalid API key attempt: {api_key[:8]}...")
        raise HTTPException(status_code=403, detail="Invalid API key")
    
    return api_keys[api_key]
