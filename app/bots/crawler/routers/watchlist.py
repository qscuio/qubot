"""
Watchlist Router

Handles user watchlist: adding/removing stocks, viewing with prices.
"""

from typing import Optional

from aiogram import Router, F, types
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.services.watchlist import watchlist_service
from app.core.stock_links import get_chart_url
from app.core.logger import Logger

from .common import (
    is_allowed, safe_answer, safe_edit_text,
    get_webapp_base, build_webapp_button,
)

logger = Logger("WatchlistRouter")
router = Router()


# ─────────────────────────────────────────────────────────────────────────────
# Add Stock to Watchlist
# ─────────────────────────────────────────────────────────────────────────────

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
            text, markup = await _get_watchlist_ui(message.from_user.id, chat_type=message.chat.type)
            await status.edit_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
        except Exception as e:
            await status.edit_text(f"❌ 加载失败: {e}")
        return

    parts = args.split(maxsplit=1)
    code = parts[0].strip()
    name = parts[1].strip() if len(parts) > 1 else None

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


# ─────────────────────────────────────────────────────────────────────────────
# Remove Stock from Watchlist
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
# View Watchlist
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("mywatch"))
async def cmd_mywatch(message: types.Message):
    """View watchlist with real-time prices."""
    if not await is_allowed(message.from_user.id):
        return

    status = await message.answer("⏳ 正在加载自选列表...")

    try:
        text, markup = await _get_watchlist_ui(message.from_user.id, chat_type=message.chat.type)
        await status.edit_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
    except Exception as e:
        await status.edit_text(f"❌ 加载失败: {e}")


async def _get_watchlist_ui(
    user_id: int,
    realtime: bool = False,
    chat_type: Optional[str] = None,
    page: int = 0
) -> tuple[str, types.InlineKeyboardMarkup]:
    """Build watchlist UI with prices."""
    PAGE_SIZE = 20

    webapp_base = get_webapp_base(chat_type)
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
    page = max(0, min(page, total_pages - 1))
    start_idx = page * PAGE_SIZE
    end_idx = min(start_idx + PAGE_SIZE, total_stocks)
    page_stocks = stocks[start_idx:end_idx]

    # Header
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
            icon = "🟢"
        elif total > 0:
            icon = "⬆️"
        elif total > -5:
            icon = "⬇️"
        else:
            icon = "🔴"

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
            builder.row(build_webapp_button(
                name,
                code,
                "watchlist",
                webapp_base,
                suffix=suffix,
                prefix=f"{icon}{idx}."
            ))

    # Delete buttons for current page stocks (limit to 8)
    del_buttons = []
    for s in page_stocks[:8]:
        name_short = s.get('name', s['code'])[:6]
        del_buttons.append(
            types.InlineKeyboardButton(text=f"❌ {name_short}", callback_data=f"watch:del:{s['code']}")
        )
    if del_buttons:
        for i in range(0, len(del_buttons), 4):
            builder.row(*del_buttons[i:i + 4])

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


@router.callback_query(F.data.startswith("watch:list"))
async def cb_watch_list(callback: types.CallbackQuery):
    """View watchlist (cached prices) with pagination."""
    await safe_answer(callback)

    parts = callback.data.split(":")
    page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0

    try:
        await callback.message.edit_text("⏳ 正在加载...", parse_mode="HTML")
        text, markup = await _get_watchlist_ui(
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

    parts = callback.data.split(":")
    page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0

    try:
        await callback.message.edit_text("⏳ 正在获取实时行情...", parse_mode="HTML")
        text, markup = await _get_watchlist_ui(
            callback.from_user.id,
            realtime=True,
            chat_type=callback.message.chat.type if callback.message else None,
            page=page
        )
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
    except Exception as e:
        await callback.message.edit_text(f"❌ 加载失败: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Clear Watchlist
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "watch:clear")
async def cb_watch_clear(callback: types.CallbackQuery):
    """Ask for confirmation to clear watchlist."""
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


# ─────────────────────────────────────────────────────────────────────────────
# Delete Single Stock
# ─────────────────────────────────────────────────────────────────────────────

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
        text, markup = await _get_watchlist_ui(
            callback.from_user.id,
            realtime=False,
            chat_type=callback.message.chat.type if callback.message else None
        )
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
    except Exception:
        pass
