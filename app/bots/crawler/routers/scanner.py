"""
Stock Scanner Router

Handles stock signal scanning: various technical signals, database sync, and results pagination.
"""

import time
from typing import Optional

from aiogram import Router, F, types, Bot
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.services.stock_scanner import stock_scanner
from app.core.database import db
from app.core.timezone import china_today
from app.core.stock_links import get_chart_url
from app.core.logger import Logger

from .common import (
    is_allowed, safe_answer, safe_edit_text,
    get_webapp_base, build_webapp_button,
)

logger = Logger("ScannerRouter")
router = Router()

# Cache for scan results (store in memory for pagination)
_scan_results_cache = {}

# Signal name and icon mappings
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
    "strong_fanbao": "强势股反包",
    "broken_limit_up_streak": "连板断板",
    "pullback_ma5": "5日线回踩",
    "pullback_ma20": "20日线回踩",
    "pullback_ma30": "30日线回踩",
    "pullback_ma5_weekly": "5周线回踩",
    "multi_signal": "多信号共振",
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
    "low_weekly_2_bullish": "低位周线两连阳",
    "weekly_3_bullish": "低位周线三连阳",
    "weekly_4_bullish": "低位周线四连阳",
    "low_monthly_2_bullish": "低位月线两连阳",
    "monthly_3_bullish": "低位月线3连阳",
    "monthly_3_bullish": "低位月线3连阳",
    "monthly_4_bullish": "低位月线四连阳",
    "low_accumulation_launch": "低位潜伏启动",
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
    "low_weekly_2_bullish": "📊",
    "weekly_3_bullish": "📈",
    "weekly_4_bullish": "🚀",
    "low_monthly_2_bullish": "📅",
    "monthly_3_bullish": "🌙",
    "monthly_3_bullish": "🌙",
    "monthly_4_bullish": "🌕",
    "low_accumulation_launch": "🚀",
}


# ─────────────────────────────────────────────────────────────────────────────
# Scanner Main Menu
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "scanner:main")
async def cb_scanner_main(callback: types.CallbackQuery):
    """Show signal scanner main menu."""
    await safe_answer(callback)

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
    builder.button(text="🚀 低位潜伏启动", callback_data="scanner:scan:low_accumulation_launch")
    builder.button(text="⚡ 底部快启动", callback_data="scanner:scan:bottom_quick_start")
    builder.button(text="🧭 长周期刚逆转", callback_data="scanner:scan:long_cycle_reversal")
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
    builder.button(text="↩️ 强势股反包", callback_data="scanner:scan:strong_fanbao")
    builder.button(text="🏚️ 昨日断板", callback_data="scanner:scan:yesterday_broken_board")
    builder.button(text="🏚️ 前日断板", callback_data="scanner:scan:day_before_yesterday_broken_board")
    builder.button(text="💔 连板断板", callback_data="scanner:scan:broken_limit_up_streak")
    builder.button(text="↩️ 5日线回踩", callback_data="scanner:scan:pullback_ma5")
    builder.button(text="🔄 20日线回踩", callback_data="scanner:scan:pullback_ma20")
    builder.button(text="🔙 30日线回踩", callback_data="scanner:scan:pullback_ma30")
    builder.button(text="📅 5周线回踩", callback_data="scanner:scan:pullback_ma5_weekly")
    builder.button(text="📊 低位周线两连阳", callback_data="scanner:scan:low_weekly_2_bullish")
    builder.button(text="📈 低位周线三连阳", callback_data="scanner:scan:weekly_3_bullish")
    builder.button(text="🚀 低位周线四连阳", callback_data="scanner:scan:weekly_4_bullish")
    builder.button(text="📅 低位月线两连阳", callback_data="scanner:scan:low_monthly_2_bullish")
    builder.button(text="🌙 低位月线3连阳", callback_data="scanner:scan:monthly_3_bullish")
    builder.button(text="🌕 低位月线四连阳", callback_data="scanner:scan:monthly_4_bullish")

    # Trend Signals (LinReg)
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

    builder.adjust(4, 2, 2, 2, 3, 2, 2, 2, 2, 1, 3, 2, 2, 3, 3, 3, 2, 2, 1)

    try:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Scan Command and Callbacks
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("scan"))
async def cmd_scan(message: types.Message, command: CommandObject = None, force: bool = False, signal_type: str = "all"):
    """Run stock signal scan."""
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

    last_update_time = time.time()

    async def on_progress(current, total, phase="scanning"):
        nonlocal last_update_time
        now = time.time()
        if now - last_update_time < 1.0 and current < total:
            return

        last_update_time = now
        percent = int(current / total * 100) if total > 0 else 0
        progress_bar = "▓" * (percent // 10) + "░" * (10 - (percent // 10))

        phase_text = "⏳ 正在加载数据..." if phase == "loading" else "🔍 正在扫描..."
        
        try:
            await status.edit_text(
                f"{phase_text} ({SIGNAL_NAMES.get(signal_type, '全部')})\n\n"
                f"⏳ 进度: {percent}% ({current}/{total})\n"
                f"{progress_bar}"
            )
        except Exception:
            pass

    try:
        # If user selected a specific signal, only scan that one
        if signal_type != "all":
            enabled_signals = [signal_type]
        else:
            enabled_signals = None  # Scan all
            
        signals = await stock_scanner.scan_all_stocks(
            force=force, 
            progress_callback=on_progress,
            enabled_signals=enabled_signals
        )

        if not signals or all(len(v) == 0 for v in signals.values()):
            cache_note = "\n\n♻️ 使用缓存结果（数据库未更新）" if stock_scanner.last_scan_used_cache else ""
            await status.answer(f"🔍 扫描完成\n\n📭 暂无信号{cache_note}")
            return

        # Cache results for pagination
        _scan_results_cache[user_id] = signals

        # Send summary header
        total_signals = sum(len(v) for v in signals.values())
        cache_note = "♻️ 使用缓存结果（数据库未更新）\n\n" if stock_scanner.last_scan_used_cache else ""
        summary = (
            "🔍 <b>启动信号扫描完成</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{cache_note}"
        )
        for sig_type, stocks in signals.items():
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
            if signal_type != "all" and sig_type != signal_type:
                continue
            if stocks:
                icon = SIGNAL_ICONS.get(sig_type, "•")
                name = SIGNAL_NAMES.get(sig_type, sig_type)
                await _send_signal_list(
                    sender,
                    f"{icon} <b>{name}</b> ({len(stocks)}只)",
                    stocks,
                    context=f"scanner_{sig_type}",
                    chat_type=chat_type
                )

    except Exception as e:
        await status.answer(f"❌ 扫描失败: {e}")


async def _send_signal_list(
    sender,
    title: str,
    stocks: list,
    context: str,
    page: int = 1,
    page_size: int = 20,
    chat_type: Optional[str] = None
):
    """Send paginated signal list."""
    if not stocks:
        return

    total_stocks = len(stocks)
    total_pages = (total_stocks + page_size - 1) // page_size

    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages

    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    current_page_stocks = stocks[start_idx:end_idx]

    webapp_base = get_webapp_base(chat_type)
    use_webapp_buttons = bool(webapp_base)

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

    builder = InlineKeyboardBuilder()
    if use_webapp_buttons:
        for i, s in enumerate(current_page_stocks, start_idx + 1):
            suffix = None
            if s.get("signal_count"):
                suffix = f"{s['signal_count']}信号"
            builder.row(build_webapp_button(
                s.get('name') or s['code'],
                s['code'],
                context or "scanner",
                webapp_base,
                suffix=suffix,
                prefix=f"{i}."
            ))

    nav_buttons = []
    if page > 1:
        nav_buttons.append(types.InlineKeyboardButton(text="⬅️ 上一页", callback_data=f"scanner:page:{context}:{page-1}"))
    if page < total_pages:
        nav_buttons.append(types.InlineKeyboardButton(text="下一页 ➡️", callback_data=f"scanner:page:{context}:{page+1}"))

    if nav_buttons:
        builder.row(*nav_buttons)

    builder.row(types.InlineKeyboardButton(text="◀️ 返回菜单", callback_data="scanner:main"))

    await sender.answer(text, parse_mode="HTML", reply_markup=builder.as_markup(), disable_web_page_preview=True)


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
    parts = callback.data.split(":")
    signal_type = parts[2] if len(parts) > 2 else "all"
    force = signal_type == "force"

    if signal_type == "force":
        signal_type = "all"

    await _run_scan_from_callback(callback, force=force, signal_type=signal_type)


@router.callback_query(F.data.startswith("scanner:page:"))
async def cb_scanner_page(callback: types.CallbackQuery):
    """Handle scanner pagination."""
    try:
        parts = callback.data.split(":")
        if len(parts) < 4:
            await callback.answer("无效请求")
            return

        context = parts[2]
        page = int(parts[3])
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

        await _send_signal_list(
            callback.message,
            title,
            stocks,
            context=context,
            page=page,
            chat_type=callback.message.chat.type if callback.message else None
        )
        await callback.answer()

    except Exception as e:
        await callback.answer(f"❌ 错误: {e}", show_alert=True)


@router.callback_query(F.data == "lu:scan")
async def cb_scan(callback: types.CallbackQuery):
    """Trigger scan from limit-up menu."""
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
    webapp_base = get_webapp_base(chat_type)
    use_webapp_buttons = bool(webapp_base)
    context = f"scanner_{signal_type}"

    if use_webapp_buttons:
        text += "<i>点击下方按钮查看K线</i>\n"
    else:
        for i, s in enumerate(page_stocks, start + 1):
            stock_name = s.get('name') or s.get('code')
            chart_url = get_chart_url(s['code'], stock_name, context=context)
            text += f"{i}. <a href=\"{chart_url}\">{stock_name}</a> ({s['code']})\n"

    builder = InlineKeyboardBuilder()
    if use_webapp_buttons:
        for i, s in enumerate(page_stocks, start + 1):
            suffix = None
            if s.get("signal_count"):
                suffix = f"{s['signal_count']}信号"
            builder.row(build_webapp_button(
                s.get('name') or s['code'],
                s['code'],
                context,
                webapp_base,
                suffix=suffix,
                prefix=f"{i}."
            ))

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
        await callback.message.answer("📭 缓存已失效，请重新扫描")
        return

    chat_type = callback.message.chat.type if callback.message else None
    webapp_base = get_webapp_base(chat_type)
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


# ─────────────────────────────────────────────────────────────────────────────
# Database Check and Sync
# ─────────────────────────────────────────────────────────────────────────────

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
        last_time = [0.0]
        async def progress_cb(stage: str, current: int, total: int, message: str):
            now = time.time()
            if now - last_time[0] < 10 and current < total:
                return
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
    """Check stock_history database status."""
    if not await is_allowed(message.from_user.id):
        return

    from app.services.stock_history import stock_history_service

    status = await message.answer("⏳ 检查数据库状态...")

    try:
        stats = await stock_history_service.get_stats()

        if not stats:
            await status.edit_text("❌ 数据库未连接")
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
            text += "\n💡 <b>建议:</b> 执行 /dbsync 同步数据"
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

    status_msg = await message.answer("⏳ 正在后台同步数据（含完整性检查）...\n\n会定时推送进度通知")

    def make_progress_callback(msg_obj):
        last_time = [0.0]
        async def progress_cb(stage: str, current: int, total: int, msg: str):
            now = time.time()
            if now - last_time[0] < 1.5 and current < total:
                return
            last_time[0] = now

            percent = int(current / total * 100) if total > 0 else 0
            progress_bar = "▓" * (percent // 10) + "░" * (10 - (percent // 10))

            formatted_msg = (
                f"{msg}\n"
                f"⏳ 进度: {percent}% ({current}/{total})\n"
                f"{progress_bar}"
            )

            try:
                if formatted_msg != msg_obj.text:
                    await msg_obj.edit_text(formatted_msg, parse_mode="HTML")
            except Exception as e:
                if "message is not modified" not in str(e).lower():
                    logger.error(f"Failed to update progress message: {e}")
        return progress_cb

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

    def make_progress_callback(msg_obj):
        last_time = [0.0]
        async def progress_cb(stage: str, current: int, total: int, msg: str):
            now = time.time()
            if now - last_time[0] < 1.5 and current < total:
                return
            last_time[0] = now

            percent = int(current / total * 100) if total > 0 else 0
            progress_bar = "▓" * (percent // 10) + "░" * (10 - (percent // 10))

            formatted_msg = (
                f"{msg}\n"
                f"⏳ 进度: {percent}% ({current}/{total})\n"
                f"{progress_bar}"
            )

            try:
                if formatted_msg != msg_obj.text:
                    await msg_obj.edit_text(formatted_msg, parse_mode="HTML")
            except Exception as e:
                if "message is not modified" not in str(e).lower():
                    logger.error(f"Failed to update progress message: {e}")
        return progress_cb

    try:
        await callback.message.edit_text("⏳ 正在后台同步数据（含完整性检查）...\n\n会定时推送进度通知")
        asyncio.create_task(stock_history_service.sync_with_integrity_check(make_progress_callback(callback.message)))

    except Exception as e:
        await callback.message.edit_text(f"❌ 同步失败: {e}")


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

    text = f"📜 <b>HISTORY: {code}</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
    text += "<code>Date       Close   Chg%   Vol</code>\n"

    for h in history:
        date_str = h['date'].strftime("%m-%d")
        close = h['close']
        pct = h['change_pct']
        vol = h['volume'] / 10000

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

    from app.core.config import settings

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

    webapp_url = None
    if settings.WEBFRONT_URL:
        webapp_url = f"{settings.WEBFRONT_URL.rstrip('/')}/miniapp/chart/?code={code}"
    else:
        webapp_url = get_chart_url(code)

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
