"""
Daban (打板) Router

Handles limit-up board trading: analysis, portfolio, signals, sentiment.
"""

from aiogram import Router, F, types
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.services.daban_service import daban_service
from app.services.daban_simulator import daban_simulator, MAX_POSITIONS as DABAN_MAX_POSITIONS

from .common import is_allowed, safe_answer, safe_edit_text

router = Router()


# ─────────────────────────────────────────────────────────────────────────────
# Daban Command
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("daban"))
async def cmd_daban(message: types.Message, command: CommandObject):
    """Daban service commands.

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


# ─────────────────────────────────────────────────────────────────────────────
# Daban Main Menu
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "daban:main")
async def cb_daban_main(callback: types.CallbackQuery):
    """Show daban main menu."""
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


# ─────────────────────────────────────────────────────────────────────────────
# Portfolio
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "daban:portfolio")
async def cb_daban_portfolio(callback: types.CallbackQuery):
    """Show daban portfolio."""
    await safe_answer(callback)

    report = await daban_simulator.generate_portfolio_report()

    builder = InlineKeyboardBuilder()
    builder.button(text="📊 统计", callback_data="daban:stats")
    builder.button(text="🔄 刷新", callback_data="daban:portfolio")
    builder.button(text="◀️ 返回", callback_data="daban:main")
    builder.adjust(2, 1)

    await safe_edit_text(callback.message, report, reply_markup=builder.as_markup())


# ─────────────────────────────────────────────────────────────────────────────
# Statistics
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "daban:stats")
async def cb_daban_stats(callback: types.CallbackQuery):
    """Show daban statistics."""
    await safe_answer(callback)

    report = await daban_simulator.generate_stats_report()

    builder = InlineKeyboardBuilder()
    builder.button(text="📦 持仓", callback_data="daban:portfolio")
    builder.button(text="🔄 刷新", callback_data="daban:stats")
    builder.button(text="◀️ 返回", callback_data="daban:main")
    builder.adjust(2, 1)

    await safe_edit_text(callback.message, report, reply_markup=builder.as_markup())


# ─────────────────────────────────────────────────────────────────────────────
# Scan
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "daban:scan")
async def cb_daban_scan(callback: types.CallbackQuery):
    """Trigger daban scan."""
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


# ─────────────────────────────────────────────────────────────────────────────
# Sentiment
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
# Live Monitoring
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
# Signals
# ─────────────────────────────────────────────────────────────────────────────

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
