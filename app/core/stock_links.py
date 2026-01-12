from typing import Optional


def _normalize_code(code: str) -> str:
    return str(code).zfill(6)


def get_chart_url(code: str, name: Optional[str] = None) -> str:
    """Return 东方财富 mobile web URL for a stock code.
    
    Uses wap.eastmoney.com which is:
    - Clickable as a hyperlink in Telegram
    - Prompts to open in APP on mobile devices
    
    Format: https://wap.eastmoney.com/quote/stock/{market}.{code}.html
    Market: 1=Shanghai (6xxxxx), 0=Shenzhen (0xxxxx, 3xxxxx)
    """
    code = _normalize_code(code)
    
    # Determine market: 1=SH, 0=SZ
    market = "1" if code.startswith("6") else "0"
    
    # 东方财富手机网页版 - Telegram可点击，手机打开会提示用APP打开
    return f"https://wap.eastmoney.com/quote/stock/{market}.{code}.html"


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
