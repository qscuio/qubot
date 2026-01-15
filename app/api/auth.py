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


def validate_telegram_data(init_data: str, bot_token: str) -> dict:
    """
    Validate Telegram WebApp initData.
    Returns parsed data dict if valid, None otherwise.
    """
    import hmac
    import hashlib
    import json
    from urllib.parse import parse_qsl, unquote

    if not init_data or not bot_token:
        return None

    try:
        parsed = dict(parse_qsl(init_data))
    except ValueError:
        return None
    
    if "hash" not in parsed:
        return None

    hash_ = parsed.pop("hash")
    
    # Sort keys alphabetically
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    
    # HMAC-SHA256 signature
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    
    if calculated_hash != hash_:
        return None
        
    return parsed


async def verify_webapp(request: Request, x_telegram_init_data: str = APIKeyHeader(name="X-Telegram-Init-Data", auto_error=False)) -> int:
    """
    Verify Telegram WebApp initData and return user_id.
    """
    # 1. Check if auth is required (skip if no tokens configured? No, creating security hole)
    # But if ALLOWED_USERS is empty, maybe we allow all? 
    # Logic: Authenticate first, then Authorize.
    
    if not x_telegram_init_data:
        # Development bypass or public access?
        # If user explicitly asked for restriction, we must enforce it.
        # Check if we have allowed users configured.
        if settings.allowed_users_list:
             raise HTTPException(status_code=401, detail="Authentication required")
        # If no allowed users set, maybe just warn? No, user asked to "limit access".
        # Let's enforce auth validation if header is present, else fail if allowed_list is set.
        pass

    header_data = request.headers.get("X-Telegram-Init-Data")
    if not header_data:
        # If allowed users are configured, we strictly require auth
        if settings.allowed_users_list:
            raise HTTPException(status_code=401, detail="Missing initData")
        return 0 # Anonymous

    # Try all possible tokens
    tokens = [
        settings.CRAWLER_BOT_TOKEN,
        settings.BOT_TOKEN,
        settings.AGENT_BOT_TOKEN
    ]
    tokens = [t for t in tokens if t]
    
    user_data = None
    import json
    
    for token in tokens:
        parsed = validate_telegram_data(header_data, token)
        if parsed:
            user_data = parsed
            break
            
    if not user_data:
        raise HTTPException(status_code=403, detail="Invalid initData signature")
        
    # Extract user info
    try:
        user_json = user_data.get("user")
        if not user_json:
            raise HTTPException(status_code=400, detail="No user data")
        user = json.loads(user_json)
        user_id = int(user["id"])
    except Exception:
        raise HTTPException(status_code=400, detail="Malformed user data")
        
    # Authorization
    allowed = settings.allowed_users_list
    if allowed and user_id not in allowed:
        logger.warn(f"Unauthorized WebApp access: {user_id}")
        raise HTTPException(status_code=403, detail="User not allowed")
        
    return user_id


async def verify_webapp_optional(request: Request, x_telegram_init_data: str = APIKeyHeader(name="X-Telegram-Init-Data", auto_error=False)) -> int:
    """
    Verify Telegram WebApp initData but return 0 (Anonymous) if missing or invalid.
    Used for endpoints that support both authenticated and public access.
    """
    try:
        return await verify_webapp(request, x_telegram_init_data)
    except HTTPException:
        return 0

