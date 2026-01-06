import re
from typing import List
from html import escape as html_escape


def chunk_message(text: str, max_length: int = 4096) -> List[str]:
    """Split long message into chunks for Telegram."""
    if not text or len(text) <= max_length:
        return [text] if text else []

    chunks = []
    remaining = text

    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining)
            break

        chunk = remaining[:max_length]
        split_pos = chunk.rfind("\n\n")
        if split_pos < max_length // 2:
            split_pos = chunk.rfind("\n")
        if split_pos < max_length // 2:
            split_pos = chunk.rfind(". ")
        if split_pos < max_length // 2:
            split_pos = chunk.rfind(" ")
        if split_pos < 1:
            split_pos = max_length

        chunks.append(remaining[:split_pos].rstrip())
        remaining = remaining[split_pos:].lstrip()

    return chunks


def escape_html(text: str) -> str:
    return html_escape(text, quote=False)


def format_code_block(code: str, lang: str = "") -> str:
    escaped = escape_html(code)
    return f"<pre><code class=\"language-{lang}\">{escaped}</code></pre>" if lang else f"<pre>{escaped}</pre>"


def strip_html(text: str) -> str:
    return re.sub(r'<[^>]+>', '', text)


def truncate(text: str, max_len: int = 100) -> str:
    return text if len(text) <= max_len else text[:max_len - 3] + "..."
