"""
Common utilities and helpers for crawler bot routers.

This module provides shared functionality used across all feature routers.
"""

from typing import Optional
from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest

from app.core.config import settings
from app.core.database import db
from app.core.logger import Logger
from app.core.stock_links import get_chart_url

logger = Logger("CrawlerBot")


# ─────────────────────────────────────────────────────────────────────────────
# Callback Helpers
# ─────────────────────────────────────────────────────────────────────────────

async def safe_answer(callback: types.CallbackQuery, text: str = None) -> None:
    """Safely answer callback query, ignoring stale query errors."""
    try:
        await callback.answer(text)
    except TelegramBadRequest:
        pass  # Query too old or already answered


# ─────────────────────────────────────────────────────────────────────────────
# User Authorization
# ─────────────────────────────────────────────────────────────────────────────

async def get_allowed_users() -> list:
    """Get allowed users from database."""
    if not db.pool:
        return []
    try:
        rows = await db.pool.fetch("SELECT user_id FROM allowed_users")
        return [row['user_id'] for row in rows]
    except Exception:
        return []


async def is_allowed(user_id: int) -> bool:
    """Check if user is allowed (from database)."""
    allowed_users = await get_allowed_users()
    # If no allowed users configured, allow all
    if not allowed_users:
        return True
    return user_id in allowed_users


# ─────────────────────────────────────────────────────────────────────────────
# WebApp URL Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_webapp_base() -> Optional[str]:
    """Resolve the base URL for WebApp buttons."""
    base = (settings.WEBFRONT_URL or "").strip()
    if base:
        return base.rstrip("/")

    domain = (settings.DOMAIN or "").strip()
    if domain:
        if domain.startswith("http://") or domain.startswith("https://"):
            return domain.rstrip("/")
        return f"https://{domain.rstrip('/')}"

    webhook = (settings.WEBHOOK_URL or "").strip()
    if webhook:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(webhook)
            if parsed.scheme and parsed.netloc:
                return f"{parsed.scheme}://{parsed.netloc}"
        except Exception:
            return None
    return None


def _allow_webapp_buttons(chat_type) -> bool:
    """Check if WebApp buttons are allowed for this chat type."""
    if not chat_type:
        return False
    return str(chat_type) in ("private", "group", "supergroup")


def get_webapp_base(chat_type: Optional[str]) -> Optional[str]:
    """Get WebApp base URL if allowed for this chat type."""
    if not _allow_webapp_buttons(chat_type):
        return None
    return _resolve_webapp_base()


# ─────────────────────────────────────────────────────────────────────────────
# Button Formatting Helpers
# ─────────────────────────────────────────────────────────────────────────────

def format_button_text(
    name: str,
    code: str,
    suffix: Optional[str] = None,
    prefix: Optional[str] = None,
    max_len: int = 64,
) -> str:
    """Format button text with name, code, and optional prefix/suffix."""
    parts = []
    if prefix:
        parts.append(prefix)
    parts.append(name)
    parts.append(f"({code})")
    if suffix:
        parts.append(suffix)
    text = " ".join(parts)
    if len(text) > max_len:
        text = text[: max_len - 3] + "..."
    return text


def build_webapp_button(
    name: str,
    code: str,
    context: str,
    webapp_base: str,
    suffix: Optional[str] = None,
    prefix: Optional[str] = None,
) -> types.InlineKeyboardButton:
    """Build a WebApp button for stock chart viewing."""
    url = f"{webapp_base}/miniapp/chart/?code={code}&context={context}"
    text = format_button_text(name, code, suffix=suffix, prefix=prefix)
    return types.InlineKeyboardButton(text=text, web_app=types.WebAppInfo(url=url))


# ─────────────────────────────────────────────────────────────────────────────
# Pagination Helpers
# ─────────────────────────────────────────────────────────────────────────────

def build_pagination_buttons(
    current_page: int,
    total_pages: int,
    callback_prefix: str,
    builder: InlineKeyboardBuilder = None,
) -> list[types.InlineKeyboardButton]:
    """Build pagination navigation buttons.

    Args:
        current_page: Current page number (1-indexed)
        total_pages: Total number of pages
        callback_prefix: Callback data prefix (e.g., "lu:today")
        builder: Optional builder to add buttons to

    Returns:
        List of navigation buttons
    """
    nav_buttons = []

    if current_page > 1:
        nav_buttons.append(types.InlineKeyboardButton(
            text="◀️ 上一页",
            callback_data=f"{callback_prefix}:{current_page - 1}"
        ))

    nav_buttons.append(types.InlineKeyboardButton(
        text="🔄 刷新",
        callback_data=f"{callback_prefix}:{current_page}"
    ))

    if current_page < total_pages:
        nav_buttons.append(types.InlineKeyboardButton(
            text="下一页 ▶️",
            callback_data=f"{callback_prefix}:{current_page + 1}"
        ))

    if builder and nav_buttons:
        builder.row(*nav_buttons)

    return nav_buttons


def calculate_pagination(total_items: int, page: int, page_size: int) -> tuple[int, int, int, int]:
    """Calculate pagination parameters.

    Args:
        total_items: Total number of items
        page: Requested page number (1-indexed)
        page_size: Items per page

    Returns:
        Tuple of (page, total_pages, start_idx, end_idx)
    """
    total_pages = (total_items + page_size - 1) // page_size if total_items > 0 else 1
    page = max(1, min(page, total_pages))
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    return page, total_pages, start_idx, end_idx


# ─────────────────────────────────────────────────────────────────────────────
# Message Edit Helpers
# ─────────────────────────────────────────────────────────────────────────────

async def safe_edit_text(
    message: types.Message,
    text: str,
    parse_mode: str = "HTML",
    reply_markup=None,
    disable_web_page_preview: bool = False,
) -> bool:
    """Safely edit message text, ignoring 'message not modified' errors.

    Returns:
        True if edit succeeded, False if it failed or was skipped
    """
    try:
        await message.edit_text(
            text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
            disable_web_page_preview=disable_web_page_preview,
        )
        return True
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise
        return False
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Stock List Formatting
# ─────────────────────────────────────────────────────────────────────────────

async def build_stock_list_ui(
    stocks: list,
    title: str,
    context: str,
    chat_type: Optional[str] = None,
    page: int = 1,
    page_size: int = 30,
    callback_prefix: str = None,
    back_callback: str = "main",
    show_suffix_fn=None,
) -> tuple[str, types.InlineKeyboardMarkup]:
    """Build paginated stock list UI with optional WebApp buttons.

    Args:
        stocks: List of stock dicts with 'code', 'name', and optional fields
        title: Title for the list
        context: Context string for chart URL
        chat_type: Chat type for WebApp button decision
        page: Current page (1-indexed)
        page_size: Items per page
        callback_prefix: Callback prefix for pagination (e.g., "lu:today")
        back_callback: Callback for back button
        show_suffix_fn: Optional function(stock) -> str for button suffix

    Returns:
        Tuple of (text, markup)
    """
    webapp_base = get_webapp_base(chat_type)
    use_webapp_buttons = bool(webapp_base)

    total = len(stocks)
    page, total_pages, start_idx, end_idx = calculate_pagination(total, page, page_size)
    rows = stocks[start_idx:end_idx]

    if not rows:
        text = f"{title}\n━━━━━━━━━━━━━━━━━━━━━\n📭 暂无数据"
    else:
        text = f"{title} ({start_idx+1}-{start_idx+len(rows)}/{total})\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        if use_webapp_buttons:
            text += "<i>点击下方按钮查看K线</i>\n"
        else:
            for i, r in enumerate(rows, start_idx + 1):
                name = r.get('name') or r.get('code')
                chart_url = get_chart_url(r['code'], name, context=context)
                suffix = show_suffix_fn(r) if show_suffix_fn else ""
                text += f"{i}. <a href=\"{chart_url}\">{name}</a> ({r['code']}){suffix}\n"

    builder = InlineKeyboardBuilder()

    if use_webapp_buttons and rows:
        for i, r in enumerate(rows, start_idx + 1):
            suffix = show_suffix_fn(r) if show_suffix_fn else None
            builder.row(build_webapp_button(
                r.get('name') or r['code'],
                r['code'],
                context,
                webapp_base,
                suffix=suffix,
                prefix=f"{i}."
            ))

    # Add pagination if callback_prefix provided
    if callback_prefix:
        build_pagination_buttons(page, total_pages, callback_prefix, builder)

    builder.row(types.InlineKeyboardButton(text="◀️ 返回", callback_data=back_callback))

    return text, builder.as_markup()
