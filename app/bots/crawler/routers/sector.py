"""
Sector Router

Handles sector analysis: industry/concept sectors, strong/weak sectors, sync and reports.
"""

from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.services.sector import sector_service

from .common import is_allowed, safe_answer, safe_edit_text

router = Router()


# ─────────────────────────────────────────────────────────────────────────────
# Sector Main Menu
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "sector:main")
async def cb_sector_main(callback: types.CallbackQuery):
    """Show sector analysis main menu."""
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

    await safe_edit_text(callback.message, text, reply_markup=builder.as_markup())


# ─────────────────────────────────────────────────────────────────────────────
# Industry/Concept Sectors
# ─────────────────────────────────────────────────────────────────────────────

async def _get_sector_ui(sector_type: str) -> tuple[str, types.InlineKeyboardMarkup]:
    """Build sector list UI."""
    sectors = await sector_service.get_realtime_sectors(sector_type=sector_type, limit=20)

    type_name = "行业板块" if sector_type == "industry" else "概念板块"
    type_icon = "🏭" if sector_type == "industry" else "💡"

    if not sectors:
        text = f"{type_icon} <b>{type_name}</b>\n━━━━━━━━━━━━━━━━━━━━━\n📭 暂无数据\n\n点击同步获取"
    else:
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


@router.message(Command("industry"))
async def cmd_industry(message: types.Message):
    """Show industry sectors."""
    if not await is_allowed(message.from_user.id):
        return
    text, markup = await _get_sector_ui("industry")
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "sector:industry")
async def cb_industry(callback: types.CallbackQuery):
    """Show industry sectors via callback."""
    await safe_answer(callback)
    text, markup = await _get_sector_ui("industry")
    await safe_edit_text(callback.message, text, reply_markup=markup)


@router.message(Command("concept"))
async def cmd_concept(message: types.Message):
    """Show concept sectors."""
    if not await is_allowed(message.from_user.id):
        return
    text, markup = await _get_sector_ui("concept")
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "sector:concept")
async def cb_concept(callback: types.CallbackQuery):
    """Show concept sectors via callback."""
    await safe_answer(callback)
    text, markup = await _get_sector_ui("concept")
    await safe_edit_text(callback.message, text, reply_markup=markup)


# ─────────────────────────────────────────────────────────────────────────────
# Strong Sectors
# ─────────────────────────────────────────────────────────────────────────────

async def _get_hot_ui(days: int) -> tuple[str, types.InlineKeyboardMarkup]:
    """Build strong sectors UI."""
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


@router.message(Command("hot7"))
async def cmd_hot7(message: types.Message):
    """Show 7-day strong sectors."""
    if not await is_allowed(message.from_user.id):
        return
    text, markup = await _get_hot_ui(7)
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.message(Command("hot14"))
async def cmd_hot14(message: types.Message):
    """Show 14-day strong sectors."""
    if not await is_allowed(message.from_user.id):
        return
    text, markup = await _get_hot_ui(14)
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.message(Command("hot30"))
async def cmd_hot30(message: types.Message):
    """Show 30-day strong sectors."""
    if not await is_allowed(message.from_user.id):
        return
    text, markup = await _get_hot_ui(30)
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data.startswith("sector:hot:"))
async def cb_hot(callback: types.CallbackQuery):
    """Show strong sectors via callback."""
    await safe_answer(callback)
    days = int(callback.data.split(":")[2])
    text, markup = await _get_hot_ui(days)
    await safe_edit_text(callback.message, text, reply_markup=markup)


# ─────────────────────────────────────────────────────────────────────────────
# Weak Sectors
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "sector:weak")
async def cb_weak(callback: types.CallbackQuery):
    """Show weak sectors."""
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

    await safe_edit_text(callback.message, text, reply_markup=builder.as_markup())


# ─────────────────────────────────────────────────────────────────────────────
# Sector Sync
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("sector_sync"))
async def cmd_sector_sync(message: types.Message):
    """Sync sector data."""
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
    """Sync sector data via callback."""
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
# Sector Report
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "sector:report")
async def cb_sector_report(callback: types.CallbackQuery):
    """Generate sector daily report."""
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
