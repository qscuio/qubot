from typing import Optional, Literal
from app.core.config import settings

DEFAULT_CRAWLER_BOT_USERNAME = "q_tty_crawler_bot"


def _normalize_code(code: str) -> str:
    return str(code).zfill(6)


def get_chart_url(
    code: str, 
    name: Optional[str] = None,
    source: Literal["miniapp", "eastmoney"] = "miniapp",
    context: Optional[str] = None
) -> str:
    """Return chart URL for a stock code.
    
    Args:
        code: Stock code (e.g., "600519")
        name: Stock name (optional, for display)
        source: Link source - "miniapp" (our chart) or "eastmoney"
        context: Context for navigation (e.g., "limit_up", "watchlist")
    
    Returns:
        URL to stock chart page
    """
    code = _normalize_code(code)
    
    if source == "miniapp":
        # Prefer direct Mini App link via t.me/{bot_username}/chart?startapp={code}
        # This bypasses Telegram's external link confirmation dialog
        
        # 1. Try runtime cache first (populated on bot startup via getMe)
        bot_username = None
        try:
            from app.bots.dispatcher import get_bot_username
            bot_username = get_bot_username("crawler-bot")
        except ImportError:
            pass
        
        # 2. Fallback to config setting if runtime cache not yet populated
        if not bot_username:
            bot_username = getattr(settings, 'CRAWLER_BOT_USERNAME', None)
        # 3. Hard fallback to known bot username to avoid external web links
        if not bot_username:
            bot_username = DEFAULT_CRAWLER_BOT_USERNAME
        
        if bot_username:
            # Direct Mini App link - opens chart immediately without confirmation
            # Pass context in startapp param: code_context
            start_param = f"{code}_{context}" if context else code
            return f"https://t.me/{bot_username}/chart?startapp={start_param}"
        
        # 3. Fallback to standard web URL (shows confirmation dialog)
        base_url = settings.WEBFRONT_URL
        if base_url:
            url = f"{base_url.rstrip('/')}/miniapp/chart/?code={code}"
            if context:
                url += f"&context={context}"
            return url
        # 4. Fallback to EastMoney if WEBFRONT_URL not configured
        source = "eastmoney"
    
    # EastMoney mobile web
    market = "1" if code.startswith("6") else "0"
    return f"https://wap.eastmoney.com/quote/stock/{market}.{code}.html"


def get_eastmoney_url(code: str) -> str:
    """Direct shortcut for EastMoney URL."""
    code = _normalize_code(code)
    market = "1" if code.startswith("6") else "0"
    return f"https://wap.eastmoney.com/quote/stock/{market}.{code}.html"


def get_miniapp_url(code: str) -> str:
    """Direct shortcut for our miniapp chart URL."""
    return get_chart_url(code, source="miniapp")


# Async wrapper for backward compatibility
async def get_chart_url_async(code: str, name: Optional[str] = None) -> str:
    """Async wrapper for get_chart_url (for backward compatibility)."""
    return get_chart_url(code, name)


def get_sector_url(sector_name: str, sector_type: str = "concept") -> str:
    """Generate EastMoney sector page URL.
    
    Args:
        sector_name: Name of the sector (e.g., "Kimi概念")
        sector_type: 'industry' or 'concept'
    
    Returns:
        EastMoney sector search URL
    """
    import urllib.parse
    # EastMoney search URL for sectors
    encoded_name = urllib.parse.quote(sector_name)
    return f"https://so.eastmoney.com/web/s?keyword={encoded_name}"
