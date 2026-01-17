"""
Limit-Up Router

Handles limit-up stock tracking: today's limit-ups, first-board, burst,
streak leaders, strong stocks, and startup watchlist.
"""

from typing import Optional

from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.services.limit_up import limit_up_service
from app.core.stock_links import get_chart_url
from app.core.logger import Logger

from .common import (
    is_allowed, safe_answer, safe_edit_text,
    get_webapp_base, build_webapp_button,
    calculate_pagination, build_pagination_buttons,
)

logger = Logger("LimitUpRouter")
router = Router()


# ─────────────────────────────────────────────────────────────────────────────
# Limit-Up Main Menu
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "lu:main")
async def cb_lu_main(callback: types.CallbackQuery):
    """Show limit-up tracking main menu."""
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

    await safe_edit_text(callback.message, text, reply_markup=builder.as_markup())


# ─────────────────────────────────────────────────────────────────────────────
# Today's Limit-Ups
# ─────────────────────────────────────────────────────────────────────────────

async def _get_today_ui(page: int = 1, chat_type: Optional[str] = None):
    """Build today's limit-up stocks UI."""
    PAGE_SIZE = 30
    webapp_base = get_webapp_base(chat_type)
    use_webapp_buttons = bool(webapp_base)

    try:
        stocks = await limit_up_service.get_realtime_limit_ups()
    except Exception as e:
        logger.error(f"Real-time fetch failed: {e}")
        stocks = []

    if stocks:
        sealed = [s for s in stocks if s.get("is_sealed", True)]
        sealed.sort(key=lambda x: (-x.get("limit_times", 1), -x.get("close_price", 0)))
    else:
        sealed = []

    total = len(sealed)
    page, total_pages, start_idx, end_idx = calculate_pagination(total, page, PAGE_SIZE)
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
    if use_webapp_buttons and rows:
        for i, r in enumerate(rows, start_idx + 1):
            lt = r.get('limit_times', 1)
            suffix = f"{lt}板" if lt > 1 else "首板"
            builder.row(build_webapp_button(
                r.get('name') or r['code'],
                r['code'],
                "limit_up",
                webapp_base,
                suffix=suffix,
                prefix=f"{i}."
            ))
        build_pagination_buttons(page, total_pages, "lu:today", builder)
        builder.row(types.InlineKeyboardButton(text="◀️ 返回", callback_data="lu:main"))
    else:
        build_pagination_buttons(page, total_pages, "lu:today", builder)
        builder.row(types.InlineKeyboardButton(text="◀️ 返回", callback_data="lu:main"))

    return text, builder.as_markup()


@router.message(Command("today"))
async def cmd_today(message: types.Message):
    """Show today's limit-up stocks."""
    if not await is_allowed(message.from_user.id):
        return
    text, markup = await _get_today_ui(chat_type=message.chat.type)
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data.startswith("lu:today"))
async def cb_today(callback: types.CallbackQuery):
    """Show today's limit-ups via callback with pagination."""
    await safe_answer(callback)
    parts = callback.data.split(":")
    page = int(parts[2]) if len(parts) > 2 else 1
    text, markup = await _get_today_ui(page, chat_type=callback.message.chat.type if callback.message else None)
    await safe_edit_text(callback.message, text, reply_markup=markup, disable_web_page_preview=True)


# ─────────────────────────────────────────────────────────────────────────────
# First-Board (首板)
# ─────────────────────────────────────────────────────────────────────────────

async def _get_first_ui(page: int = 1, chat_type: Optional[str] = None):
    """Build first-board limit-up stocks UI."""
    PAGE_SIZE = 30
    webapp_base = get_webapp_base(chat_type)
    use_webapp_buttons = bool(webapp_base)

    try:
        stocks = await limit_up_service.get_realtime_limit_ups()
    except Exception:
        stocks = []

    if stocks:
        first_board = [
            s for s in stocks
            if s.get("limit_times", 1) == 1 and s.get("is_sealed", True)
        ]
        first_board.sort(key=lambda x: -x.get("turnover_rate", 0))
    else:
        first_board = []

    total = len(first_board)
    page, total_pages, start_idx, end_idx = calculate_pagination(total, page, PAGE_SIZE)
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
    if use_webapp_buttons and rows:
        for i, r in enumerate(rows, start_idx + 1):
            tr = r.get('turnover_rate', 0)
            suffix = f"换手{tr:.1f}%" if tr else None
            builder.row(build_webapp_button(
                r.get('name') or r['code'],
                r['code'],
                "limit_up_first",
                webapp_base,
                suffix=suffix,
                prefix=f"{i}."
            ))
        build_pagination_buttons(page, total_pages, "lu:first", builder)
        builder.row(types.InlineKeyboardButton(text="◀️ 返回", callback_data="lu:main"))
    else:
        build_pagination_buttons(page, total_pages, "lu:first", builder)
        builder.row(types.InlineKeyboardButton(text="◀️ 返回", callback_data="lu:main"))

    return text, builder.as_markup()


@router.message(Command("first"))
async def cmd_first(message: types.Message):
    """Show first-board stocks."""
    if not await is_allowed(message.from_user.id):
        return
    text, markup = await _get_first_ui(chat_type=message.chat.type)
    await message.answer(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)


@router.callback_query(F.data.startswith("lu:first"))
async def cb_first(callback: types.CallbackQuery):
    """Show first-board stocks via callback."""
    await safe_answer(callback)
    parts = callback.data.split(":")
    page = int(parts[2]) if len(parts) > 2 else 1
    text, markup = await _get_first_ui(page, chat_type=callback.message.chat.type if callback.message else None)
    await safe_edit_text(callback.message, text, reply_markup=markup, disable_web_page_preview=True)


# ─────────────────────────────────────────────────────────────────────────────
# Burst Limit-Ups (曾涨停/炸板)
# ─────────────────────────────────────────────────────────────────────────────

async def _get_burst_ui(page: int = 1, chat_type: Optional[str] = None):
    """Build burst limit-up stocks UI."""
    PAGE_SIZE = 30
    webapp_base = get_webapp_base(chat_type)
    use_webapp_buttons = bool(webapp_base)

    try:
        stocks = await limit_up_service.get_realtime_limit_ups()
    except Exception:
        stocks = []

    if stocks:
        burst = [s for s in stocks if not s.get("is_sealed", True)]
        burst.sort(key=lambda x: -x.get("change_pct", 0))
    else:
        burst = []

    total = len(burst)
    page, total_pages, start_idx, end_idx = calculate_pagination(total, page, PAGE_SIZE)
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
    if use_webapp_buttons and rows:
        for i, r in enumerate(rows, start_idx + 1):
            cp = r.get('change_pct', 0)
            suffix = f"{cp:+.1f}%" if cp else None
            builder.row(build_webapp_button(
                r.get('name') or r['code'],
                r['code'],
                "limit_up_burst",
                webapp_base,
                suffix=suffix,
                prefix=f"{i}."
            ))
        build_pagination_buttons(page, total_pages, "lu:burst", builder)
        builder.row(types.InlineKeyboardButton(text="◀️ 返回", callback_data="lu:main"))
    else:
        build_pagination_buttons(page, total_pages, "lu:burst", builder)
        builder.row(types.InlineKeyboardButton(text="◀️ 返回", callback_data="lu:main"))

    return text, builder.as_markup()


@router.message(Command("burst"))
async def cmd_burst(message: types.Message):
    """Show burst limit-up stocks."""
    if not await is_allowed(message.from_user.id):
        return
    text, markup = await _get_burst_ui(chat_type=message.chat.type)
    await message.answer(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)


@router.callback_query(F.data.startswith("lu:burst"))
async def cb_burst(callback: types.CallbackQuery):
    """Show burst stocks via callback."""
    await safe_answer(callback)
    parts = callback.data.split(":")
    page = int(parts[2]) if len(parts) > 2 else 1
    text, markup = await _get_burst_ui(page, chat_type=callback.message.chat.type if callback.message else None)
    await safe_edit_text(callback.message, text, reply_markup=markup, disable_web_page_preview=True)


# ─────────────────────────────────────────────────────────────────────────────
# Streak Leaders (连板榜)
# ─────────────────────────────────────────────────────────────────────────────

async def _get_streak_ui(page: int = 1, chat_type: Optional[str] = None):
    """Build streak leaders UI."""
    PAGE_SIZE = 30
    webapp_base = get_webapp_base(chat_type)
    use_webapp_buttons = bool(webapp_base)
    streaks = await limit_up_service.get_streak_leaders()

    total = len(streaks)
    page, total_pages, start_idx, end_idx = calculate_pagination(total, page, PAGE_SIZE)
    rows = streaks[start_idx:end_idx]

    if not rows:
        text = "🔥 <b>连板榜</b>\n━━━━━━━━━━━━━━━━━━━━━\n📭 暂无连板股"
    else:
        text = f"🔥 <b>连板榜</b> ({start_idx+1}-{start_idx+len(rows)}/{total})\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        if use_webapp_buttons:
            text += "<i>点击下方按钮查看K线</i>\n"
        else:
            for i, s in enumerate(rows, start_idx + 1):
                name = s.get('name') or s.get('code')
                chart_url = get_chart_url(s['code'], name, context="limit_up_streak")
                text += f"{i}. <a href=\"{chart_url}\">{name}</a> ({s['code']}) - <b>{s['streak_count']}连板</b>\n"

    builder = InlineKeyboardBuilder()
    if use_webapp_buttons and rows:
        for i, s in enumerate(rows, start_idx + 1):
            suffix = f"{s['streak_count']}连板"
            builder.row(build_webapp_button(
                s.get('name') or s['code'],
                s['code'],
                "limit_up_streak",
                webapp_base,
                suffix=suffix,
                prefix=f"{i}."
            ))
        build_pagination_buttons(page, total_pages, "lu:streak", builder)
        builder.row(types.InlineKeyboardButton(text="◀️ 返回", callback_data="lu:main"))
    else:
        build_pagination_buttons(page, total_pages, "lu:streak", builder)
        builder.row(types.InlineKeyboardButton(text="◀️ 返回", callback_data="lu:main"))

    return text, builder.as_markup()


@router.message(Command("streak"))
async def cmd_streak(message: types.Message):
    """Show streak leaders."""
    if not await is_allowed(message.from_user.id):
        return
    text, markup = await _get_streak_ui(chat_type=message.chat.type)
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data.startswith("lu:streak"))
async def cb_streak(callback: types.CallbackQuery):
    """Show streak leaders via callback."""
    await safe_answer(callback)
    parts = callback.data.split(":")
    page = int(parts[2]) if len(parts) > 2 else 1
    text, markup = await _get_streak_ui(page, chat_type=callback.message.chat.type if callback.message else None)
    await safe_edit_text(callback.message, text, reply_markup=markup)


# ─────────────────────────────────────────────────────────────────────────────
# Strong Stocks (强势股)
# ─────────────────────────────────────────────────────────────────────────────

async def _get_strong_ui(page: int = 1, chat_type: Optional[str] = None):
    """Build strong stocks UI."""
    PAGE_SIZE = 30
    webapp_base = get_webapp_base(chat_type)
    use_webapp_buttons = bool(webapp_base)
    strong = await limit_up_service.get_strong_stocks()

    total = len(strong)
    page, total_pages, start_idx, end_idx = calculate_pagination(total, page, PAGE_SIZE)
    rows = strong[start_idx:end_idx]

    if not rows:
        text = "💪 <b>强势股</b> (7日)\n━━━━━━━━━━━━━━━━━━━━━\n📭 暂无强势股"
    else:
        text = f"💪 <b>强势股</b> (7日, {start_idx+1}-{start_idx+len(rows)}/{total})\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        if use_webapp_buttons:
            text += "<i>点击下方按钮查看K线</i>\n"
        else:
            for i, s in enumerate(rows, start_idx + 1):
                name = s.get('name') or s.get('code')
                chart_url = get_chart_url(s['code'], name, context="limit_up_strong")
                text += f"{i}. <a href=\"{chart_url}\">{name}</a> ({s['code']}) - {s['limit_count']}次涨停\n"

    builder = InlineKeyboardBuilder()
    if use_webapp_buttons and rows:
        for i, s in enumerate(rows, start_idx + 1):
            suffix = f"{s['limit_count']}次涨停"
            builder.row(build_webapp_button(
                s.get('name') or s['code'],
                s['code'],
                "limit_up_strong",
                webapp_base,
                suffix=suffix,
                prefix=f"{i}."
            ))
        build_pagination_buttons(page, total_pages, "lu:strong", builder)
        builder.row(types.InlineKeyboardButton(text="◀️ 返回", callback_data="lu:main"))
    else:
        build_pagination_buttons(page, total_pages, "lu:strong", builder)
        builder.row(types.InlineKeyboardButton(text="◀️ 返回", callback_data="lu:main"))

    return text, builder.as_markup()


@router.message(Command("strong"))
async def cmd_strong(message: types.Message):
    """Show strong stocks."""
    if not await is_allowed(message.from_user.id):
        return
    text, markup = await _get_strong_ui(chat_type=message.chat.type)
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data.startswith("lu:strong"))
async def cb_strong(callback: types.CallbackQuery):
    """Show strong stocks via callback."""
    await safe_answer(callback)
    parts = callback.data.split(":")
    page = int(parts[2]) if len(parts) > 2 else 1
    text, markup = await _get_strong_ui(page, chat_type=callback.message.chat.type if callback.message else None)
    await safe_edit_text(callback.message, text, reply_markup=markup)


# ─────────────────────────────────────────────────────────────────────────────
# Startup Watchlist (启动追踪)
# ─────────────────────────────────────────────────────────────────────────────

async def _get_watch_ui(page: int = 1, chat_type: Optional[str] = None):
    """Build startup watchlist UI."""
    PAGE_SIZE = 30
    webapp_base = get_webapp_base(chat_type)
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
    page, total_pages, start_idx, end_idx = calculate_pagination(total, page, PAGE_SIZE)
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
    if use_webapp_buttons and rows:
        for i, w in enumerate(rows, start_idx + 1):
            limit_date = w['first_limit_date'].strftime('%m/%d') if w['first_limit_date'] else None
            builder.row(build_webapp_button(
                w.get('name') or w['code'],
                w['code'],
                "limit_up_watch",
                webapp_base,
                suffix=limit_date,
                prefix=f"{i}."
            ))
        build_pagination_buttons(page, total_pages, "lu:watch", builder)
        builder.row(types.InlineKeyboardButton(text="◀️ 返回", callback_data="lu:main"))
    else:
        build_pagination_buttons(page, total_pages, "lu:watch", builder)
        builder.row(types.InlineKeyboardButton(text="◀️ 返回", callback_data="lu:main"))

    return text, builder.as_markup()


@router.message(Command("startup"))
async def cmd_startup(message: types.Message):
    """View limit-up startup watchlist."""
    if not await is_allowed(message.from_user.id):
        return
    text, markup = await _get_watch_ui(chat_type=message.chat.type)
    await message.answer(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)


@router.callback_query(F.data.startswith("lu:watch"))
async def cb_watch(callback: types.CallbackQuery):
    """Show startup watchlist via callback."""
    await safe_answer(callback)
    parts = callback.data.split(":")
    page = int(parts[2]) if len(parts) > 2 else 1
    text, markup = await _get_watch_ui(page, chat_type=callback.message.chat.type if callback.message else None)
    await safe_edit_text(callback.message, text, reply_markup=markup, disable_web_page_preview=True)


# ─────────────────────────────────────────────────────────────────────────────
# Sync Limit-Up
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("sync"))
async def cmd_sync(message: types.Message):
    """Sync limit-up data."""
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
    """Sync limit-up data via callback."""
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
# Limit-Up Reports (Manual Trigger)
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("limitup"))
async def cmd_limitup(message: types.Message):
    """Manual trigger for limit-up reports."""
    if not await is_allowed(message.from_user.id):
        return

    import asyncio
    from aiogram.filters import CommandObject

    # Get command args
    text = message.text or ""
    args = text.split(maxsplit=1)[1] if len(text.split()) > 1 else ""

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
