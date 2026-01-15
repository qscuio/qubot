"""
Crawler Bot Handlers

Telegram bot interface for web crawler and limit-up stock tracking.
"""

from aiogram import Router, F, types, Bot
from typing import Optional
import time
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest



from app.services.crawler import crawler_service
from app.services.limit_up import limit_up_service
from app.services.stock_scanner import stock_scanner
from app.services.sector import sector_service
from app.services.market_report import market_report_service
from app.services.watchlist import watchlist_service
from app.services.trading_simulator import trading_simulator, MAX_POSITIONS
from app.services.daban_service import daban_service
from app.services.daban_simulator import daban_simulator, MAX_POSITIONS as DABAN_MAX_POSITIONS
from app.services.portfolio import portfolio_service
from app.core.config import settings
from app.core.database import db
from app.core.logger import Logger
from app.core.stock_links import get_chart_url
from app.core.timezone import china_today

logger = Logger("CrawlerBot")
router = Router()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

async def safe_answer(callback: types.CallbackQuery, text: str = None) -> None:
    """Safely answer callback query, ignoring stale query errors."""
    try:
        await callback.answer(text)
    except TelegramBadRequest:
        pass  # Query too old or already answered


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


def _resolve_webapp_base() -> Optional[str]:
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
    if not chat_type:
        return False
    return str(chat_type) in ("private", "group", "supergroup")


def _get_webapp_base(chat_type: Optional[str]) -> Optional[str]:
    if not _allow_webapp_buttons(chat_type):
        return None
    return _resolve_webapp_base()


def _format_button_text(
    name: str,
    code: str,
    suffix: Optional[str] = None,
    prefix: Optional[str] = None,
    max_len: int = 64,
) -> str:
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


def _build_webapp_button(
    name: str,
    code: str,
    context: str,
    webapp_base: str,
    suffix: Optional[str] = None,
    prefix: Optional[str] = None,
) -> types.InlineKeyboardButton:
    url = f"{webapp_base}/miniapp/chart/?code={code}&context={context}"
    text = _format_button_text(name, code, suffix=suffix, prefix=prefix)
    return types.InlineKeyboardButton(text=text, web_app=types.WebAppInfo(url=url))


# ─────────────────────────────────────────────────────────────────────────────
# Main Menu
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    if not await is_allowed(message.from_user.id):
        return
    
    sources = await crawler_service.get_sources()
    streaks = await limit_up_service.get_streak_leaders()
    
    text = (
        "📊 <b>数据中心</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"🕷️ 爬虫网站: <b>{len(sources)}</b>\n"
        f"🔥 连板股: <b>{len(streaks)}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🕷️ 网站爬虫", callback_data="crawler:main")
    builder.button(text="📈 涨停追踪", callback_data="lu:main")
    builder.button(text="🔍 信号扫描", callback_data="scanner:main")
    builder.button(text="📊 板块分析", callback_data="sector:main")
    builder.button(text="📋 市场报告", callback_data="report:main")
    builder.button(text="🎯 打板交易", callback_data="daban:main")
    builder.button(text="⭐ 自选列表", callback_data="watch:list")
    builder.button(text="💰 模拟交易", callback_data="sim:main")
    builder.adjust(2, 2, 2, 2)
    
    await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())


# ─────────────────────────────────────────────────────────────────────────────
# Crawler Section
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "crawler:main")
async def cb_crawler_main(callback: types.CallbackQuery):
    await safe_answer(callback)
    sources = await crawler_service.get_sources()
    items = await crawler_service.get_recent_items(limit=5)
    
    text = (
        "🕷️ <b>网站爬虫</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"📁 网站: <b>{len(sources)}</b>\n"
        f"📄 最新: <b>{len(items)}</b>\n"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📁 网站列表", callback_data="crawler:list")
    builder.button(text="📄 最新内容", callback_data="crawler:recent")
    builder.button(text="🔄 立即爬取", callback_data="crawler:crawl")
    builder.button(text="◀️ 返回", callback_data="main")
    builder.adjust(2, 2)
    
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    except Exception:
        pass


@router.callback_query(F.data == "main")
async def cb_main(callback: types.CallbackQuery):
    await safe_answer(callback)
    sources = await crawler_service.get_sources()
    streaks = await limit_up_service.get_streak_leaders()
    
    text = (
        "📊 <b>数据中心</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"🕷️ 爬虫网站: <b>{len(sources)}</b>\n"
        f"🔥 连板股: <b>{len(streaks)}</b>\n"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🕷️ 网站爬虫", callback_data="crawler:main")
    builder.button(text="📈 涨停追踪", callback_data="lu:main")
    builder.button(text="🔍 信号扫描", callback_data="scanner:main")
    builder.button(text="📊 板块分析", callback_data="sector:main")
    builder.button(text="📋 市场报告", callback_data="report:main")
    builder.button(text="🎯 打板交易", callback_data="daban:main")
    builder.button(text="⭐ 自选列表", callback_data="watch:list")
    builder.button(text="💰 模拟交易", callback_data="sim:main")
    builder.adjust(2, 2, 2, 2)
    
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Add Source
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("add"))
async def cmd_add(message: types.Message, command: CommandObject):
    if not await is_allowed(message.from_user.id):
        return
    
    args = command.args
    if not args:
        text = (
            "📥 <b>添加网站</b>\n\n"
            "用法: <code>/add &lt;url&gt; [名称]</code>\n\n"
            "例如:\n"
            "• <code>/add https://finance.sina.com.cn</code>\n"
            "• <code>/add https://finance.yahoo.com 雅虎财经</code>"
        )
        await message.answer(text, parse_mode="HTML")
        return
    
    parts = args.split(maxsplit=1)
    url = parts[0]
    name = parts[1] if len(parts) > 1 else None
    
    if not url.startswith("http"):
        url = "https://" + url
    
    status = await message.answer(f"⏳ 正在添加 {url}...")
    
    try:
        result = await crawler_service.add_source(url, name)
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📁 查看列表", callback_data="crawler:list")
        builder.adjust(1)
        
        await status.edit_text(
            f"✅ 已添加 <b>{result['name']}</b>",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        await status.edit_text(f"❌ 错误: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# List Sources
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("list"))
async def cmd_list(message: types.Message):
    if not await is_allowed(message.from_user.id):
        return
    text, markup = await get_sources_ui()
    await message.answer(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)


@router.callback_query(F.data == "crawler:list")
async def cb_list(callback: types.CallbackQuery):
    await safe_answer(callback)
    text, markup = await get_sources_ui()
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
    except Exception:
        pass


async def get_sources_ui():
    sources = await crawler_service.get_sources()
    
    if not sources:
        text = "📁 <b>网站列表</b>\n━━━━━━━━━━━━━━━━━━━━━\n📭 暂无网站\n\n用 /add 添加"
        builder = InlineKeyboardBuilder()
        builder.button(text="◀️ 返回", callback_data="crawler:main")
        return text, builder.as_markup()
    
    text = f"📁 <b>网站列表</b> ({len(sources)})\n━━━━━━━━━━━━━━━━━━━━━\n"
    
    for i, src in enumerate(sources[:10], 1):
        name = src.get("name", "?")[:20]
        last = src.get("last_crawled_at")
        last_str = last.strftime("%m/%d %H:%M") if last else "从未"
        text += f"{i}. <b>{name}</b> ({last_str})\n"
    
    builder = InlineKeyboardBuilder()
    for src in sources[:8]:
        name = src.get("name", "?")[:12]
        builder.button(text=f"🗑️ {name}", callback_data=f"crawler:del:{src['id']}")
    builder.adjust(2)
    
    kb = builder.as_markup()
    kb.inline_keyboard.append([
        types.InlineKeyboardButton(text="◀️ 返回", callback_data="crawler:main"),
    ])
    
    return text, kb


@router.message(Command("remove"))
async def cmd_remove(message: types.Message):
    if not await is_allowed(message.from_user.id):
        return
    text, markup = await get_sources_ui()
    await message.answer(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)


@router.callback_query(F.data.startswith("crawler:del:"))
async def cb_delete(callback: types.CallbackQuery):
    source_id = int(callback.data.split(":")[2])
    result = await crawler_service.remove_source(source_id)
    if result:
        await safe_answer(callback, "✅ 已删除")
        text, markup = await get_sources_ui()
        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
        except Exception:
            pass
    else:
        await safe_answer(callback, "❌ 删除失败")


# ─────────────────────────────────────────────────────────────────────────────
# Crawl (Manual)
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("crawl"))
async def cmd_crawl(message: types.Message):
    if not await is_allowed(message.from_user.id):
        return
    
    status = await message.answer("⏳ 正在爬取...")
    
    try:
        result = await crawler_service.crawl_all()
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📄 查看内容", callback_data="crawler:recent")
        builder.adjust(1)
        
        await status.edit_text(
            f"✅ 爬取完成\n\n"
            f"📁 网站: <b>{result['sources']}</b>\n"
            f"📄 新内容: <b>{result['items']}</b>",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        await status.edit_text(f"❌ 错误: {e}")


@router.callback_query(F.data == "crawler:crawl")
async def cb_crawl(callback: types.CallbackQuery):
    await safe_answer(callback, "⏳ 爬取中...")
    
    try:
        result = await crawler_service.crawl_all()
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📄 查看内容", callback_data="crawler:recent")
        builder.button(text="◀️ 返回", callback_data="crawler:main")
        builder.adjust(2)
        
        await callback.message.edit_text(
            f"✅ 爬取完成\n\n"
            f"📁 网站: <b>{result['sources']}</b>\n"
            f"📄 新内容: <b>{result['items']}</b>",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        await callback.message.edit_text(f"❌ 错误: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Recent Items
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("recent"))
async def cmd_recent(message: types.Message):
    if not await is_allowed(message.from_user.id):
        return
    text, markup = await get_recent_ui()
    await message.answer(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)


@router.callback_query(F.data == "crawler:recent")
async def cb_recent(callback: types.CallbackQuery):
    await safe_answer(callback)
    text, markup = await get_recent_ui()
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
    except Exception:
        pass


async def get_recent_ui():
    items = await crawler_service.get_recent_items(limit=10)
    
    if not items:
        text = "📄 <b>最新内容</b>\n━━━━━━━━━━━━━━━━━━━━━\n📭 暂无内容"
        builder = InlineKeyboardBuilder()
        builder.button(text="◀️ 返回", callback_data="crawler:main")
        return text, builder.as_markup()
    
    text = f"📄 <b>最新内容</b> ({len(items)})\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    for item in items[:8]:
        source = item.get("source_name", "?")[:10]
        title = item.get("title", "?")[:40]
        url = item.get("url", "")
        text += f"• <a href=\"{url}\">{title}</a>\n  <i>{source}</i>\n\n"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 刷新", callback_data="crawler:recent")
    builder.button(text="◀️ 返回", callback_data="crawler:main")
    builder.adjust(2)
    
    return text, builder.as_markup()


# ═══════════════════════════════════════════════════════════════════════════
# 涨停追踪 (Limit-Up Tracking)
# ═══════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "lu:main")
async def cb_lu_main(callback: types.CallbackQuery):
    await safe_answer(callback)
    streaks = await limit_up_service.get_streak_leaders()
    strong = await limit_up_service.get_strong_stocks()
    
    text = (
        "📈 <b>涨停追踪</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔥 连板股: <b>{len(streaks)}</b>\n"
        f"💪 强势股: <b>{len(strong)}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "<i>每日15:15自动收集</i>"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📈 今日涨停", callback_data="lu:today")
    builder.button(text="🆕 首板", callback_data="lu:first")
    builder.button(text="💥 曾涨停", callback_data="lu:burst")
    builder.button(text="🔥 连板榜", callback_data="lu:streak")
    builder.button(text="💪 强势股", callback_data="lu:strong")
    builder.button(text="👀 启动追踪", callback_data="lu:watch")
    builder.button(text=" 同步涨停", callback_data="lu:sync")
    builder.button(text="◀️ 返回", callback_data="main")
    builder.adjust(2, 2, 2, 2)
    
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Today's Limit-Ups
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("today"))
async def cmd_today(message: types.Message):
    if not await is_allowed(message.from_user.id):
        return
    text, markup = await get_today_ui(chat_type=message.chat.type)
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data.startswith("lu:today"))
async def cb_today(callback: types.CallbackQuery):
    await safe_answer(callback)
    # Parse page from callback data (format: lu:today or lu:today:1)
    parts = callback.data.split(":")
    page = int(parts[2]) if len(parts) > 2 else 1
    text, markup = await get_today_ui(page, chat_type=callback.message.chat.type if callback.message else None)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
    except Exception:
        pass


async def get_today_ui(page: int = 1, chat_type: Optional[str] = None):
    PAGE_SIZE = 30
    webapp_base = _get_webapp_base(chat_type)
    use_webapp_buttons = bool(webapp_base)
    
    if not db.pool:
        return "❌ 数据库未连接", None
    
    # Use China timezone for date calculation
    # today = china_today()
    
    # 🌟 Real-time fetch from AkShare
    try:
        stocks = await limit_up_service.get_realtime_limit_ups()
    except Exception as e:
        logger.error(f"Real-time fetch failed: {e}")
        stocks = []
    
    # Filter for valid data
    if stocks:
        # Sealed only
        sealed = [s for s in stocks if s.get("is_sealed", True)]
        # Sort: limit_times desc, price desc
        sealed.sort(key=lambda x: (-x.get("limit_times", 1), -x.get("close_price", 0)))
    else:
        sealed = []
    
    total = len(sealed)
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE if total > 0 else 1
    page = max(1, min(page, total_pages))
    
    start_idx = (page - 1) * PAGE_SIZE
    end_idx = start_idx + PAGE_SIZE
    rows = sealed[start_idx:end_idx]
    
    if not rows:
        text = "📈 <b>今日涨停</b> (实时)\n━━━━━━━━━━━━━━━━━━━━━\n📭 暂无数据\n\n<i>数据源: 东方财富</i>"
    else:
        text = f"📈 <b>今日涨停</b> ({start_idx+1}-{start_idx+len(rows)}/{total})\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        if use_webapp_buttons:
            text += "<i>点击下方按钮查看K线</i>\n"
        else:
            for i, r in enumerate(rows, start_idx + 1):
                lt = r.get('limit_times', 1)
                streak = f" [{lt}板]" if lt > 1 else ""
                name = r.get('name') or r.get('code')
                chart_url = get_chart_url(r['code'], name, context="limit_up")
                text += f"{i}. <a href=\"{chart_url}\">{name}</a> ({r['code']}){streak}\n"
    
    builder = InlineKeyboardBuilder()
    if use_webapp_buttons:
        if rows:
            for i, r in enumerate(rows, start_idx + 1):
                lt = r.get('limit_times', 1)
                suffix = f"{lt}板" if lt > 1 else "首板"
                builder.row(
                    _build_webapp_button(
                        r.get('name') or r['code'],
                        r['code'],
                        "limit_up",
                        webapp_base,
                        suffix=suffix,
                        prefix=f"{i}."
                    )
                )
        nav_buttons = []
        if page > 1:
            nav_buttons.append(types.InlineKeyboardButton(text="◀️ 上一页", callback_data=f"lu:today:{page-1}"))
        nav_buttons.append(types.InlineKeyboardButton(text="🔄 刷新", callback_data=f"lu:today:{page}"))
        if page < total_pages:
            nav_buttons.append(types.InlineKeyboardButton(text="下一页 ▶️", callback_data=f"lu:today:{page+1}"))
        if nav_buttons:
            builder.row(*nav_buttons)
        builder.row(types.InlineKeyboardButton(text="◀️ 返回", callback_data="lu:main"))
    else:
        # Pagination buttons
        if page > 1:
            builder.button(text="◀️ 上一页", callback_data=f"lu:today:{page-1}")
        builder.button(text="🔄 刷新", callback_data=f"lu:today:{page}")
        if page < total_pages:
            builder.button(text="下一页 ▶️", callback_data=f"lu:today:{page+1}")
        builder.button(text="◀️ 返回", callback_data="lu:main")
        builder.adjust(3, 1)
    
    return text, builder.as_markup()


# ─────────────────────────────────────────────────────────────────────────────
# First-Board (首板 - First-time Limit-up)
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("first"))
async def cmd_first(message: types.Message):
    if not await is_allowed(message.from_user.id):
        return
    text, markup = await get_first_ui(chat_type=message.chat.type)
    await message.answer(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)


@router.callback_query(F.data.startswith("lu:first"))
async def cb_first(callback: types.CallbackQuery):
    await safe_answer(callback)
    parts = callback.data.split(":")
    page = int(parts[2]) if len(parts) > 2 else 1
    text, markup = await get_first_ui(page, chat_type=callback.message.chat.type if callback.message else None)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
    except Exception:
        pass


async def get_first_ui(page: int = 1, chat_type: Optional[str] = None):
    """Get today's first-time limit-up stocks (首板 - 收盘涨停 limit_times=1)."""
    PAGE_SIZE = 30
    webapp_base = _get_webapp_base(chat_type)
    use_webapp_buttons = bool(webapp_base)
    
    if not db.pool:
        return "❌ 数据库未连接", None
    
    # Use China timezone for date calculation
    # today = china_today()
    
    # 🌟 Real-time fetch
    try:
        stocks = await limit_up_service.get_realtime_limit_ups()
    except Exception:
        stocks = []
        
    if stocks:
        # Filter: limit_times=1 AND is_sealed=True
        first_board = [
            s for s in stocks 
            if s.get("limit_times", 1) == 1 and s.get("is_sealed", True)
        ]
        # Sort by turnover desc
        first_board.sort(key=lambda x: -x.get("turnover_rate", 0))
    else:
        first_board = []
    
    total = len(first_board)
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE if total > 0 else 1
    page = max(1, min(page, total_pages))
    
    start_idx = (page - 1) * PAGE_SIZE
    end_idx = start_idx + PAGE_SIZE
    rows = first_board[start_idx:end_idx]
    
    if not rows:
        text = "🆕 <b>首板</b> (实时)\n━━━━━━━━━━━━━━━━━━━━━\n📭 暂无首板数据"
    else:
        text = f"🆕 <b>首板</b> ({start_idx+1}-{start_idx+len(rows)}/{total})\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        if use_webapp_buttons:
            text += "<i>点击下方按钮查看K线</i>\n"
        else:
            for i, r in enumerate(rows, start_idx + 1):
                name = r.get('name') or r.get('code')
                tr = r.get('turnover_rate', 0)
                turnover = f"换手{tr:.1f}%" if tr else ""
                chart_url = get_chart_url(r['code'], name, context="limit_up_first")
                text += f"{i}. <a href=\"{chart_url}\">{name}</a> ({r['code']}) {turnover}\n"
    
    builder = InlineKeyboardBuilder()
    if use_webapp_buttons:
        if rows:
            for i, r in enumerate(rows, start_idx + 1):
                tr = r.get('turnover_rate', 0)
                suffix = f"换手{tr:.1f}%" if tr else None
                builder.row(
                    _build_webapp_button(
                        r.get('name') or r['code'],
                        r['code'],
                        "limit_up_first",
                        webapp_base,
                        suffix=suffix,
                        prefix=f"{i}."
                    )
                )
        nav_buttons = []
        if page > 1:
            nav_buttons.append(types.InlineKeyboardButton(text="◀️ 上一页", callback_data=f"lu:first:{page-1}"))
        nav_buttons.append(types.InlineKeyboardButton(text="🔄 刷新", callback_data=f"lu:first:{page}"))
        if page < total_pages:
            nav_buttons.append(types.InlineKeyboardButton(text="下一页 ▶️", callback_data=f"lu:first:{page+1}"))
        if nav_buttons:
            builder.row(*nav_buttons)
        builder.row(types.InlineKeyboardButton(text="◀️ 返回", callback_data="lu:main"))
    else:
        if page > 1:
            builder.button(text="◀️ 上一页", callback_data=f"lu:first:{page-1}")
        builder.button(text="🔄 刷新", callback_data=f"lu:first:{page}")
        if page < total_pages:
            builder.button(text="下一页 ▶️", callback_data=f"lu:first:{page+1}")
        builder.button(text="◀️ 返回", callback_data="lu:main")
        builder.adjust(3, 1)
    
    return text, builder.as_markup()


# ─────────────────────────────────────────────────────────────────────────────
# Burst Limit-Ups (曾涨停/炸板)
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("burst"))
async def cmd_burst(message: types.Message):
    if not await is_allowed(message.from_user.id):
        return
    text, markup = await get_burst_ui(chat_type=message.chat.type)
    await message.answer(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)


@router.callback_query(F.data.startswith("lu:burst"))
async def cb_burst(callback: types.CallbackQuery):
    await safe_answer(callback)
    parts = callback.data.split(":")
    page = int(parts[2]) if len(parts) > 2 else 1
    text, markup = await get_burst_ui(page, chat_type=callback.message.chat.type if callback.message else None)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
    except Exception:
        pass


async def get_burst_ui(page: int = 1, chat_type: Optional[str] = None):
    """Get today's burst limit-up stocks (曾涨停/炸板 - 触及涨停但收盘未封住)."""
    PAGE_SIZE = 30
    webapp_base = _get_webapp_base(chat_type)
    use_webapp_buttons = bool(webapp_base)
    
    if not db.pool:
        return "❌ 数据库未连接", None
    
    # Use China timezone for date calculation
    # today = china_today()
    
    # 🌟 Real-time fetch
    try:
        stocks = await limit_up_service.get_realtime_limit_ups()
    except Exception:
        stocks = []
        
    if stocks:
        # Filter: is_sealed=False (Burst)
        burst = [s for s in stocks if not s.get("is_sealed", True)]
        # Sort by change_pct desc
        burst.sort(key=lambda x: -x.get("change_pct", 0))
    else:
        burst = []
    
    total = len(burst)
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE if total > 0 else 1
    page = max(1, min(page, total_pages))
    
    start_idx = (page - 1) * PAGE_SIZE
    end_idx = start_idx + PAGE_SIZE
    rows = burst[start_idx:end_idx]
    
    if not rows:
        text = "💥 <b>曾涨停</b> (实时)\n━━━━━━━━━━━━━━━━━━━━━\n📭 暂无炸板数据"
    else:
        text = f"💥 <b>曾涨停</b> ({start_idx+1}-{start_idx+len(rows)}/{total})\n━━━━━━━━━━━━━━━━━━━━━\n<i>日内涨停但未封住</i>\n\n"
        if use_webapp_buttons:
            text += "<i>点击下方按钮查看K线</i>\n"
        else:
            for i, r in enumerate(rows, start_idx + 1):
                name = r.get('name') or r.get('code')
                cp = r.get('change_pct', 0)
                change = f"{cp:.1f}%" if cp else ""
                chart_url = get_chart_url(r['code'], name, context="limit_up_burst")
                text += f"{i}. <a href=\"{chart_url}\">{name}</a> ({r['code']}) {change}\n"
    
    builder = InlineKeyboardBuilder()
    if use_webapp_buttons:
        if rows:
            for i, r in enumerate(rows, start_idx + 1):
                cp = r.get('change_pct', 0)
                suffix = f"{cp:+.1f}%" if cp else None
                builder.row(
                    _build_webapp_button(
                        r.get('name') or r['code'],
                        r['code'],
                        "limit_up_burst",
                        webapp_base,
                        suffix=suffix,
                        prefix=f"{i}."
                    )
                )
        nav_buttons = []
        if page > 1:
            nav_buttons.append(types.InlineKeyboardButton(text="◀️ 上一页", callback_data=f"lu:burst:{page-1}"))
        nav_buttons.append(types.InlineKeyboardButton(text="🔄 刷新", callback_data=f"lu:burst:{page}"))
        if page < total_pages:
            nav_buttons.append(types.InlineKeyboardButton(text="下一页 ▶️", callback_data=f"lu:burst:{page+1}"))
        if nav_buttons:
            builder.row(*nav_buttons)
        builder.row(types.InlineKeyboardButton(text="◀️ 返回", callback_data="lu:main"))
    else:
        if page > 1:
            builder.button(text="◀️ 上一页", callback_data=f"lu:burst:{page-1}")
        builder.button(text="🔄 刷新", callback_data=f"lu:burst:{page}")
        if page < total_pages:
            builder.button(text="下一页 ▶️", callback_data=f"lu:burst:{page+1}")
        builder.button(text="◀️ 返回", callback_data="lu:main")
        builder.adjust(3, 1)
    
    return text, builder.as_markup()


# ─────────────────────────────────────────────────────────────────────────────
# Streak Leaders
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("streak"))
async def cmd_streak(message: types.Message):
    if not await is_allowed(message.from_user.id):
        return
    text, markup = await get_streak_ui(chat_type=message.chat.type)
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "lu:streak")
async def cb_streak(callback: types.CallbackQuery):
    await safe_answer(callback)
    text, markup = await get_streak_ui(chat_type=callback.message.chat.type if callback.message else None)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        pass


async def get_streak_ui(chat_type: Optional[str] = None):
    webapp_base = _get_webapp_base(chat_type)
    use_webapp_buttons = bool(webapp_base)
    streaks = await limit_up_service.get_streak_leaders()
    
    if not streaks:
        text = "🔥 <b>连板榜</b>\n━━━━━━━━━━━━━━━━━━━━━\n📭 暂无连板股"
    else:
        text = f"🔥 <b>连板榜</b> ({len(streaks)})\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        if use_webapp_buttons:
            text += "<i>点击下方按钮查看K线</i>\n"
        else:
            for i, s in enumerate(streaks, 1):
                name = s.get('name') or s.get('code')
                chart_url = get_chart_url(s['code'], name, context="limit_up_streak")
                text += f"{i}. <a href=\"{chart_url}\">{name}</a> ({s['code']}) - <b>{s['streak_count']}连板</b>\n"
    
    builder = InlineKeyboardBuilder()
    if use_webapp_buttons and streaks:
        for i, s in enumerate(streaks, 1):
            suffix = f"{s['streak_count']}连板"
            builder.row(
                _build_webapp_button(
                    s.get('name') or s['code'],
                    s['code'],
                    "limit_up_streak",
                    webapp_base,
                    suffix=suffix,
                    prefix=f"{i}."
                )
            )
    if use_webapp_buttons:
        builder.row(
            types.InlineKeyboardButton(text="🔄 刷新", callback_data="lu:streak"),
            types.InlineKeyboardButton(text="◀️ 返回", callback_data="lu:main")
        )
    else:
        builder.button(text="🔄 刷新", callback_data="lu:streak")
        builder.button(text="◀️ 返回", callback_data="lu:main")
        builder.adjust(2)
    
    return text, builder.as_markup()


# ─────────────────────────────────────────────────────────────────────────────
# Strong Stocks
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("strong"))
async def cmd_strong(message: types.Message):
    if not await is_allowed(message.from_user.id):
        return
    text, markup = await get_strong_ui(chat_type=message.chat.type)
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "lu:strong")
async def cb_strong(callback: types.CallbackQuery):
    await safe_answer(callback)
    text, markup = await get_strong_ui(chat_type=callback.message.chat.type if callback.message else None)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        pass


async def get_strong_ui(chat_type: Optional[str] = None):
    webapp_base = _get_webapp_base(chat_type)
    use_webapp_buttons = bool(webapp_base)
    strong = await limit_up_service.get_strong_stocks()
    
    if not strong:
        text = "💪 <b>强势股</b> (7日)\n━━━━━━━━━━━━━━━━━━━━━\n📭 暂无强势股"
    else:
        text = f"💪 <b>强势股</b> (7日, {len(strong)})\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        if use_webapp_buttons:
            text += "<i>点击下方按钮查看K线</i>\n"
        else:
            for i, s in enumerate(strong, 1):
                name = s.get('name') or s.get('code')
                chart_url = get_chart_url(s['code'], name, context="limit_up_strong")
                text += f"{i}. <a href=\"{chart_url}\">{name}</a> ({s['code']}) - {s['limit_count']}次涨停\n"
    
    builder = InlineKeyboardBuilder()
    if use_webapp_buttons and strong:
        for i, s in enumerate(strong, 1):
            suffix = f"{s['limit_count']}次涨停"
            builder.row(
                _build_webapp_button(
                    s.get('name') or s['code'],
                    s['code'],
                    "limit_up_strong",
                    webapp_base,
                    suffix=suffix,
                    prefix=f"{i}."
                )
            )
    if use_webapp_buttons:
        builder.row(
            types.InlineKeyboardButton(text="🔄 刷新", callback_data="lu:strong"),
            types.InlineKeyboardButton(text="◀️ 返回", callback_data="lu:main")
        )
    else:
        builder.button(text="🔄 刷新", callback_data="lu:strong")
        builder.button(text="◀️ 返回", callback_data="lu:main")
        builder.adjust(2)
    
    return text, builder.as_markup()


# ─────────────────────────────────────────────────────────────────────────────
# Startup Watchlist (启动追踪)
# ─────────────────────────────────────────────────────────────────────────────

# Startup Watchlist UI accessible via callback "lu:watch" from the menu
# Also accessible via /startup command

@router.message(Command("startup"))
async def cmd_startup(message: types.Message):
    """View limit-up startup watchlist (启动追踪)."""
    if not await is_allowed(message.from_user.id):
        return
    text, markup = await get_watch_ui(chat_type=message.chat.type)
    await message.answer(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)


@router.callback_query(F.data.startswith("lu:watch"))
async def cb_watch(callback: types.CallbackQuery):
    await safe_answer(callback)
    parts = callback.data.split(":")
    page = int(parts[2]) if len(parts) > 2 else 1
    text, markup = await get_watch_ui(page, chat_type=callback.message.chat.type if callback.message else None)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
    except Exception:
        pass


async def get_watch_ui(page: int = 1, chat_type: Optional[str] = None):
    """Get startup watchlist (一个月内涨停一次的股票)."""
    PAGE_SIZE = 30
    webapp_base = _get_webapp_base(chat_type)
    use_webapp_buttons = bool(webapp_base)
    watchlist = await limit_up_service.get_startup_watchlist()
    
    if not watchlist:
        text = "👀 <b>启动追踪</b>\n━━━━━━━━━━━━━━━━━━━━━\n📭 暂无观察股\n\n<i>一个月内涨停一次的股票会加入观察</i>"
        builder = InlineKeyboardBuilder()
        if use_webapp_buttons:
            builder.row(
                types.InlineKeyboardButton(text="🔄 刷新", callback_data="lu:watch"),
                types.InlineKeyboardButton(text="◀️ 返回", callback_data="lu:main")
            )
        else:
            builder.button(text="🔄 刷新", callback_data="lu:watch")
            builder.button(text="◀️ 返回", callback_data="lu:main")
            builder.adjust(2)
        return text, builder.as_markup()
        
    total = len(watchlist)
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE if total > 0 else 1
    page = max(1, min(page, total_pages))
    
    start_idx = (page - 1) * PAGE_SIZE
    end_idx = start_idx + PAGE_SIZE
    rows = watchlist[start_idx:end_idx]
    
    if not rows:
        text = "👀 <b>启动追踪</b>\n━━━━━━━━━━━━━━━━━━━━━\n📭 暂无数据"
    else:
        text = f"👀 <b>启动追踪</b> ({start_idx+1}-{start_idx+len(rows)}/{total})\n━━━━━━━━━━━━━━━━━━━━━\n<i>一个月涨停一次，再次涨停将剔除</i>\n\n"
        if use_webapp_buttons:
            text += "<i>点击下方按钮查看K线</i>\n"
        else:
            for i, w in enumerate(rows, start_idx + 1):
                name = w.get('name') or w.get('code')
                limit_date = w['first_limit_date'].strftime('%m/%d') if w['first_limit_date'] else ''
                chart_url = get_chart_url(w['code'], name, context="limit_up_watch")
                text += f"{i}. <a href=\"{chart_url}\">{name}</a> ({w['code']}) {limit_date}\n"
    
    builder = InlineKeyboardBuilder()
    if use_webapp_buttons:
        if rows:
            for i, w in enumerate(rows, start_idx + 1):
                limit_date = w['first_limit_date'].strftime('%m/%d') if w['first_limit_date'] else None
                builder.row(
                    _build_webapp_button(
                        w.get('name') or w['code'],
                        w['code'],
                        "limit_up_watch",
                        webapp_base,
                        suffix=limit_date,
                        prefix=f"{i}."
                    )
                )
        nav_buttons = []
        if page > 1:
            nav_buttons.append(types.InlineKeyboardButton(text="◀️ 上一页", callback_data=f"lu:watch:{page-1}"))
        nav_buttons.append(types.InlineKeyboardButton(text="🔄 刷新", callback_data=f"lu:watch:{page}"))
        if page < total_pages:
            nav_buttons.append(types.InlineKeyboardButton(text="下一页 ▶️", callback_data=f"lu:watch:{page+1}"))
        if nav_buttons:
            builder.row(*nav_buttons)
        builder.row(types.InlineKeyboardButton(text="◀️ 返回", callback_data="lu:main"))
    else:
        if page > 1:
            builder.button(text="◀️ 上一页", callback_data=f"lu:watch:{page-1}")
        builder.button(text="🔄 刷新", callback_data=f"lu:watch:{page}")
        if page < total_pages:
            builder.button(text="下一页 ▶️", callback_data=f"lu:watch:{page+1}")
        builder.button(text="◀️ 返回", callback_data="lu:main")
        builder.adjust(3, 1)
    
    return text, builder.as_markup()


# ─────────────────────────────────────────────────────────────────────────────
# Sync Limit-Up
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("sync"))
async def cmd_sync(message: types.Message):
    if not await is_allowed(message.from_user.id):
        return
    
    status = await message.answer("⏳ 正在同步涨停数据...")
    
    try:
        stocks = await limit_up_service.collect_limit_ups()
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📈 查看今日", callback_data="lu:today")
        builder.adjust(1)
        
        await status.edit_text(
            f"✅ 同步完成\n\n📈 涨停股: <b>{len(stocks)}</b>只",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        await status.edit_text(f"❌ 同步失败: {e}")


@router.callback_query(F.data == "lu:sync")
async def cb_lu_sync(callback: types.CallbackQuery):
    await safe_answer(callback, "⏳ 同步中...")
    
    try:
        stocks = await limit_up_service.collect_limit_ups()
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📈 查看今日", callback_data="lu:today")
        builder.button(text="◀️ 返回", callback_data="lu:main")
        builder.adjust(2)
        
        await callback.message.edit_text(
            f"✅ 同步完成\n\n📈 涨停股: <b>{len(stocks)}</b>只",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        await callback.message.edit_text(f"❌ 同步失败: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# AI Stock Scanner
# ─────────────────────────────────────────────────────────────────────────────

# Temporary cache for scan results (store in memory for pagination)
_scan_results_cache = {}

SIGNAL_NAMES = {
    "breakout": "突破信号",
    "kuangbiao": "狂飙启动",
    "startup_candidate": "启动关注",
    "triple_bullish_shrink_breakout": "蓄势爆发",
    "volume": "放量信号",
    "ma_bullish": "多头排列",
    "small_bullish_5": "底部5连阳",
    "volume_price": "量价启动",
    "small_bullish_4": "底部四连阳",
    "small_bullish_4_1_bearish": "四阳一阴",
    "small_bullish_5_1_bearish": "五阳一阴",
    "small_bullish_3_1_bearish_1_bullish": "三阳一阴一阳",
    "small_bullish_5_in_7": "低位七天五阳",
    "small_bullish_6_in_7": "7天六阳",
    "slow_bull_7": "7天慢牛",
    "slow_bull_5": "5天慢牛",
    "strong_first_negative": "强势股首阴",
    "broken_limit_up_streak": "连板断板",
    "pullback_ma5": "5日线回踩",
    "pullback_ma20": "20日线回踩",
    "pullback_ma30": "30日线回踩",
    "pullback_ma5_weekly": "5周线回踩",
    "multi_signal": "🔥多信号共振",
    # New Signal Names (Linear Regression Channel)
    "support_linreg_5": "5日趋势支撑",
    "support_linreg_10": "10日趋势支撑",
    "support_linreg_20": "20日趋势支撑",
    "breakout_linreg_5": "突破5日趋势",
    "breakout_linreg_10": "突破10日趋势",
    "breakout_linreg_20": "突破20日趋势",
    "top_gainers_weekly": "周涨幅榜",
    "top_gainers_half_month": "半月涨幅榜",
    "top_gainers_monthly": "月涨幅榜",
    "top_gainers_weekly_no_lu": "周涨幅(非连板)",
    "top_gainers_half_month_no_lu": "半月涨幅(非连板)",
    "top_gainers_monthly_no_lu": "月涨幅(非连板)",
}

SIGNAL_ICONS = {
    "breakout": "🚀",
    "kuangbiao": "🏎️",
    "startup_candidate": "🛫",
    "triple_bullish_shrink_breakout": "📈",
    "volume": "📊",
    "ma_bullish": "📈",
    "small_bullish_5": "🐜",
    "volume_price": "💰",
    "small_bullish_4": "🐜",
    "small_bullish_4_1_bearish": "📉",
    "small_bullish_5_1_bearish": "📉",
    "small_bullish_3_1_bearish_1_bullish": "📈",
    "small_bullish_5_in_7": "📅",
    "small_bullish_6_in_7": "📅",
    "slow_bull_7": "🐂",
    "slow_bull_5": "🐂",
    "strong_first_negative": "💪",
    "broken_limit_up_streak": "💔",
    "pullback_ma5": "5️⃣",
    "pullback_ma20": "2️⃣",
    "pullback_ma30": "3️⃣",
    "pullback_ma5_weekly": "W️⃣",
    "multi_signal": "🔥",
    "support_linreg_5": "5️⃣",
    "support_linreg_10": "🔟",
    "support_linreg_20": "2️⃣",
    "breakout_linreg_5": "⬆️",
    "breakout_linreg_10": "⬆️",
    "breakout_linreg_20": "⬆️",
    "top_gainers_weekly": "🗓️",
    "top_gainers_half_month": "🌓",
    "top_gainers_monthly": "🌕",
    "top_gainers_weekly_no_lu": "🗓️",
    "top_gainers_half_month_no_lu": "🌓",
    "top_gainers_monthly_no_lu": "🌕",
}


@router.callback_query(F.data == "scanner:main")
async def cb_scanner_main(callback: types.CallbackQuery):
    """Signal scanner main menu (independent from limit-up tracking)."""
    await safe_answer(callback)
    
    # Get database stats for display
    from app.services.stock_history import stock_history_service
    stats = await stock_history_service.get_stats()
    
    stock_count = stats.get('stock_count', 0) if stats else 0
    max_date = stats.get('max_date', 'N/A') if stats else 'N/A'
    
    text = (
        "🔍 <b>信号扫描</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 本地数据: <b>{stock_count}</b> 只股票\n"
        f"📅 数据日期: <b>{max_date}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<i>基于本地历史K线数据扫描技术信号</i>\n"
    )
    
    builder = InlineKeyboardBuilder()
    # New Signals (Hot)
    builder.button(text="🚀 启动关注", callback_data="scanner:scan:startup_candidate")
    builder.button(text="🏎️ 狂飙启动", callback_data="scanner:scan:kuangbiao")
    builder.button(text="🔥 蓄势爆发", callback_data="scanner:scan:triple_bullish_shrink_breakout")

    # 2 columns for signals
    builder.button(text="🔺 突破信号", callback_data="scanner:scan:breakout")
    builder.button(text="📊 放量信号", callback_data="scanner:scan:volume")
    builder.button(text="📈 多头排列", callback_data="scanner:scan:ma_bullish")
    builder.button(text="🌅 底部5连阳", callback_data="scanner:scan:small_bullish_5")
    builder.button(text="🚀 量价启动", callback_data="scanner:scan:volume_price")
    builder.button(text="⭐ 多信号共振", callback_data="scanner:scan:multi_signal")
    builder.button(text="🔥 底部四连阳", callback_data="scanner:scan:small_bullish_4")
    builder.button(text="📉 四阳一阴", callback_data="scanner:scan:small_bullish_4_1_bearish")
    builder.button(text="📉 五阳一阴", callback_data="scanner:scan:small_bullish_5_1_bearish")
    builder.button(text="📈 三阳一阴一阳", callback_data="scanner:scan:small_bullish_3_1_bearish_1_bullish")
    builder.button(text="🌤️ 七天五阳", callback_data="scanner:scan:small_bullish_5_in_7")
    builder.button(text="🌤️ 7天六阳", callback_data="scanner:scan:small_bullish_6_in_7")
    builder.button(text="🐂 7天慢牛", callback_data="scanner:scan:slow_bull_7")
    builder.button(text="🐂 5天慢牛", callback_data="scanner:scan:slow_bull_5")
    builder.button(text="🟢 强势股首阴", callback_data="scanner:scan:strong_first_negative")
    builder.button(text="💔 连板断板", callback_data="scanner:scan:broken_limit_up_streak")
    builder.button(text="↩️ 5日线回踩", callback_data="scanner:scan:pullback_ma5")
    builder.button(text="🔄 20日线回踩", callback_data="scanner:scan:pullback_ma20")
    builder.button(text="🔙 30日线回踩", callback_data="scanner:scan:pullback_ma30")
    builder.button(text="📅 5周线回踩", callback_data="scanner:scan:pullback_ma5_weekly")
    
    # New Trend Signals (LinReg)
    builder.button(text="5️⃣ 5日趋势支撑", callback_data="scanner:scan:support_linreg_5")
    builder.button(text="🔟 10日趋势支撑", callback_data="scanner:scan:support_linreg_10")
    builder.button(text="2️⃣ 20日趋势支撑", callback_data="scanner:scan:support_linreg_20")
    builder.button(text="⬆️ 突破5日趋势", callback_data="scanner:scan:breakout_linreg_5")
    builder.button(text="⬆️ 突破10日趋势", callback_data="scanner:scan:breakout_linreg_10")
    builder.button(text="⬆️ 突破20日趋势", callback_data="scanner:scan:breakout_linreg_20")

    # Top Gainers
    builder.button(text="🔥 每周涨幅", callback_data="scanner:scan:top_gainers_weekly")
    builder.button(text="🔥 半月涨幅", callback_data="scanner:scan:top_gainers_half_month")
    builder.button(text="🔥 每月涨幅", callback_data="scanner:scan:top_gainers_monthly")
    builder.button(text="🛡️ 每周(无板)", callback_data="scanner:scan:top_gainers_weekly_no_lu")
    builder.button(text="🛡️ 半月(无板)", callback_data="scanner:scan:top_gainers_half_month_no_lu")
    builder.button(text="🛡️ 月度(无板)", callback_data="scanner:scan:top_gainers_monthly_no_lu")
    
    # Control buttons
    builder.button(text="🔍 全部扫描", callback_data="scanner:scan:all")
    builder.button(text="⚡ 强制扫描", callback_data="scanner:scan:force")
    builder.button(text="📊 数据库状态", callback_data="scanner:dbcheck")
    builder.button(text="🔄 同步数据", callback_data="scanner:dbsync")
    builder.button(text="◀️ 返回", callback_data="main")
    
    # Layout: 2 cols for signals, then 2, 2, 1
    # Layout: 2 cols for signals, then 2, 2, 1
    # Original: 2, 2, 2, 3, 3, 3, 3, 2, 1
    # Added 6 buttons (3 rows of 2 or 2 rows of 3)
    # Let's use 3 columns for the new ones
    # Layout: 3 cols for new signals, then 2, 2, ...
    # Layout: 3 cols for new signals, then 2, 2, ...
    # Added 2 more buttons (7天六阳, 7天慢牛)
    # Adjust layout: 3, 2, 2, 2, 3, 3, 3, 3, 3, 3, 2, 1 -> 3, 2, 2, 2, 3, 3, 3, 3, 3, 3, 2, 1
    # Wait, let's count.
    # New: 3
    # 2 cols: 6 (breakout, volume, ma_bullish, small_bullish_5, volume_price, multi_signal) -> 3 rows of 2
    # 2 cols: 4 (small_bullish_4, 4_1, 5_1, 3_1_1) -> 2 rows of 2
    # 2 cols: 4 (5_in_7, 6_in_7, slow_bull_7, strong_first_negative) -> 2 rows of 2
    # 2 cols: 6 (broken, pb5, pb20, pb30, pb5w) -> Wait, broken is 1. pb are 4.
    # broken, pb5, pb20, pb30, pb5w -> 5 buttons.
    # LinReg: 6 buttons.
    # Gainers: 6 buttons.
    # Control: 5 buttons.
    
    # Let's just use a simpler layout strategy or keep adjusting.
    # 3 (new)
    # 2, 2, 2 (6 signals)
    # 2, 2 (4 signals)
    # 2, 2 (4 signals: 5in7, 6in7, slow7, strong)
    # 2, 2, 1 (5 signals: broken, pb5, pb20, pb30, pb5w) -> broken, pb5 | pb20, pb30 | pb5w
    # 3, 3 (6 LinReg)
    # 3, 3 (6 Gainers)
    # 2, 1 (Control: all, force | dbcheck, dbsync | back) -> 2, 2, 1
    
    # Layout: 3 cols for new signals, then 2, 2, ...
    # Added 3 more buttons (7天六阳, 7天慢牛, 5天慢牛)
    # Adjust layout: 3, 2, 2, 2, 3, 3, 3, 3, 3, 3, 2, 1 -> 3, 2, 2, 2, 3, 3, 3, 3, 3, 3, 2, 1
    # Wait, let's count.
    # New: 3
    # 2 cols: 6 (breakout, volume, ma_bullish, small_bullish_5, volume_price, multi_signal) -> 3 rows of 2
    # 2 cols: 4 (small_bullish_4, 4_1, 5_1, 3_1_1) -> 2 rows of 2
    # 2 cols: 5 (5_in_7, 6_in_7, slow_bull_7, slow_bull_5, strong_first_negative) -> 2 rows of 2, then 1?
    # Or make it 3 cols for these?
    # Let's try to group them nicely.
    # 5_in_7, 6_in_7, slow_bull_7, slow_bull_5, strong_first_negative
    # Maybe 3, 2?
    # 5_in_7, 6_in_7, slow_bull_7
    # slow_bull_5, strong_first_negative
    
    # Current layout: 3, 2, 2, 2, 2, 2, 2, 2, 2, 1, 3, 3, 3, 3, 2, 2, 1
    # The 5th group (lines 1221-1225) now has 5 buttons.
    # So we change the 5th '2' to '3' and '2'.
    # 3, 2, 2, 2, 3, 2, 2, 2, 2, 1, 3, 3, 3, 3, 2, 2, 1
    
    builder.adjust(3, 2, 2, 2, 3, 2, 2, 2, 2, 1, 3, 3, 3, 3, 2, 2, 1)
    
    try:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())
    except Exception:
        pass


async def _run_scan_from_callback(callback: types.CallbackQuery, force: bool = False, signal_type: str = "all"):
    """Trigger stock signal scan from callback."""
    await safe_answer(callback, "扫描中...")

    class MockMessage:
        def __init__(self, msg):
            self.from_user = callback.from_user
            self._msg = msg
            self.chat = msg.chat if msg else None

        async def answer(self, text, **kwargs):
            return await self._msg.answer(text, **kwargs)

    mock_msg = MockMessage(callback.message)
    await cmd_scan(mock_msg, force=force, signal_type=signal_type)


@router.callback_query(F.data.startswith("scanner:scan"))
async def cb_scanner_scan(callback: types.CallbackQuery):
    """Trigger stock signal scan (specific or all)."""
    # Parse signal type from callback data
    # scanner:scan (default all)
    # scanner:scan:breakout
    # scanner:scan:all
    # scanner:scan:force
    
    parts = callback.data.split(":")
    signal_type = parts[2] if len(parts) > 2 else "all"
    force = signal_type == "force"
    
    if signal_type == "force":
        signal_type = "all"
        
    await _run_scan_from_callback(callback, force=force, signal_type=signal_type)


@router.callback_query(F.data == "scanner:scan:force")
async def cb_scanner_scan_force(callback: types.CallbackQuery):
    """Trigger stock signal scan (force)."""
    await _run_scan_from_callback(callback, force=True)


@router.callback_query(F.data == "scanner:dbcheck")
async def cb_scanner_dbcheck(callback: types.CallbackQuery):
    """Show database status from scanner menu."""
    await safe_answer(callback)
    
    from app.services.stock_history import stock_history_service
    
    try:
        stats = await stock_history_service.get_stats()
        
        if not stats:
            await callback.message.answer("❌ 数据库未连接")
            return
        
        total_records = stats.get('total_records', 0)
        stock_count = stats.get('stock_count', 0)
        min_date = stats.get('min_date')
        max_date = stats.get('max_date')
        
        today = china_today()
        days_old = (today - max_date).days if max_date else 999
        freshness = "✅ 最新" if days_old <= 1 else f"⚠️ {days_old}天前"
        
        recent_count = 0
        if db.pool:
            recent_count = await db.pool.fetchval("""
                SELECT COUNT(DISTINCT code) 
                FROM stock_history 
                WHERE date >= $1::date - INTERVAL '7 days'
            """, today) or 0
        
        text = (
            "📊 <b>stock_history 数据库状态</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📁 总记录数: <b>{total_records:,}</b>\n"
            f"📈 股票数量: <b>{stock_count}</b>\n"
            f"📅 数据范围: {min_date} ~ {max_date}\n"
            f"🕐 数据新鲜度: {freshness}\n"
            f"⏱️ 近7天数据: <b>{recent_count}</b> 只股票\n"
        )
        
        if recent_count == 0:
            text += "\n⚠️ <b>问题:</b> 近7天无数据，信号扫描将无法工作"
            text += "\n💡 <b>建议:</b> 点击同步数据"
        elif days_old > 3:
            text += "\n⚠️ <b>建议:</b> 数据较旧，建议同步"
        else:
            text += "\n✅ 数据库状态良好"
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 同步数据", callback_data="scanner:dbsync")
        builder.button(text="◀️ 返回", callback_data="scanner:main")
        builder.adjust(2)
        
        await callback.message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())
        
    except Exception as e:
        await callback.message.answer(f"❌ 检查失败: {e}")


@router.callback_query(F.data == "scanner:dbsync")
async def cb_scanner_dbsync(callback: types.CallbackQuery, bot: Bot):
    """Trigger database sync from scanner menu."""
    if not await is_allowed(callback.from_user.id):
        await safe_answer(callback, "无权限")
        return
    
    await safe_answer(callback)
    
    import asyncio
    from app.services.stock_history import stock_history_service
    
    chat_id = callback.message.chat.id
    
    def make_progress_callback():
        last_time = [0.0]  # Use list for mutable closure
        async def progress_cb(stage: str, current: int, total: int, message: str):
            now = time.time()
            if now - last_time[0] < 10 and current < total:
                return  # Rate limit: at most once per 10 seconds
            last_time[0] = now
            try:
                await bot.send_message(chat_id, message, parse_mode="HTML")
            except Exception:
                pass
        return progress_cb
    
    try:
        await callback.message.answer("⏳ 正在后台同步数据（含完整性检查）...\n\n会定时推送进度通知")
        
        asyncio.create_task(stock_history_service.sync_with_integrity_check(make_progress_callback()))
        
    except Exception as e:
        await callback.message.answer(f"❌ 同步失败: {e}")


@router.message(Command("dbcheck"))
async def cmd_dbcheck(message: types.Message):
    """Check stock_history database status (non-blocking)."""
    if not await is_allowed(message.from_user.id):
        return
    
    from app.services.stock_history import stock_history_service
    
    status = await message.answer("⏳ 检查数据库状态...")
    
    try:
        # Get database stats (fast local query)
        stats = await stock_history_service.get_stats()
        
        if not stats:
            await status.edit_text("❌ 数据库未连接")
            return
        
        total_records = stats.get('total_records', 0)
        stock_count = stats.get('stock_count', 0)
        min_date = stats.get('min_date')
        max_date = stats.get('max_date')
        
        # Use local database count (no external API call)
        # total_available = stock_count  # What we have is what we show
        
        # Check freshness
        today = china_today()
        days_old = (today - max_date).days if max_date else 999
        freshness = "✅ 最新" if days_old <= 1 else f"⚠️ {days_old}天前"
        
        # Get recent data count
        recent_count = 0
        if db.pool:
            recent_count = await db.pool.fetchval("""
                SELECT COUNT(DISTINCT code) 
                FROM stock_history 
                WHERE date >= $1::date - INTERVAL '7 days'
            """, today) or 0
        
        text = (
            "📊 <b>stock_history 数据库状态</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📁 总记录数: <b>{total_records:,}</b>\n"
            f"📈 股票数量: <b>{stock_count}</b>\n"
            f"📅 数据范围: {min_date} ~ {max_date}\n"
            f"🕐 数据新鲜度: {freshness}\n"
            f"⏱️ 近7天数据: <b>{recent_count}</b> 只股票\n"
        )
        
        # Add recommendations
        if recent_count == 0:
            text += "\n⚠️ <b>问题:</b> 近7天无数据，信号扫描将无法工作"
            text += "\n💡 <b>建议:</b> 执行 /dbsync 同步数据"
        # elif coverage < 50:
        #     text += "\n⚠️ <b>建议:</b> 执行 /dbsync 填充缺失数据"
        elif days_old > 3:
            text += "\n⚠️ <b>建议:</b> 执行 /dbsync 更新陈旧数据"
        else:
            text += "\n✅ 数据库状态良好"
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 立即同步", callback_data="db:sync")
        builder.button(text="◀️ 返回", callback_data="main")
        builder.adjust(2)
        
        await status.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
        
    except Exception as e:
        await status.edit_text(f"❌ 检查失败: {e}")


@router.message(Command("dbsync"))
async def cmd_dbsync(message: types.Message, bot: Bot):
    """Sync stock history data to local database with progress notifications."""
    if not await is_allowed(message.from_user.id):
        return
    
    import asyncio
    from app.services.stock_history import stock_history_service
    
    chat_id = message.chat.id
    
    status_msg = await message.answer("⏳ 正在后台同步数据（含完整性检查）...\n\n会定时推送进度通知")
    
    def make_progress_callback(msg_obj):
        last_time = [0.0]  # Use list for mutable closure
        async def progress_cb(stage: str, current: int, total: int, msg: str):
            now = time.time()
            if now - last_time[0] < 1.5 and current < total:
                return  # Rate limit: at most once per 1.5 seconds
            last_time[0] = now
            
            # Calculate percentage and bar
            percent = int(current / total * 100) if total > 0 else 0
            progress_bar = "▓" * (percent // 10) + "░" * (10 - (percent // 10))
            
            # Format message with bar
            formatted_msg = (
                f"{msg}\n"
                f"⏳ 进度: {percent}% ({current}/{total})\n"
                f"{progress_bar}"
            )
            
            try:
                if formatted_msg != msg_obj.text:
                    await msg_obj.edit_text(formatted_msg, parse_mode="HTML")
            except Exception as e:
                # Ignore "message is not modified" errors
                if "message is not modified" in str(e).lower():
                    pass
                else:
                    logger.error(f"Failed to update progress message: {e}")
        return progress_cb
    
    # Trigger sync with progress callback
    asyncio.create_task(stock_history_service.sync_with_integrity_check(make_progress_callback(status_msg)))


@router.callback_query(F.data == "db:sync")
async def cb_db_sync(callback: types.CallbackQuery, bot: Bot):
    """Trigger database sync (callback version) with progress notifications."""
    if not await is_allowed(callback.from_user.id):
        await safe_answer(callback, "无权限")
        return
    
    await safe_answer(callback)
    
    import asyncio
    from app.services.stock_history import stock_history_service
    
    chat_id = callback.message.chat.id
    
    def make_progress_callback(msg_obj):
        last_time = [0.0]
        async def progress_cb(stage: str, current: int, total: int, msg: str):
            now = time.time()
            if now - last_time[0] < 1.5 and current < total:
                return
            last_time[0] = now
            
            # Calculate percentage and bar
            percent = int(current / total * 100) if total > 0 else 0
            progress_bar = "▓" * (percent // 10) + "░" * (10 - (percent // 10))
            
            # Format message with bar
            formatted_msg = (
                f"{msg}\n"
                f"⏳ 进度: {percent}% ({current}/{total})\n"
                f"{progress_bar}"
            )
            
            try:
                if formatted_msg != msg_obj.text:
                    await msg_obj.edit_text(formatted_msg, parse_mode="HTML")
            except Exception as e:
                # Ignore "message is not modified" errors
                if "message is not modified" in str(e).lower():
                    pass
                else:
                    logger.error(f"Failed to update progress message: {e}")
        return progress_cb
    
    try:
        await callback.message.edit_text("⏳ 正在后台同步数据（含完整性检查）...\n\n会定时推送进度通知")
        
        asyncio.create_task(stock_history_service.sync_with_integrity_check(make_progress_callback(callback.message)))
        
    except Exception as e:
        await callback.message.edit_text(f"❌ 同步失败: {e}")


@router.message(Command("scan"))
async def cmd_scan(message: types.Message, command: CommandObject = None, force: bool = False, signal_type: str = "all"):
    if not await is_allowed(message.from_user.id):
        return
    
    user_id = message.from_user.id if hasattr(message, 'from_user') else 0
    _scan_results_cache.pop(user_id, None)
    chat_type = message.chat.type if message.chat else None

    if not force and command and command.args:
        arg = command.args.strip().lower()
        force = arg in ("force", "f", "强制")

    status = await message.answer(f"🔍 正在扫描... ({SIGNAL_NAMES.get(signal_type, '全部')})\n\n⏳ 准备中...")
    sender = status
    
    import time
    last_update_time = time.time()
    
    async def on_progress(current, total):
        nonlocal last_update_time
        # Throttle updates: max one update every 1.5 seconds
        now = time.time()
        if now - last_update_time < 1.5 and current < total:
            return
            
        last_update_time = now
        percent = int(current / total * 100)
        progress_bar = "▓" * (percent // 10) + "░" * (10 - (percent // 10))
        
        try:
            await status.edit_text(
                f"🔍 正在扫描... ({SIGNAL_NAMES.get(signal_type, '全部')})\n\n"
                f"⏳ 进度: {percent}% ({current}/{total})\n"
                f"{progress_bar}"
            )
        except Exception:
            pass # Ignore message not modified errors

    try:
        signals = await stock_scanner.scan_all_stocks(force=force, progress_callback=on_progress)
        
        if not signals or all(len(v) == 0 for v in signals.values()):
            cache_note = "\n\n♻️ 使用缓存结果（数据库未更新）" if stock_scanner.last_scan_used_cache else ""
            await status.answer(f"🔍 扫描完成\n\n📭 暂无信号{cache_note}")
            return
        
        # Cache results for pagination
        _scan_results_cache[user_id] = signals
        
        # Helper to send complete stock list in multiple messages if needed
        async def send_signal_list(title: str, stocks: list, context: str = None, page: int = 1, page_size: int = 20, message_to_edit: types.Message = None):
            """Send list with pagination."""
            if not stocks:
                return
            
            total_stocks = len(stocks)
            total_pages = (total_stocks + page_size - 1) // page_size
            
            # Ensure page is valid
            if page < 1:
                page = 1
            if page > total_pages:
                page = total_pages
            
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            current_page_stocks = stocks[start_idx:end_idx]
            
            webapp_base = _get_webapp_base(chat_type)
            use_webapp_buttons = bool(webapp_base)

            # Build message text
            lines = [f"{title} (第 {page}/{total_pages} 页)", ""]
            if use_webapp_buttons:
                lines.append("<i>点击下方按钮查看K线</i>")
            else:
                for i, s in enumerate(current_page_stocks, start_idx + 1):
                    name = s.get('name') or s.get('code')
                    chart_url = get_chart_url(s['code'], name, context=context)
                    line = f"{i}. <a href=\"{chart_url}\">{name}</a> ({s['code']})"
                    lines.append(line)
            
            text = "\n".join(lines)
            
            # Build pagination keyboard
            builder = InlineKeyboardBuilder()
            if use_webapp_buttons:
                for i, s in enumerate(current_page_stocks, start_idx + 1):
                    suffix = None
                    if s.get("signal_count"):
                        suffix = f"{s['signal_count']}信号"
                    builder.row(
                        _build_webapp_button(
                            s.get('name') or s['code'],
                            s['code'],
                            context or "scanner",
                            webapp_base,
                            suffix=suffix,
                            prefix=f"{i}."
                        )
                    )
            
            # Navigation buttons
            nav_buttons = []
            if page > 1:
                nav_buttons.append(types.InlineKeyboardButton(text="⬅️ 上一页", callback_data=f"scanner:page:{context}:{page-1}"))
            if page < total_pages:
                nav_buttons.append(types.InlineKeyboardButton(text="下一页 ➡️", callback_data=f"scanner:page:{context}:{page+1}"))
            
            if nav_buttons:
                builder.row(*nav_buttons)
            
            builder.row(types.InlineKeyboardButton(text="◀️ 返回菜单", callback_data="scanner:main"))

            await sender.answer(text, parse_mode="HTML", reply_markup=builder.as_markup(), disable_web_page_preview=True)
        
        # Send summary header
        total_signals = sum(len(v) for v in signals.values())
        cache_note = "♻️ 使用缓存结果（数据库未更新）\n\n" if stock_scanner.last_scan_used_cache else ""
        summary = (
            "🔍 <b>启动信号扫描完成</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{cache_note}"
        )
        for sig_type, stocks in signals.items():
            # Filter if specific type requested
            if signal_type != "all" and sig_type != signal_type:
                continue
                
            if stocks:
                icon = SIGNAL_ICONS.get(sig_type, "•")
                name = SIGNAL_NAMES.get(sig_type, sig_type)
                summary += f"{icon} {name}: <b>{len(stocks)}只</b>\n"
        summary += f"\n共 <b>{total_signals}</b> 个信号"
        
        summary_builder = InlineKeyboardBuilder()
        summary_builder.button(text="◀️ 返回菜单", callback_data="scanner:main")
        await status.answer(summary, parse_mode="HTML", reply_markup=summary_builder.as_markup())
        
        # Send complete list for each signal type
        for sig_type, stocks in signals.items():
            # Filter if specific type requested
            if signal_type != "all" and sig_type != signal_type:
                continue
                
            if stocks:
                icon = SIGNAL_ICONS.get(sig_type, "•")
                name = SIGNAL_NAMES.get(sig_type, sig_type)
                await send_signal_list(
                    f"{icon} <b>{name}</b> ({len(stocks)}只)", 
                    stocks, 
                    context=f"scanner_{sig_type}"
                )
            
    except Exception as e:
        await status.answer(f"❌ 扫描失败: {e}")


@router.callback_query(F.data.startswith("scanner:page:"))
async def cb_scanner_page(callback: types.CallbackQuery):
    """Handle scanner pagination."""
    try:
        # Format: scanner:page:context:page_num
        # context is like "scanner_signal_type"
        parts = callback.data.split(":")
        if len(parts) < 4:
            await callback.answer("无效请求")
            return
            
        context = parts[2]
        page = int(parts[3])
        
        # Extract signal type from context (scanner_xxx)
        signal_type = context.replace("scanner_", "")
        
        user_id = callback.from_user.id
        if user_id not in _scan_results_cache:
            await callback.answer("⚠️ 结果已过期，请重新扫描", show_alert=True)
            return
            
        signals = _scan_results_cache[user_id]
        if signal_type not in signals:
            await callback.answer("⚠️ 无此信号数据", show_alert=True)
            return
            
        stocks = signals[signal_type]
        icon = SIGNAL_ICONS.get(signal_type, "•")
        name = SIGNAL_NAMES.get(signal_type, signal_type)
        title = f"{icon} <b>{name}</b> ({len(stocks)}只)"
        
        # We need to access send_signal_list logic. 
        # Since it's a local function in cmd_scan, we should refactor it or duplicate logic.
        # For simplicity/speed, let's duplicate the pagination logic here or make it a standalone helper.
        # But wait, send_signal_list was defined inside cmd_scan. I should probably move it out.
        # Refactoring to move send_signal_list out is better.
        
        await _send_signal_list_paginated(
            callback.message,
            title,
            stocks,
            context=context,
            page=page,
            message_to_edit=None,
            chat_type=callback.message.chat.type if callback.message else None
        )
        await callback.answer()
        
    except Exception as e:
        await callback.answer(f"❌ 错误: {e}", show_alert=True)

async def _send_signal_list_paginated(
    sender_or_message,
    title: str,
    stocks: list,
    context: str = None,
    page: int = 1,
    page_size: int = 20,
    message_to_edit: types.Message = None,
    chat_type: Optional[str] = None,
):
    """Send list with pagination (Shared helper)."""
    if not stocks:
        return
    
    total_stocks = len(stocks)
    total_pages = (total_stocks + page_size - 1) // page_size
    
    # Ensure page is valid
    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages
    
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    current_page_stocks = stocks[start_idx:end_idx]
    
    webapp_base = _get_webapp_base(chat_type)
    use_webapp_buttons = bool(webapp_base)

    # Build message text
    lines = [f"{title} (第 {page}/{total_pages} 页)", ""]
    if use_webapp_buttons:
        lines.append("<i>点击下方按钮查看K线</i>")
    else:
        for i, s in enumerate(current_page_stocks, start_idx + 1):
            name = s.get('name') or s.get('code')
            chart_url = get_chart_url(s['code'], name, context=context)
            line = f"{i}. <a href=\"{chart_url}\">{name}</a> ({s['code']})"
            lines.append(line)
    
    text = "\n".join(lines)
    
    # Build pagination keyboard
    builder = InlineKeyboardBuilder()
    
    if use_webapp_buttons:
        for i, s in enumerate(current_page_stocks, start_idx + 1):
            suffix = None
            if s.get("signal_count"):
                suffix = f"{s['signal_count']}信号"
            builder.row(
                _build_webapp_button(
                    s.get('name') or s['code'],
                    s['code'],
                    context or "scanner",
                    webapp_base,
                    suffix=suffix,
                    prefix=f"{i}."
                )
            )

    # Navigation buttons
    nav_buttons = []
    if page > 1:
        nav_buttons.append(types.InlineKeyboardButton(text="⬅️ 上一页", callback_data=f"scanner:page:{context}:{page-1}"))
    if page < total_pages:
        nav_buttons.append(types.InlineKeyboardButton(text="下一页 ➡️", callback_data=f"scanner:page:{context}:{page+1}"))
    
    if nav_buttons:
        builder.row(*nav_buttons)
    
    builder.row(types.InlineKeyboardButton(text="◀️ 返回菜单", callback_data="scanner:main"))

    if isinstance(sender_or_message, types.Message):
        await sender_or_message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup(), disable_web_page_preview=True)


# ─────────────────────────────────────────────────────────────────────────────
# Stock History Command
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("history"))
async def cmd_history(message: types.Message, command: CommandObject):
    """Check stock history data."""
    if not await is_allowed(message.from_user.id):
        return
    
    code = command.args
    if not code:
        await message.answer(
            "📜 <b>Stock History</b>\n\n"
            "Usage: <code>/history &lt;code&gt;</code>\n"
            "Example: <code>/history 600519</code>",
            parse_mode="HTML"
        )
        return
    
    from app.services.stock_history import stock_history_service
    
    code = code.strip()
    history = await stock_history_service.get_stock_history(code, days=10)
    
    if not history:
        await message.answer(f"❌ No history found for <code>{code}</code>", parse_mode="HTML")
        return
    
    # Format as table
    text = f"📜 <b>HISTORY: {code}</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
    text += "<code>Date       Close   Chg%   Vol</code>\n"
    
    for h in history:
        date_str = h['date'].strftime("%m-%d")
        close = h['close']
        pct = h['change_pct']
        vol = h['volume'] / 10000  # 万手
        
        # Color for change
        # icon = "🔴" if pct > 0 else "🟢" if pct < 0 else "⚪"
        
        text += f"{date_str}  {close:>6.2f}  {pct:>5.2f}%  {vol:>4.0f}万\n"
    
    await message.answer(text, parse_mode="HTML")


# ─────────────────────────────────────────────────────────────────────────────
# Interactive Chart (Mini App)
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("chart"))
async def cmd_chart(message: types.Message, command: CommandObject):
    """Open interactive candlestick chart as Telegram Mini App."""
    if not await is_allowed(message.from_user.id):
        return
    
    code = command.args
    if not code:
        await message.answer(
            "📈 <b>Interactive Chart</b>\n\n"
            "Usage: <code>/chart &lt;code&gt;</code>\n"
            "Example: <code>/chart 600519</code>\n\n"
            "<i>Opens an interactive candlestick chart with zoom/pan</i>",
            parse_mode="HTML"
        )
        return
    
    code = code.strip()
    
    # Build Mini App URL (prefer WebApp button to avoid confirmation dialog)
    webapp_url = None
    if settings.WEBFRONT_URL:
        webapp_url = f"{settings.WEBFRONT_URL.rstrip('/')}/miniapp/chart/?code={code}"
    else:
        webapp_url = get_chart_url(code)

    # Create button (WebApp opens inline without confirmation when configured)
    builder = InlineKeyboardBuilder()
    if settings.WEBFRONT_URL:
        builder.button(text="📈 Open Chart", web_app=types.WebAppInfo(url=webapp_url))
    else:
        builder.button(text="📈 Open Chart", url=webapp_url)
    builder.button(text="📜 History", callback_data=f"history:{code}")
    builder.adjust(1)
    
    await message.answer(
        f"📈 <b>Chart: {code}</b>\n\n"
        f"Click below to open interactive chart:",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )


@router.callback_query(F.data == "lu:scan")
async def cb_scan(callback: types.CallbackQuery):
    await _run_scan_from_callback(callback, force=False)


@router.callback_query(F.data.startswith("scan:list:"))
async def cb_scan_list(callback: types.CallbackQuery):
    """View paginated list of scan results for a signal type."""
    await safe_answer(callback)
    
    parts = callback.data.split(":")
    signal_type = parts[2]
    page = int(parts[3]) if len(parts) > 3 else 0
    
    user_id = callback.from_user.id
    signals = _scan_results_cache.get(user_id, {})
    stocks = signals.get(signal_type, [])
    
    if not stocks:
        await callback.answer("暂无数据，请重新扫描")
        return
    
    # Pagination settings
    per_page = 15
    total_pages = (len(stocks) + per_page - 1) // per_page
    page = max(0, min(page, total_pages - 1))
    
    start = page * per_page
    end = start + per_page
    page_stocks = stocks[start:end]
    
    icon = SIGNAL_ICONS.get(signal_type, "•")
    name = SIGNAL_NAMES.get(signal_type, signal_type)
    
    text = f"{icon} <b>{name}</b> ({len(stocks)}只)\n"
    text += "━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"<i>第 {page + 1}/{total_pages} 页</i>\n\n"
    chat_type = callback.message.chat.type if callback.message else None
    webapp_base = _get_webapp_base(chat_type)
    use_webapp_buttons = bool(webapp_base)
    context = f"scanner_{signal_type}"

    if use_webapp_buttons:
        text += "<i>点击下方按钮查看K线</i>\n"
    else:
        for i, s in enumerate(page_stocks, start + 1):
            name = s.get('name') or s.get('code')
            chart_url = get_chart_url(s['code'], name, context=context)
            text += f"{i}. <a href=\"{chart_url}\">{name}</a> ({s['code']})\n"
    
    builder = InlineKeyboardBuilder()
    if use_webapp_buttons:
        for i, s in enumerate(page_stocks, start + 1):
            suffix = None
            if s.get("signal_count"):
                suffix = f"{s['signal_count']}信号"
            builder.row(
                _build_webapp_button(
                    s.get('name') or s['code'],
                    s['code'],
                    context,
                    webapp_base,
                    suffix=suffix,
                    prefix=f"{i}."
                )
            )
    
    # Pagination buttons
    if use_webapp_buttons:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(types.InlineKeyboardButton(text="⬅️ 上一页", callback_data=f"scan:list:{signal_type}:{page-1}"))
        if page < total_pages - 1:
            nav_buttons.append(types.InlineKeyboardButton(text="➡️ 下一页", callback_data=f"scan:list:{signal_type}:{page+1}"))
        if nav_buttons:
            builder.row(*nav_buttons)
        builder.row(
            types.InlineKeyboardButton(text="◀️ 返回扫描", callback_data="scan:back"),
            types.InlineKeyboardButton(text="◀️ 返回菜单", callback_data="scanner:main")
        )
    else:
        if page > 0:
            builder.button(text="⬅️ 上一页", callback_data=f"scan:list:{signal_type}:{page-1}")
        if page < total_pages - 1:
            builder.button(text="➡️ 下一页", callback_data=f"scan:list:{signal_type}:{page+1}")
        
        builder.button(text="◀️ 返回扫描", callback_data="scan:back")
        builder.button(text="◀️ 返回菜单", callback_data="scanner:main")
        builder.adjust(2, 1, 1)
    
    try:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup(), disable_web_page_preview=True)
    except Exception:
        pass


@router.callback_query(F.data == "scan:back")
async def cb_scan_back(callback: types.CallbackQuery):
    """Return to scan results summary."""
    await safe_answer(callback)
    
    user_id = callback.from_user.id
    signals = _scan_results_cache.get(user_id, {})
    
    if not signals or all(len(v) == 0 for v in signals.values()):
        # No cached results, trigger new scan
        await callback.message.answer("📭 缓存已失效，请重新扫描")
        return
    
    chat_type = callback.message.chat.type if callback.message else None
    webapp_base = _get_webapp_base(chat_type)
    use_webapp_buttons = bool(webapp_base)

    text = "🔍 <b>启动信号扫描</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    for signal_type, stocks in signals.items():
        if not stocks:
            continue
        
        icon = SIGNAL_ICONS.get(signal_type, "•")
        name = SIGNAL_NAMES.get(signal_type, signal_type)
        
        text += f"{icon} <b>{name}</b> ({len(stocks)})\n"
        if not use_webapp_buttons:
            for s in stocks[:5]:
                name_label = s.get('name') or s.get('code')
                chart_url = get_chart_url(s['code'], name_label)
                text += f"  • <a href=\"{chart_url}\">{name_label}</a> ({s['code']})\n"
            if len(stocks) > 5:
                text += f"  <i>...及其他 {len(stocks) - 5} 只</i>\n"
        text += "\n"

    if use_webapp_buttons:
        text += "<i>点击下方按钮查看对应列表</i>\n"
    
    builder = InlineKeyboardBuilder()
    for signal_type, stocks in signals.items():
        if stocks:
            name = SIGNAL_NAMES.get(signal_type, signal_type)
            builder.button(text=f"📋 {name}全部", callback_data=f"scan:list:{signal_type}:0")
    builder.button(text="🔄 重新扫描", callback_data="scanner:scan")
    builder.button(text="◀️ 返回", callback_data="scanner:main")
    builder.adjust(2, 2, 2)
    
    try:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup(), disable_web_page_preview=True)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# 板块分析 (Sector Analysis)
# ═══════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "sector:main")
async def cb_sector_main(callback: types.CallbackQuery):
    await safe_answer(callback)
    
    text = (
        "📊 <b>板块分析</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🏭 行业板块 + 💡概念板块\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "<i>每日16:05自动收集</i>"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🏭 行业板块", callback_data="sector:industry")
    builder.button(text="💡 概念板块", callback_data="sector:concept")
    builder.button(text="🔥 7日强势", callback_data="sector:hot:7")
    builder.button(text="📈 14日强势", callback_data="sector:hot:14")
    builder.button(text="📊 30日强势", callback_data="sector:hot:30")
    builder.button(text="📉 弱势板块", callback_data="sector:weak")
    builder.button(text="📋 今日日报", callback_data="sector:report")
    builder.button(text="🔄 同步数据", callback_data="sector:sync")
    builder.button(text="◀️ 返回", callback_data="main")
    builder.adjust(2, 3, 2, 2)
    
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Industry Sectors (行业板块)
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("industry"))
async def cmd_industry(message: types.Message):
    if not await is_allowed(message.from_user.id):
        return
    text, markup = await get_sector_ui("industry")
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "sector:industry")
async def cb_industry(callback: types.CallbackQuery):
    await safe_answer(callback)
    text, markup = await get_sector_ui("industry")
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Concept Sectors (概念板块)
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("concept"))
async def cmd_concept(message: types.Message):
    if not await is_allowed(message.from_user.id):
        return
    text, markup = await get_sector_ui("concept")
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "sector:concept")
async def cb_concept(callback: types.CallbackQuery):
    await safe_answer(callback)
    text, markup = await get_sector_ui("concept")
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        pass


async def get_sector_ui(sector_type: str):
    """Get sector list UI."""
    sectors = await sector_service.get_realtime_sectors(sector_type=sector_type, limit=20)
    
    type_name = "行业板块" if sector_type == "industry" else "概念板块"
    type_icon = "🏭" if sector_type == "industry" else "💡"
    
    if not sectors:
        text = f"{type_icon} <b>{type_name}</b>\n━━━━━━━━━━━━━━━━━━━━━\n📭 暂无数据\n\n点击同步获取"
    else:
        # Count up/down
        up_count = sum(1 for s in sectors if s['change_pct'] > 0)
        down_count = len(sectors) - up_count
        
        text = f"{type_icon} <b>{type_name}</b> (涨{up_count}/跌{down_count})\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        # Top gainers
        text += "📈 <b>领涨</b>\n"
        for i, s in enumerate(sectors[:8], 1):
            pct = f"{s['change_pct']:+.2f}%"
            leader = f"({s['leading_stock']})" if s.get('leading_stock') else ""
            text += f"{i}. {s['name']} {pct} {leader}\n"
        
        # Bottom losers
        text += "\n📉 <b>领跌</b>\n"
        for s in sectors[-3:]:
            pct = f"{s['change_pct']:+.2f}%"
            text += f"  • {s['name']} {pct}\n"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 刷新", callback_data=f"sector:{sector_type}")
    builder.button(text="◀️ 返回", callback_data="sector:main")
    builder.adjust(2)
    
    return text, builder.as_markup()


# ─────────────────────────────────────────────────────────────────────────────
# Strong Sectors (强势板块)
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("hot7"))
async def cmd_hot7(message: types.Message):
    if not await is_allowed(message.from_user.id):
        return
    text, markup = await get_hot_ui(7)
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.message(Command("hot14"))
async def cmd_hot14(message: types.Message):
    if not await is_allowed(message.from_user.id):
        return
    text, markup = await get_hot_ui(14)
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.message(Command("hot30"))
async def cmd_hot30(message: types.Message):
    if not await is_allowed(message.from_user.id):
        return
    text, markup = await get_hot_ui(30)
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data.startswith("sector:hot:"))
async def cb_hot(callback: types.CallbackQuery):
    await safe_answer(callback)
    days = int(callback.data.split(":")[2])
    text, markup = await get_hot_ui(days)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        pass


async def get_hot_ui(days: int):
    """Get strong sectors UI."""
    sectors = await sector_service.get_strong_sectors(days=days, limit=15)
    
    if not sectors:
        text = f"🔥 <b>{days}日强势板块</b>\n━━━━━━━━━━━━━━━━━━━━━\n📭 暂无数据\n\n需要积累{days}天历史数据"
    else:
        text = f"🔥 <b>{days}日强势板块</b> TOP15\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for i, s in enumerate(sectors, 1):
            type_icon = "🏭" if s['type'] == 'industry' else "💡"
            total_pct = f"{float(s['total_change']):+.2f}%"
            up_days = s.get('up_days', 0)
            total_days = s.get('total_days', 0)
            win_rate = f"({up_days}/{total_days}天阳)" if total_days > 0 else ""
            text += f"{i}. {type_icon} {s['name']} {total_pct} {win_rate}\n"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="7日", callback_data="sector:hot:7")
    builder.button(text="14日", callback_data="sector:hot:14")
    builder.button(text="30日", callback_data="sector:hot:30")
    builder.button(text="◀️ 返回", callback_data="sector:main")
    builder.adjust(3, 1)
    
    return text, builder.as_markup()


# ─────────────────────────────────────────────────────────────────────────────
# Weak Sectors (弱势板块)
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "sector:weak")
async def cb_weak(callback: types.CallbackQuery):
    await safe_answer(callback)
    
    sectors = await sector_service.get_weak_sectors(days=7, limit=15)
    
    if not sectors:
        text = "📉 <b>7日弱势板块</b>\n━━━━━━━━━━━━━━━━━━━━━\n📭 暂无数据"
    else:
        text = "📉 <b>7日弱势板块</b> TOP15\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for i, s in enumerate(sectors, 1):
            type_icon = "🏭" if s['type'] == 'industry' else "💡"
            total_pct = f"{float(s['total_change']):+.2f}%"
            down_days = s.get('down_days', 0)
            total_days = s.get('total_days', 0)
            lose_rate = f"({down_days}/{total_days}天阴)" if total_days > 0 else ""
            text += f"{i}. {type_icon} {s['name']} {total_pct} {lose_rate}\n"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 刷新", callback_data="sector:weak")
    builder.button(text="◀️ 返回", callback_data="sector:main")
    builder.adjust(2)
    
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Sector Sync (同步数据)
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("sector_sync"))
async def cmd_sector_sync(message: types.Message):
    if not await is_allowed(message.from_user.id):
        return
    
    status = await message.answer("⏳ 正在同步板块数据...")
    
    try:
        result = await sector_service.collect_all_sectors()
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🏭 行业板块", callback_data="sector:industry")
        builder.button(text="💡 概念板块", callback_data="sector:concept")
        builder.adjust(2)
        
        await status.edit_text(
            f"✅ 同步完成\n\n"
            f"🏭 行业板块: <b>{result['industry']}</b>\n"
            f"💡 概念板块: <b>{result['concept']}</b>",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        await status.edit_text(f"❌ 同步失败: {e}")


@router.callback_query(F.data == "sector:sync")
async def cb_sector_sync(callback: types.CallbackQuery):
    await safe_answer(callback, "⏳ 同步中...")
    
    try:
        result = await sector_service.collect_all_sectors()
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🏭 行业板块", callback_data="sector:industry")
        builder.button(text="💡 概念板块", callback_data="sector:concept")
        builder.button(text="◀️ 返回", callback_data="sector:main")
        builder.adjust(2, 1)
        
        await callback.message.edit_text(
            f"✅ 同步完成\n\n"
            f"🏭 行业板块: <b>{result['industry']}</b>\n"
            f"💡 概念板块: <b>{result['concept']}</b>",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        await callback.message.edit_text(f"❌ 同步失败: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Sector Report (板块日报)
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "sector:report")
async def cb_sector_report(callback: types.CallbackQuery):
    await safe_answer(callback, "生成日报中...")
    
    try:
        report = await sector_service.generate_daily_report()
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 刷新", callback_data="sector:report")
        builder.button(text="◀️ 返回", callback_data="sector:main")
        builder.adjust(2)
        
        await callback.message.edit_text(report, parse_mode="HTML", reply_markup=builder.as_markup())
    except Exception as e:
        await callback.message.edit_text(f"❌ 生成失败: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Help
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("help"))
async def cmd_help(message: types.Message):
    if not await is_allowed(message.from_user.id):
        return
    
    text = (
        "📊 <b>命令列表</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "<b>🕷️ 网站爬虫</b>\n"
        "/add - 添加网站\n"
        "/remove - 删除网站\n"
        "/list - 网站列表\n"
        "/crawl - 立即爬取\n"
        "/recent - 最新内容\n\n"
        "<b>📈 涨停追踪</b>\n"
        "/today - 今日涨停\n"
        "/first - 首板(收盘封板)\n"
        "/burst - 曾涨停(炸板)\n"
        "/streak - 连板榜\n"
        "/strong - 强势股\n"
        "/watch - 启动追踪\n"
        "/scan - 信号扫描\n"
        "/scan force - 强制扫描(忽略缓存)\n"
        "/sync - 同步涨停\n\n"
        "<b>📊 板块分析</b>\n"
        "/industry - 行业板块\n"
        "/concept - 概念板块\n"
        "/hot7 - 7日强势板块\n"
        "/hot14 - 14日强势板块\n"
        "/hot30 - 30日强势板块\n"
        "/sector_sync - 同步板块数据\n\n"
        "<b>👤 用户管理</b>\n"
        "/useradd - 添加用户\n"
        "/userdel - 删除用户\n"
        "/userlist - 用户列表"
    )
    await message.answer(text, parse_mode="HTML")


# ─────────────────────────────────────────────────────────────────────────────
# User Management (用户管理)
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("useradd"))
async def cmd_useradd(message: types.Message, command: CommandObject):
    """Add a user to allowed list: /useradd <user_id> [username]"""
    if not await is_allowed(message.from_user.id):
        return
    
    if not command.args:
        await message.answer("❌ 用法: /useradd <user_id> [username]")
        return
    
    args = command.args.split()
    try:
        user_id = int(args[0])
    except ValueError:
        await message.answer("❌ user_id 必须是数字")
        return
    
    username = args[1] if len(args) > 1 else None
    
    if not db.pool:
        await message.answer("❌ 数据库未连接")
        return
    
    try:
        await db.pool.execute("""
            INSERT INTO allowed_users (user_id, username, added_by)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO UPDATE SET username = $2
        """, user_id, username, message.from_user.id)
        
        name_str = f" (@{username})" if username else ""
        await message.answer(f"✅ 已添加用户: <code>{user_id}</code>{name_str}", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ 添加失败: {e}")


@router.message(Command("userdel"))
async def cmd_userdel(message: types.Message, command: CommandObject):
    """Remove a user from allowed list: /userdel <user_id>"""
    if not await is_allowed(message.from_user.id):
        return
    
    if not command.args:
        await message.answer("❌ 用法: /userdel <user_id>")
        return
    
    try:
        user_id = int(command.args.strip())
    except ValueError:
        await message.answer("❌ user_id 必须是数字")
        return
    
    if not db.pool:
        await message.answer("❌ 数据库未连接")
        return
    
    try:
        result = await db.pool.execute("""
            DELETE FROM allowed_users WHERE user_id = $1
        """, user_id)
        
        if result == "DELETE 1":
            await message.answer(f"✅ 已删除用户: <code>{user_id}</code>", parse_mode="HTML")
        else:
            await message.answer(f"⚠️ 用户不存在: <code>{user_id}</code>", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ 删除失败: {e}")


@router.message(Command("userlist"))
async def cmd_userlist(message: types.Message):
    """List all allowed users."""
    if not await is_allowed(message.from_user.id):
        return
    
    text, markup = await get_userlist_ui()
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "user:list")
async def cb_userlist(callback: types.CallbackQuery):
    await safe_answer(callback)
    text, markup = await get_userlist_ui()
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        pass


@router.callback_query(F.data.startswith("user:del:"))
async def cb_user_del(callback: types.CallbackQuery):
    user_id = int(callback.data.split(":")[2])
    
    if not db.pool:
        await safe_answer(callback, "❌ 数据库未连接")
        return
    
    try:
        await db.pool.execute("DELETE FROM allowed_users WHERE user_id = $1", user_id)
        await safe_answer(callback, "✅ 已删除")
        
        text, markup = await get_userlist_ui()
        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
        except Exception:
            pass
    except Exception as e:
        await safe_answer(callback, f"❌ 失败: {e}")


async def get_userlist_ui():
    """Get user list UI."""
    # Get all users from DB (includes seeded env users)
    db_users = []
    if db.pool:
        try:
            rows = await db.pool.fetch("""
                SELECT user_id, username, added_by, created_at
                FROM allowed_users ORDER BY created_at DESC
            """)
            db_users = list(rows)
        except Exception:
            pass
    
    text = "👤 <b>授权用户</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    if db_users:
        for row in db_users:
            username = f" (@{row['username']})" if row['username'] else ""
            source = " 🔒" if row['username'] == 'env' else ""
            text += f"  • <code>{row['user_id']}</code>{username}{source}\n"
    else:
        text += "📭 无授权用户 (允许所有人)"
    
    builder = InlineKeyboardBuilder()
    
    # Add delete buttons for users
    for row in db_users[:10]:  # Limit to 10 buttons
        label = f"❌ {row['username'] or row['user_id']}"
        builder.button(text=label, callback_data=f"user:del:{row['user_id']}")
    
    builder.button(text="🔄 刷新", callback_data="user:list")
    builder.button(text="◀️ 返回", callback_data="main")
    
    # Adjust layout
    if db_users:
        builder.adjust(2, 2, 2, 2, 2, 2)
    else:
        builder.adjust(2)
    
    return text, builder.as_markup()


# ═══════════════════════════════════════════════════════════════════════════
# 市场报告 (Market Report)
# ═══════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "report:main")
async def cb_report_main(callback: types.CallbackQuery):
    await safe_answer(callback)
    
    # Get latest report info
    latest_weekly = await market_report_service.get_latest_report("weekly")
    latest_monthly = await market_report_service.get_latest_report("monthly")
    
    weekly_info = f"最近: {latest_weekly['report_date'].strftime('%m/%d')}" if latest_weekly else "暂无"
    monthly_info = f"最近: {latest_monthly['report_date'].strftime('%m月')}" if latest_monthly else "暂无"
    
    text = (
        "📋 <b>市场报告</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 周报: {weekly_info}\n"
        f"📆 月报: {monthly_info}\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "<i>周五20:00自动发送周报</i>\n"
        "<i>月末20:00自动发送月报</i>"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 即时周报", callback_data="report:weekly")
    builder.button(text="📈 即时月报", callback_data="report:monthly")
    builder.button(text="📋 近7日分析", callback_data="report:days:7")
    builder.button(text="📋 近14日分析", callback_data="report:days:14")
    builder.button(text="◀️ 返回", callback_data="main")
    builder.adjust(2, 2, 1)
    
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    except Exception:
        pass


@router.message(Command("report"))
async def cmd_report(message: types.Message, command: CommandObject):
    """Generate market report on-demand."""
    if not await is_allowed(message.from_user.id):
        return
    
    args = command.args if command else None
    days = 7  # Default
    
    if args:
        try:
            days = int(args)
        except ValueError:
            pass
    
    status = await message.answer(f"📊 正在生成近{days}日市场报告...\n\n⏳ 需要AI分析，请稍候")
    
    try:
        report = await market_report_service.generate_on_demand_report(days=days)
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 刷新", callback_data=f"report:days:{days}")
        builder.button(text="◀️ 返回", callback_data="report:main")
        builder.adjust(2)
        
        await status.edit_text(report, parse_mode="HTML", reply_markup=builder.as_markup())
    except Exception as e:
        await status.edit_text(f"❌ 报告生成失败: {e}")


@router.callback_query(F.data == "report:weekly")
async def cb_report_weekly(callback: types.CallbackQuery):
    await safe_answer(callback, "生成周报中...")
    
    try:
        # Show loading message (ignore if same)
        try:
            await callback.message.edit_text("📊 正在生成周报...\n\n⏳ 需要AI分析，请稍候", parse_mode="HTML")
        except TelegramBadRequest:
            pass  # Ignore if loading message same as current
        
        # Generate report
        report = await market_report_service.generate_weekly_report()
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 刷新", callback_data="report:weekly")
        builder.button(text="◀️ 返回", callback_data="report:main")
        builder.adjust(2)
        
        # Send report (ignore if same as before)
        try:
            await callback.message.edit_text(report, parse_mode="HTML", reply_markup=builder.as_markup())
        except TelegramBadRequest as e:
            if "not modified" not in str(e):
                raise  # Re-raise if it's a different error
    except Exception as e:
        try:
            await callback.message.edit_text(f"❌ 周报生成失败: {e}")
        except Exception:
            pass


@router.callback_query(F.data == "report:monthly")
async def cb_report_monthly(callback: types.CallbackQuery):
    await safe_answer(callback, "生成月报中...")
    
    try:
        # Show loading message (ignore if same)
        try:
            await callback.message.edit_text("📈 正在生成月报...\n\n⏳ 需要AI分析，请稍候", parse_mode="HTML")
        except TelegramBadRequest:
            pass
        
        # Generate report
        report = await market_report_service.generate_monthly_report()
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 刷新", callback_data="report:monthly")
        builder.button(text="◀️ 返回", callback_data="report:main")
        builder.adjust(2)
        
        # Send report (ignore if same as before)
        try:
            await callback.message.edit_text(report, parse_mode="HTML", reply_markup=builder.as_markup())
        except TelegramBadRequest as e:
            if "not modified" not in str(e):
                raise
    except Exception as e:
        try:
            await callback.message.edit_text(f"❌ 月报生成失败: {e}")
        except Exception:
            pass


@router.callback_query(F.data.startswith("report:days:"))
async def cb_report_days(callback: types.CallbackQuery):
    days = int(callback.data.split(":")[2])
    await safe_answer(callback, f"生成{days}日报告...")
    
    try:
        # Show loading message (ignore if same)
        try:
            await callback.message.edit_text(f"📋 正在生成近{days}日市场报告...\n\n⏳ 需要AI分析，请稍候", parse_mode="HTML")
        except TelegramBadRequest:
            pass
        
        # Generate report
        report = await market_report_service.generate_on_demand_report(days=days)
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 刷新", callback_data=f"report:days:{days}")
        builder.button(text="◀️ 返回", callback_data="report:main")
        builder.adjust(2)
        
        # Send report (ignore if same as before)
        try:
            await callback.message.edit_text(report, parse_mode="HTML", reply_markup=builder.as_markup())
        except TelegramBadRequest as e:
            if "not modified" not in str(e):
                raise
    except Exception as e:
        try:
            await callback.message.edit_text(f"❌ 报告生成失败: {e}")
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════
# 自选列表 (User Watchlist)
# ═══════════════════════════════════════════════════════════════════════════

@router.message(Command("watch"))
async def cmd_watch_add(message: types.Message, command: CommandObject):
    """Add a stock to watchlist: /watch 600519 or /watch 600519 贵州茅台"""
    if not await is_allowed(message.from_user.id):
        return
    
    args = command.args if command else None
    if not args:
        # Show user's watchlist
        status = await message.answer("⏳ 正在加载自选列表...")
        try:
            text, markup = await get_watchlist_ui(message.from_user.id, chat_type=message.chat.type)
            await status.edit_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
        except Exception as e:
            await status.edit_text(f"❌ 加载失败: {e}")
        return

    
    parts = args.split(maxsplit=1)
    code = parts[0].strip()
    name = parts[1].strip() if len(parts) > 1 else None
    
    # Normalize code (remove leading zeros if needed for some stocks)
    if not code.isdigit():
        await message.answer("❌ 股票代码应为数字")
        return
    
    status = await message.answer(f"⏳ 正在添加 {code}...")
    
    try:
        result = await watchlist_service.add_stock(
            user_id=message.from_user.id,
            code=code,
            name=name
        )
        
        stock_name = result.get('name', code)
        add_price = result.get('add_price', 0)
        price_str = f"价格: {add_price:.2f}" if add_price else ""
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📋 查看自选", callback_data="watch:list")
        builder.adjust(1)
        
        await status.edit_text(
            f"✅ 已添加 <b>{stock_name}</b> ({code})\n{price_str}",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        await status.edit_text(f"❌ 添加失败: {e}")


@router.message(Command("unwatch"))
async def cmd_watch_remove(message: types.Message, command: CommandObject):
    """Remove a stock from watchlist: /unwatch 600519"""
    if not await is_allowed(message.from_user.id):
        return
    
    args = command.args if command else None
    if not args:
        await message.answer("用法: <code>/unwatch 600519</code>", parse_mode="HTML")
        return
    
    code = args.strip().split()[0]
    
    success = await watchlist_service.remove_stock(
        user_id=message.from_user.id,
        code=code
    )
    
    if success:
        builder = InlineKeyboardBuilder()
        builder.button(text="📋 查看自选", callback_data="watch:list")
        builder.adjust(1)
        
        await message.answer(
            f"✅ 已从自选删除 {code}",
            reply_markup=builder.as_markup()
        )
    else:
        await message.answer(f"❌ 删除失败，{code} 可能不在自选列表中")


@router.message(Command("mywatch"))
async def cmd_mywatch(message: types.Message):
    """View watchlist with real-time prices."""
    if not await is_allowed(message.from_user.id):
        return
    
    status = await message.answer("⏳ 正在加载自选列表...")
    
    try:
        text, markup = await get_watchlist_ui(message.from_user.id, chat_type=message.chat.type)
        await status.edit_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
    except Exception as e:
        await status.edit_text(f"❌ 加载失败: {e}")


@router.callback_query(F.data.startswith("watch:list"))
async def cb_watch_list(callback: types.CallbackQuery):
    """View watchlist (cached prices) with pagination."""
    await safe_answer(callback)
    
    # Parse page from callback_data: "watch:list" or "watch:list:N"
    parts = callback.data.split(":")
    page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    
    try:
        await callback.message.edit_text("⏳ 正在加载...", parse_mode="HTML")
        text, markup = await get_watchlist_ui(
            callback.from_user.id, 
            realtime=False, 
            chat_type=callback.message.chat.type if callback.message else None,
            page=page
        )
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
    except Exception as e:
        await callback.message.edit_text(f"❌ 加载失败: {e}")


@router.callback_query(F.data.startswith("watch:realtime"))
async def cb_watch_realtime(callback: types.CallbackQuery):
    """View watchlist with real-time prices and pagination."""
    await safe_answer(callback)
    
    # Parse page from callback_data: "watch:realtime" or "watch:realtime:N"
    parts = callback.data.split(":")
    page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    
    try:
        await callback.message.edit_text("⏳ 正在获取实时行情...", parse_mode="HTML")
        text, markup = await get_watchlist_ui(
            callback.from_user.id, 
            realtime=True, 
            chat_type=callback.message.chat.type if callback.message else None,
            page=page
        )
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
    except Exception as e:
        await callback.message.edit_text(f"❌ 加载失败: {e}")


@router.callback_query(F.data == "watch:clear")
async def cb_watch_clear(callback: types.CallbackQuery):
    """Clear all stocks from watchlist."""
    # Ask for confirmation
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ 确认清空", callback_data="watch:clear:confirm")
    builder.button(text="❌ 取消", callback_data="watch:list")
    builder.adjust(2)
    
    await callback.message.edit_text(
        "⚠️ <b>确认清空自选列表？</b>\n\n此操作无法撤销。",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )


@router.callback_query(F.data == "watch:clear:confirm")
async def cb_watch_clear_confirm(callback: types.CallbackQuery):
    """Execute clear watchlist."""
    await safe_answer(callback)
    
    success = await watchlist_service.clear_watchlist(callback.from_user.id)
    
    if success:
        await callback.message.edit_text(
            "✅ 自选列表已清空",
            reply_markup=InlineKeyboardBuilder().button(text="◀️ 返回", callback_data="watch:list").as_markup()
        )
    else:
        await callback.message.edit_text(
            "❌ 清空失败",
            reply_markup=InlineKeyboardBuilder().button(text="◀️ 返回", callback_data="watch:list").as_markup()
        )


@router.callback_query(F.data.startswith("watch:del:"))
async def cb_watch_del(callback: types.CallbackQuery):
    """Delete stock from watchlist."""
    code = callback.data.split(":")[2]
    
    success = await watchlist_service.remove_stock(
        user_id=callback.from_user.id,
        code=code
    )
    
    if success:
        await safe_answer(callback, f"✅ 已删除 {code}")
    else:
        await safe_answer(callback, "❌ 删除失败")
    
    # Refresh list
    try:
        text, markup = await get_watchlist_ui(callback.from_user.id, realtime=False, chat_type=callback.message.chat.type if callback.message else None)
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
    except Exception:
        pass


async def get_watchlist_ui(user_id: int, realtime: bool = False, chat_type: Optional[str] = None, page: int = 0):
    """Get watchlist UI with prices.
    
    Args:
        user_id: User ID
        realtime: If True, fetch real-time prices from AkShare
        page: Page number (0-indexed) for pagination
    """
    PAGE_SIZE = 20
    
    webapp_base = _get_webapp_base(chat_type)
    use_webapp_buttons = bool(webapp_base)
    if realtime:
        stocks = await watchlist_service.get_watchlist_realtime(user_id)
    else:
        stocks = await watchlist_service.get_watchlist_with_prices(user_id)
    
    if not stocks:
        text = (
            "⭐ <b>自选列表</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "📭 暂无自选股票\n\n"
            "用 <code>/watch 600519</code> 添加"
        )
        builder = InlineKeyboardBuilder()
        builder.button(text="◀️ 返回", callback_data="main")
        return text, builder.as_markup()
    
    # Sort by total change descending
    stocks.sort(key=lambda x: x.get('total_change', 0), reverse=True)
    
    # Pagination
    total_stocks = len(stocks)
    total_pages = (total_stocks + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(0, min(page, total_pages - 1))  # Clamp page to valid range
    start_idx = page * PAGE_SIZE
    end_idx = min(start_idx + PAGE_SIZE, total_stocks)
    page_stocks = stocks[start_idx:end_idx]
    
    # Header with data source indicator and pagination info
    source = "📡 实时" if realtime else "📊 缓存"
    page_info = f" [{page + 1}/{total_pages}]" if total_pages > 1 else ""
    text = f"⭐ <b>自选列表</b> ({total_stocks}){page_info} {source}\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    if use_webapp_buttons:
        text += "<i>点击下方按钮查看K线</i>\n"
    
    for idx, s in enumerate(page_stocks, start_idx + 1):
        name = s.get('name', s['code'])
        code = s['code']
        current = s.get('current_price', 0)
        today = s.get('today_change', 0)
        total = s.get('total_change', 0)
        add_date = s.get('add_date')
        
        # Icon based on total performance
        if total > 5:
            icon = "🟢"  # Big gain
        elif total > 0:
            icon = "⬆️"  # Small gain
        elif total > -5:
            icon = "⬇️"  # Small loss
        else:
            icon = "🔴"  # Big loss

        if use_webapp_buttons:
            continue
        
        chart_url = get_chart_url(code, name, context="watchlist")
        date_str = add_date.strftime('%m/%d') if add_date else ""
        
        text += (
            f"{icon} <a href=\"{chart_url}\"><b>{name}</b></a> ({code})\n"
            f"   💰 {current:.2f} | 今日 {today:+.2f}% | 累计 <b>{total:+.2f}%</b>\n"
            f"   <i>加入: {date_str}</i>\n\n"
        )
    
    builder = InlineKeyboardBuilder()

    if use_webapp_buttons:
        for idx, s in enumerate(page_stocks, start_idx + 1):
            name = s.get('name', s['code'])
            code = s['code']
            current = s.get('current_price', 0)
            today = s.get('today_change', 0)
            total = s.get('total_change', 0)
            if total > 5:
                icon = "🟢"
            elif total > 0:
                icon = "⬆️"
            elif total > -5:
                icon = "⬇️"
            else:
                icon = "🔴"
            suffix = f"{current:.2f} {today:+.2f}% T{total:+.2f}%"
            builder.row(
                _build_webapp_button(
                    name,
                    code,
                    "watchlist",
                    webapp_base,
                    suffix=suffix,
                    prefix=f"{icon}{idx}."
                )
            )
    
    # Add delete buttons for current page stocks (limit to 8)
    for s in page_stocks[:8]:
        name_short = s.get('name', s['code'])[:6]
        builder.button(text=f"❌ {name_short}", callback_data=f"watch:del:{s['code']}")
    
    # Pagination buttons
    nav_buttons = []
    if page > 0:
        nav_buttons.append(types.InlineKeyboardButton(
            text="◀️ 上一页",
            callback_data=f"watch:{'realtime' if realtime else 'list'}:{page - 1}"
        ))
    if page < total_pages - 1:
        nav_buttons.append(types.InlineKeyboardButton(
            text="下一页 ▶️",
            callback_data=f"watch:{'realtime' if realtime else 'list'}:{page + 1}"
        ))
    
    if nav_buttons:
        builder.row(*nav_buttons)
    
    # Toggle between cached and realtime + return button
    # Toggle between cached and realtime + return button
    if use_webapp_buttons:
        builder.row(
            types.InlineKeyboardButton(
                text="📊 缓存数据" if realtime else "📡 实时刷新",
                callback_data="watch:list:0" if realtime else "watch:realtime:0"
            ),
            types.InlineKeyboardButton(text="🗑️ 清空", callback_data="watch:clear")
        )
        builder.row(types.InlineKeyboardButton(text="◀️ 返回", callback_data="main"))
    else:
        if realtime:
            builder.button(text="📊 缓存数据", callback_data="watch:list:0")
        else:
            builder.button(text="📡 实时刷新", callback_data="watch:realtime:0")
        builder.button(text="◀️ 返回", callback_data="main")
        builder.adjust(2, 2, 2, 2, 2)
    
    return text, builder.as_markup()



# ═══════════════════════════════════════════════════════════════════════════
# Trading Simulator (模拟交易)
# ═══════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "sim:main")
async def cb_sim_main(callback: types.CallbackQuery):
    """Trading simulator main menu."""
    await safe_answer(callback)
    
    stats = await trading_simulator.get_statistics()
    
    text = (
        "💰 <b>模拟交易</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 账户总值: ¥{stats.get('total_value', 1000000):,.0f}\n"
        f"📈 总收益: {stats.get('total_return_pct', 0):+.2f}%\n"
        f"📦 当前持仓: {stats.get('current_positions', 0)}/{MAX_POSITIONS}\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "<i>每日15:35自动扫描交易</i>"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 持仓", callback_data="sim:portfolio")
    builder.button(text="📉 盈亏", callback_data="sim:pnl")
    builder.button(text="📜 历史", callback_data="sim:trades")
    builder.button(text="🔍 手动扫描", callback_data="sim:scan")
    builder.button(text="◀️ 返回", callback_data="main")
    builder.adjust(2, 2, 1)
    
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    except Exception:
        pass


@router.message(Command("portfolio"))
async def cmd_portfolio(message: types.Message):
    """Show current trading portfolio."""
    if not await is_allowed(message.from_user.id):
        return
    
    report = await trading_simulator.generate_portfolio_report()
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📉 盈亏统计", callback_data="sim:pnl")
    builder.button(text="📜 交易历史", callback_data="sim:trades")
    builder.button(text="🔄 刷新", callback_data="sim:portfolio")
    builder.adjust(2, 1)
    
    await message.answer(report, parse_mode="HTML", reply_markup=builder.as_markup())


@router.callback_query(F.data == "sim:portfolio")
async def cb_portfolio(callback: types.CallbackQuery):
    await safe_answer(callback)
    report = await trading_simulator.generate_portfolio_report()
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📉 盈亏统计", callback_data="sim:pnl")
    builder.button(text="📜 交易历史", callback_data="sim:trades")
    builder.button(text="🔄 刷新", callback_data="sim:portfolio")
    builder.adjust(2, 1)
    
    try:
        await callback.message.edit_text(report, parse_mode="HTML", reply_markup=builder.as_markup())
    except:
        pass


@router.message(Command("pnl"))
async def cmd_pnl(message: types.Message):
    """Show P&L statistics."""
    if not await is_allowed(message.from_user.id):
        return
    
    report = await trading_simulator.generate_pnl_report()
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 持仓", callback_data="sim:portfolio")
    builder.button(text="📜 历史", callback_data="sim:trades")
    builder.button(text="🔄 刷新", callback_data="sim:pnl")
    builder.adjust(2, 1)
    
    await message.answer(report, parse_mode="HTML", reply_markup=builder.as_markup())


@router.callback_query(F.data == "sim:pnl")
async def cb_pnl(callback: types.CallbackQuery):
    await safe_answer(callback)
    report = await trading_simulator.generate_pnl_report()
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 持仓", callback_data="sim:portfolio")
    builder.button(text="📜 历史", callback_data="sim:trades")
    builder.button(text="🔄 刷新", callback_data="sim:pnl")
    builder.adjust(2, 1)
    
    try:
        await callback.message.edit_text(report, parse_mode="HTML", reply_markup=builder.as_markup())
    except:
        pass


@router.message(Command("trades"))
async def cmd_trades(message: types.Message):
    """Show recent trade history."""
    if not await is_allowed(message.from_user.id):
        return
    
    report = await trading_simulator.generate_trades_report()
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 持仓", callback_data="sim:portfolio")
    builder.button(text="📉 盈亏", callback_data="sim:pnl")
    builder.button(text="🔄 刷新", callback_data="sim:trades")
    builder.adjust(2, 1)
    
    await message.answer(report, parse_mode="HTML", reply_markup=builder.as_markup())


@router.callback_query(F.data == "sim:trades")
async def cb_trades(callback: types.CallbackQuery):
    await safe_answer(callback)
    report = await trading_simulator.generate_trades_report()
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 持仓", callback_data="sim:portfolio")
    builder.button(text="📉 盈亏", callback_data="sim:pnl")
    builder.button(text="🔄 刷新", callback_data="sim:trades")
    builder.button(text="◀️ 返回", callback_data="sim:main")
    builder.adjust(2, 2)
    
    try:
        await callback.message.edit_text(report, parse_mode="HTML", reply_markup=builder.as_markup())
    except Exception:
        pass


@router.message(Command("sim"))
async def cmd_sim(message: types.Message, command: CommandObject):
    """Trading simulator commands.
    
    /sim - Show main menu
    /sim scan - Manual trigger daily scan
    /sim status - Show account status
    """
    if not await is_allowed(message.from_user.id):
        return
    
    args = command.args
    
    if args == "scan":
        # Manual scan trigger
        status_msg = await message.answer("⏳ 正在扫描买卖信号...")
        
        try:
            await trading_simulator.daily_routine()
            stats = await trading_simulator.get_statistics()
            
            await status_msg.edit_text(
                f"✅ 扫描完成\n\n"
                f"📦 当前持仓: {stats.get('current_positions', 0)}/10\n"
                f"💵 可用资金: ¥{stats.get('current_cash', 0):,.0f}\n"
                f"📈 总收益: {stats.get('total_return_pct', 0):+.2f}%",
                parse_mode="HTML"
            )
        except Exception as e:
            await status_msg.edit_text(f"❌ 扫描失败: {e}")
        return
    
    if args == "status":
        report = await trading_simulator.generate_pnl_report()
        await message.answer(report, parse_mode="HTML")
        return
    
    # Default: show sim menu
    stats = await trading_simulator.get_statistics()
    
    text = (
        "🤖 <b>模拟交易</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 初始资金: ¥{stats.get('initial_capital', 1000000):,.0f}\n"
        f"📊 账户总值: ¥{stats.get('total_value', 1000000):,.0f}\n"
        f"📈 总收益: {stats.get('total_return_pct', 0):+.2f}%\n"
        f"📦 当前持仓: {stats.get('current_positions', 0)}/10\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "<i>每日15:35自动扫描交易</i>"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 持仓", callback_data="sim:portfolio")
    builder.button(text="📉 盈亏", callback_data="sim:pnl")
    builder.button(text="📜 历史", callback_data="sim:trades")
    builder.button(text="🔍 手动扫描", callback_data="sim:scan")
    builder.adjust(2, 2)
    
    await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())


@router.callback_query(F.data == "sim:scan")
async def cb_sim_scan(callback: types.CallbackQuery):
    await safe_answer(callback, "⏳ 扫描中...")
    
    try:
        await trading_simulator.daily_routine()
        stats = await trading_simulator.get_statistics()
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📊 查看持仓", callback_data="sim:portfolio")
        builder.adjust(1)
        
        await callback.message.edit_text(
            f"✅ 扫描完成\n\n"
            f"📦 当前持仓: {stats.get('current_positions', 0)}/10\n"
            f"💵 可用资金: ¥{stats.get('current_cash', 0):,.0f}\n"
            f"📈 总收益: {stats.get('total_return_pct', 0):+.2f}%",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        await callback.message.edit_text(f"❌ 扫描失败: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# Limit-Up Reports (涨停股报告)
# ═══════════════════════════════════════════════════════════════════════════

@router.message(Command("limitup"))
async def cmd_limitup(message: types.Message, command: CommandObject):
    """Manual trigger for limit-up reports.
    
    /limitup morning - Send morning price update
    /limitup afternoon - Send afternoon limit-up report
    """
    if not await is_allowed(message.from_user.id):
        return
    
    import asyncio
    from app.services.limit_up import limit_up_service
    
    args = command.args or ""
    
    if args == "morning":
        await message.answer("⏳ 早报正在后台生成并发送到频道...")
        asyncio.create_task(limit_up_service.send_morning_price_update())
    
    elif args == "afternoon":
        await message.answer("⏳ 涨停日报正在后台生成并发送到频道...")
        asyncio.create_task(limit_up_service.send_afternoon_report())
    
    else:
        await message.answer(
            "📊 <b>涨停股报告</b>\n\n"
            "<code>/limitup morning</code> - 发送昨日涨停股早报\n"
            "<code>/limitup afternoon</code> - 发送今日涨停日报",
            parse_mode="HTML"
        )



# ═══════════════════════════════════════════════════════════════════════════
# 打板 Trading (打板模拟)
# ═══════════════════════════════════════════════════════════════════════════

@router.message(Command("daban"))
async def cmd_daban(message: types.Message, command: CommandObject):
    """打板 service commands.
    
    /daban - Show today's 打板 recommendations
    /daban portfolio - Show 打板 portfolio
    /daban stats - Show 打板 statistics
    /daban scan - Manual scan and buy
    """
    if not await is_allowed(message.from_user.id):
        return
    
    args = command.args or ""
    
    if args == "portfolio":
        report = await daban_simulator.generate_portfolio_report()
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📊 统计", callback_data="daban:stats")
        builder.button(text="🔄 刷新", callback_data="daban:portfolio")
        builder.button(text="◀️ 返回", callback_data="daban:main")
        builder.adjust(2, 1)
        
        await message.answer(report, parse_mode="HTML", reply_markup=builder.as_markup())
        return
    
    if args == "stats":
        report = await daban_simulator.generate_stats_report()
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📦 持仓", callback_data="daban:portfolio")
        builder.button(text="🔄 刷新", callback_data="daban:stats")
        builder.button(text="◀️ 返回", callback_data="daban:main")
        builder.adjust(2, 1)
        
        await message.answer(report, parse_mode="HTML", reply_markup=builder.as_markup())
        return
    
    if args == "live":
        report = await daban_service.generate_live_report()
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔔 信号", callback_data="daban:signals")
        builder.button(text="🔄 刷新", callback_data="daban:live")
        builder.button(text="◀️ 返回", callback_data="daban:main")
        builder.adjust(2, 1)
        
        await message.answer(report, parse_mode="HTML", reply_markup=builder.as_markup())
        return
    
    if args == "signals":
        report = await daban_service.generate_signals_report()
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📊 实时", callback_data="daban:live")
        builder.button(text="🔄 刷新", callback_data="daban:signals")
        builder.button(text="◀️ 返回", callback_data="daban:main")
        builder.adjust(2, 1)
        
        await message.answer(report, parse_mode="HTML", reply_markup=builder.as_markup())
        return

    
    if args == "scan":
        status_msg = await message.answer("⏳ 扫描打板标的...")
        try:
            await daban_simulator.afternoon_scan_buy()
            stats = await daban_simulator.get_statistics()
            
            await status_msg.edit_text(
                f"✅ 打板扫描完成\n\n"
                f"📦 当前持仓: {stats.get('current_positions', 0)}/{DABAN_MAX_POSITIONS}\n"
                f"💵 可用资金: ¥{stats.get('current_cash', 0):,.0f}\n"
                f"📈 总收益: {stats.get('total_return_pct', 0):+.2f}%"
            )
        except Exception as e:
            await status_msg.edit_text(f"❌ 扫描失败: {e}")
        return
    
    # Default: show 打板 analysis
    status_msg = await message.answer("⏳ 分析打板标的...")
    
    try:
        report = await daban_service.generate_daban_report()
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📦 持仓", callback_data="daban:portfolio")
        builder.button(text="📊 统计", callback_data="daban:stats")
        builder.button(text="🟢 实时", callback_data="daban:live")
        builder.button(text="🌡️ 情绪", callback_data="daban:sentiment")
        builder.button(text="🔍 扫描买入", callback_data="daban:scan")
        builder.button(text="🔄 刷新", callback_data="daban:main")
        builder.adjust(3, 3)
        
        await status_msg.edit_text(report, parse_mode="HTML", reply_markup=builder.as_markup())
    except Exception as e:
        await status_msg.edit_text(f"❌ 分析失败: {e}")


@router.callback_query(F.data == "daban:main")
async def cb_daban_main(callback: types.CallbackQuery):
    """打板 main menu."""
    await safe_answer(callback)
    
    try:
        await callback.message.edit_text("⏳ 分析打板标的...", parse_mode="HTML")
        report = await daban_service.generate_daban_report()
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📦 持仓", callback_data="daban:portfolio")
        builder.button(text="📊 统计", callback_data="daban:stats")
        builder.button(text="🟢 实时", callback_data="daban:live")
        builder.button(text="🌡️ 情绪", callback_data="daban:sentiment")
        builder.button(text="🔍 扫描买入", callback_data="daban:scan")
        builder.button(text="🔄 刷新", callback_data="daban:main")
        builder.button(text="◀️ 返回", callback_data="main")
        builder.adjust(3, 3, 1)
        
        await callback.message.edit_text(report, parse_mode="HTML", reply_markup=builder.as_markup())
    except Exception as e:
        await callback.message.edit_text(f"❌ 失败: {e}")


@router.callback_query(F.data == "daban:portfolio")
async def cb_daban_portfolio(callback: types.CallbackQuery):
    await safe_answer(callback)
    
    report = await daban_simulator.generate_portfolio_report()
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 统计", callback_data="daban:stats")
    builder.button(text="🔄 刷新", callback_data="daban:portfolio")
    builder.button(text="◀️ 返回", callback_data="daban:main")
    builder.adjust(2, 1)
    
    try:
        await callback.message.edit_text(report, parse_mode="HTML", reply_markup=builder.as_markup())
    except Exception:
        pass


@router.callback_query(F.data == "daban:stats")
async def cb_daban_stats(callback: types.CallbackQuery):
    await safe_answer(callback)
    
    report = await daban_simulator.generate_stats_report()
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📦 持仓", callback_data="daban:portfolio")
    builder.button(text="🔄 刷新", callback_data="daban:stats")
    builder.button(text="◀️ 返回", callback_data="daban:main")
    builder.adjust(2, 1)
    
    try:
        await callback.message.edit_text(report, parse_mode="HTML", reply_markup=builder.as_markup())
    except Exception:
        pass


@router.callback_query(F.data == "daban:scan")
async def cb_daban_scan(callback: types.CallbackQuery):
    await safe_answer(callback, "⏳ 扫描打板...")
    
    try:
        await daban_simulator.afternoon_scan_buy()
        stats = await daban_simulator.get_statistics()
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📦 查看持仓", callback_data="daban:portfolio")
        builder.button(text="◀️ 返回", callback_data="daban:main")
        builder.adjust(1, 1)
        
        await callback.message.edit_text(
            f"✅ 打板扫描完成\n\n"
            f"📦 当前持仓: {stats.get('current_positions', 0)}/{DABAN_MAX_POSITIONS}\n"
            f"💵 可用资金: ¥{stats.get('current_cash', 0):,.0f}\n"
            f"📈 总收益: {stats.get('total_return_pct', 0):+.2f}%",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        await callback.message.edit_text(f"❌ 扫描失败: {e}")


@router.callback_query(F.data == "daban:sentiment")
async def cb_daban_sentiment(callback: types.CallbackQuery):
    """Show market sentiment and recommendation performance."""
    await safe_answer(callback)
    
    try:
        await callback.message.edit_text("⏳ 加载市场情绪...", parse_mode="HTML")
        report = await daban_service.generate_sentiment_report()
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📊 打板分析", callback_data="daban:main")
        builder.button(text="🔄 刷新", callback_data="daban:sentiment")
        builder.adjust(2)
        
        await callback.message.edit_text(report, parse_mode="HTML", reply_markup=builder.as_markup())
    except Exception as e:
        await callback.message.edit_text(f"❌ 失败: {e}")


@router.callback_query(F.data == "daban:live")
async def cb_daban_live(callback: types.CallbackQuery):
    """Show live limit-up monitoring status."""
    await safe_answer(callback)
    
    try:
        report = await daban_service.generate_live_report()
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔔 信号", callback_data="daban:signals")
        builder.button(text="🔄 刷新", callback_data="daban:live")
        builder.button(text="◀️ 返回", callback_data="daban:main")
        builder.adjust(2, 1)
        
        await callback.message.edit_text(report, parse_mode="HTML", reply_markup=builder.as_markup())
    except Exception as e:
        await callback.message.edit_text(f"❌ 失败: {e}")


@router.callback_query(F.data == "daban:signals")
async def cb_daban_signals(callback: types.CallbackQuery):
    """Show recent signal history."""
    await safe_answer(callback)
    
    try:
        report = await daban_service.generate_signals_report()
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📊 实时", callback_data="daban:live")
        builder.button(text="🔄 刷新", callback_data="daban:signals")
        builder.button(text="◀️ 返回", callback_data="daban:main")
        builder.adjust(2, 1)
        
        await callback.message.edit_text(report, parse_mode="HTML", reply_markup=builder.as_markup())
    except Exception as e:
        await callback.message.edit_text(f"❌ 失败: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# Portfolio Management (实盘持仓)
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("port"))
async def cmd_port(message: types.Message, command: CommandObject):
    """Manage real portfolio."""
    if not await is_allowed(message.from_user.id):
        return

    args = command.args
    if not args:
        # Show portfolio
        await show_portfolio(message)
        return

    parts = args.split()
    action = parts[0].lower()

    if action == "add":
        # /port add <code> <cost> <shares>
        if len(parts) < 4:
            await message.answer("用法: /port add <代码> <成本价> <股数>")
            return
        
        code = parts[1]
        try:
            cost = float(parts[2])
            shares = int(parts[3])
        except ValueError:
            await message.answer("❌ 价格或股数格式错误")
            return
            
        success = await portfolio_service.add_position(message.from_user.id, code, cost, shares)
        if success:
            await message.answer(f"✅ 已添加 {code}: {shares}股 @ {cost}")
            await show_portfolio(message)
        else:
            await message.answer("❌ 添加失败")

    elif action == "del":
        # /port del <code>
        if len(parts) < 2:
            await message.answer("用法: /port del <代码>")
            return
            
        code = parts[1]
        success = await portfolio_service.remove_position(message.from_user.id, code)
        if success:
            await message.answer(f"✅ 已删除 {code}")
            await show_portfolio(message)
        else:
            await message.answer("❌ 删除失败")
            
    else:
        await message.answer(
            "💼 <b>持仓管理</b>\n\n"
            "• 查看: /port\n"
            "• 添加: /port add <代码> <成本> <股数>\n"
            "• 删除: /port del <代码>",
            parse_mode="HTML"
        )

async def show_portfolio(message: types.Message):
    """Show portfolio with P&L."""
    portfolio = await portfolio_service.get_portfolio(message.from_user.id)
    
    if not portfolio:
        await message.answer("💼 <b>实盘持仓</b>\n━━━━━━━━━━━━━━━━━━━━━\n📭 当前无持仓\n\n使用 /port add 添加", parse_mode="HTML")
        return

    total_market = 0
    total_profit = 0
    total_cost = 0
    
    lines = ["💼 <b>实盘持仓</b>", "━━━━━━━━━━━━━━━━━━━━━"]
    
    for p in portfolio:
        name = p.get('name', p['code'])
        code = p['code']
        current = p.get('current_price', 0)
        cost = float(p['cost_price'])
        shares = p['shares']
        profit = p.get('profit', 0)
        profit_pct = p.get('profit_pct', 0)
        today_pct = p.get('today_change', 0)
        
        emoji = "🔴" if profit > 0 else ("🟢" if profit < 0 else "⚪")
        
        lines.append(
            f"{emoji} <b>{name}</b> ({code})\n"
            f"   现价: {current:.2f} ({today_pct:+.2f}%)\n"
            f"   持仓: {shares}股 @ {cost:.2f}\n"
            f"   盈亏: {profit:+,.0f} ({profit_pct:+.2f}%)"
        )
        
        total_market += p.get('market_value', 0)
        total_profit += profit
        total_cost += cost * shares

    total_return = (total_profit / total_cost * 100) if total_cost > 0 else 0
    
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"💰 总市值: ¥{total_market:,.0f}")
    lines.append(f"📈 总盈亏: ¥{total_profit:+,.0f} ({total_return:+.2f}%)")
    
    await message.answer("\n".join(lines), parse_mode="HTML")
