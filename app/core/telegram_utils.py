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


def escape_html_attr(text: str) -> str:
    return html_escape(text, quote=True)


def format_code_block(code: str, lang: str = "") -> str:
    escaped = escape_html(code)
    return f"<pre><code class=\"language-{lang}\">{escaped}</code></pre>" if lang else f"<pre>{escaped}</pre>"


def strip_html(text: str) -> str:
    return re.sub(r'<[^>]+>', '', text)


def truncate(text: str, max_len: int = 100) -> str:
    return text if len(text) <= max_len else text[:max_len - 3] + "..."


CODE_FENCE_RE = re.compile(r"```(\w+)?\r?\n([\s\S]*?)```")
INLINE_CODE_RE = re.compile(r"`([^`]+)`")
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
BOLD_RE = re.compile(r"\*\*([^\s*][^*]*?[^\s*])\*\*")
ITALIC_RE = re.compile(r"\*([^\s*][^*]*?[^\s*])\*")


def markdown_to_telegram_html(text: str) -> str:
    """Convert a small Markdown subset to Telegram-friendly HTML."""
    if not text:
        return ""

    parts = []
    last = 0
    for match in CODE_FENCE_RE.finditer(text):
        parts.append(_format_text_block(text[last:match.start()]))
        code = match.group(2) or ""
        parts.append(f"<pre><code>{escape_html(code)}</code></pre>")
        last = match.end()

    parts.append(_format_text_block(text[last:]))
    return "".join(parts)


def _format_text_block(text: str) -> str:
    lines = text.splitlines()
    formatted = [_format_line(line) for line in lines]
    return "\n".join(formatted)


def _format_line(line: str) -> str:
    heading = HEADING_RE.match(line)
    if heading:
        content = _format_inline(heading.group(2).strip())
        return f"<b>{content}</b>"
    return _format_inline(line)


def _format_inline(text: str) -> str:
    if not text:
        return ""

    segments = []
    last = 0
    for match in INLINE_CODE_RE.finditer(text):
        segments.append(_format_plain(text[last:match.start()]))
        code = escape_html(match.group(1) or "")
        segments.append(f"<code>{code}</code>")
        last = match.end()

    segments.append(_format_plain(text[last:]))
    return "".join(segments)


def _format_plain(text: str) -> str:
    if not text:
        return ""

    segments = []
    last = 0
    for match in LINK_RE.finditer(text):
        segments.append(escape_html(text[last:match.start()]))
        label = escape_html(match.group(1) or "")
        url = escape_html_attr(match.group(2) or "")
        segments.append(f"<a href=\"{url}\">{label}</a>")
        last = match.end()

    segments.append(escape_html(text[last:]))
    joined = "".join(segments)
    joined = BOLD_RE.sub(r"<b>\1</b>", joined)
    joined = ITALIC_RE.sub(r"<i>\1</i>", joined)
    return joined
