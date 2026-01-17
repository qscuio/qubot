"""
Trading Simulator Router

Handles simulated trading: portfolio, P&L, trade history, manual scans.
"""

from aiogram import Router, F, types
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.services.trading_simulator import trading_simulator, MAX_POSITIONS

from .common import is_allowed, safe_answer, safe_edit_text

router = Router()


# ─────────────────────────────────────────────────────────────────────────────
# Simulator Main Menu
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "sim:main")
async def cb_sim_main(callback: types.CallbackQuery):
    """Show trading simulator main menu."""
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

    await safe_edit_text(callback.message, text, reply_markup=builder.as_markup())


# ─────────────────────────────────────────────────────────────────────────────
# Portfolio
# ─────────────────────────────────────────────────────────────────────────────

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
    """Show portfolio via callback."""
    await safe_answer(callback)
    report = await trading_simulator.generate_portfolio_report()

    builder = InlineKeyboardBuilder()
    builder.button(text="📉 盈亏统计", callback_data="sim:pnl")
    builder.button(text="📜 交易历史", callback_data="sim:trades")
    builder.button(text="🔄 刷新", callback_data="sim:portfolio")
    builder.adjust(2, 1)

    await safe_edit_text(callback.message, report, reply_markup=builder.as_markup())


# ─────────────────────────────────────────────────────────────────────────────
# P&L Statistics
# ─────────────────────────────────────────────────────────────────────────────

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
    """Show P&L via callback."""
    await safe_answer(callback)
    report = await trading_simulator.generate_pnl_report()

    builder = InlineKeyboardBuilder()
    builder.button(text="📊 持仓", callback_data="sim:portfolio")
    builder.button(text="📜 历史", callback_data="sim:trades")
    builder.button(text="🔄 刷新", callback_data="sim:pnl")
    builder.adjust(2, 1)

    await safe_edit_text(callback.message, report, reply_markup=builder.as_markup())


# ─────────────────────────────────────────────────────────────────────────────
# Trade History
# ─────────────────────────────────────────────────────────────────────────────

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
    """Show trade history via callback."""
    await safe_answer(callback)
    report = await trading_simulator.generate_trades_report()

    builder = InlineKeyboardBuilder()
    builder.button(text="📊 持仓", callback_data="sim:portfolio")
    builder.button(text="📉 盈亏", callback_data="sim:pnl")
    builder.button(text="🔄 刷新", callback_data="sim:trades")
    builder.button(text="◀️ 返回", callback_data="sim:main")
    builder.adjust(2, 2)

    await safe_edit_text(callback.message, report, reply_markup=builder.as_markup())


# ─────────────────────────────────────────────────────────────────────────────
# Sim Command (Multi-purpose)
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
# Manual Scan
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "sim:scan")
async def cb_sim_scan(callback: types.CallbackQuery):
    """Trigger manual scan via callback."""
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
