from urllib.parse import quote


def _normalize_code(code: str) -> str:
    return str(code).zfill(6)


def _eastmoney_chart_url(code: str) -> str:
    """Generate EastMoney K-line chart URL for a stock code."""
    code = _normalize_code(code)
    market = "sh" if code.startswith("6") else "sz"
    return f"https://quote.eastmoney.com/{market}{code}.html"


def get_chart_url(code: str) -> str:
    """Return a Telegram Instant View link to the stock chart page."""
    base_url = _eastmoney_chart_url(code)
    return f"https://t.me/iv?url={quote(base_url, safe='')}"
