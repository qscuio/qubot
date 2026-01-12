from typing import Dict, Optional
from app.core.config import settings


def _normalize_code(code: str) -> str:
    return str(code).zfill(6)


def get_chart_url(code: str, name: Optional[str] = None) -> str:
    """Return our Mini App chart URL for a stock code.
    
    Uses WEBFRONT_URL to construct the URL to our interactive chart.
    Falls back to EastMoney if WEBFRONT_URL is not configured.
    """
    code = _normalize_code(code)
    
    # Use our Mini App chart if WEBFRONT_URL is configured
    base_url = settings.WEBFRONT_URL
    if base_url:
        return f"{base_url.rstrip('/')}/miniapp/chart/?code={code}"
    
    # Fallback to EastMoney
    market = "sh" if code.startswith("6") else "sz"
    return f"https://quote.eastmoney.com/{market}{code}.html"


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
