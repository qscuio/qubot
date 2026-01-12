from typing import Optional, Literal
from app.core.config import settings


def _normalize_code(code: str) -> str:
    return str(code).zfill(6)


def get_chart_url(
    code: str, 
    name: Optional[str] = None,
    source: Literal["miniapp", "eastmoney"] = "miniapp"
) -> str:
    """Return chart URL for a stock code.
    
    Args:
        code: Stock code (e.g., "600519")
        name: Stock name (optional, for display)
        source: Link source - "miniapp" (our chart) or "eastmoney"
    
    Returns:
        URL to stock chart page
    """
    code = _normalize_code(code)
    
    if source == "miniapp":
        # Use our Mini App chart
        base_url = settings.WEBFRONT_URL
        if base_url:
            return f"{base_url.rstrip('/')}/miniapp/chart/?code={code}"
        # Fallback to EastMoney if WEBFRONT_URL not configured
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
    code = _normalize_code(code)
    base_url = settings.WEBFRONT_URL
    if base_url:
        return f"{base_url.rstrip('/')}/miniapp/chart/?code={code}"
    return get_eastmoney_url(code)  # Fallback


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
