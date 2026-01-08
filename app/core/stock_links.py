from typing import Dict, Optional
from app.services.telegraph import telegraph_service


def _normalize_code(code: str) -> str:
    return str(code).zfill(6)


def _eastmoney_chart_url(code: str) -> str:
    """Generate EastMoney K-line chart URL for a stock code."""
    code = _normalize_code(code)
    market = "sh" if code.startswith("6") else "sz"
    return f"https://quote.eastmoney.com/{market}{code}.html"


_chart_url_cache: Dict[str, str] = {}


async def get_chart_url(code: str, name: Optional[str] = None) -> str:
    """Return a Telegraph link for a stock chart, falling back to the chart URL."""
    code = _normalize_code(code)
    cached = _chart_url_cache.get(code)
    if cached:
        return cached

    base_url = _eastmoney_chart_url(code)
    title = f"{name} ({code})" if name else f"{code} Chart"
    content_nodes = [
        {"tag": "p", "children": [title]},
        {"tag": "p", "children": [{"tag": "a", "attrs": {"href": base_url}, "children": ["Open chart"]}]},
    ]

    telegraph_url = await telegraph_service.create_page(
        title=title,
        content_nodes=content_nodes,
        author_name="QuBot"
    )
    if telegraph_url:
        _chart_url_cache[code] = telegraph_url
        return telegraph_url

    return base_url
