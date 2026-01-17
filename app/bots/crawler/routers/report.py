"""
Market Report Router

Handles market reports: weekly/monthly reports, on-demand analysis.
"""

from aiogram import Router, F, types
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest

from app.services.market_report import market_report_service

from .common import is_allowed, safe_answer, safe_edit_text

router = Router()


# ─────────────────────────────────────────────────────────────────────────────
# Report Main Menu
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "report:main")
async def cb_report_main(callback: types.CallbackQuery):
    """Show market report main menu."""
    await safe_answer(callback)

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

    await safe_edit_text(callback.message, text, reply_markup=builder.as_markup())


# ─────────────────────────────────────────────────────────────────────────────
# On-Demand Report
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
# Weekly Report
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "report:weekly")
async def cb_report_weekly(callback: types.CallbackQuery):
    """Generate weekly report."""
    await safe_answer(callback, "生成周报中...")

    try:
        try:
            await callback.message.edit_text("📊 正在生成周报...\n\n⏳ 需要AI分析，请稍候", parse_mode="HTML")
        except TelegramBadRequest:
            pass

        report = await market_report_service.generate_weekly_report()

        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 刷新", callback_data="report:weekly")
        builder.button(text="◀️ 返回", callback_data="report:main")
        builder.adjust(2)

        try:
            await callback.message.edit_text(report, parse_mode="HTML", reply_markup=builder.as_markup())
        except TelegramBadRequest as e:
            if "not modified" not in str(e):
                raise
    except Exception as e:
        try:
            await callback.message.edit_text(f"❌ 周报生成失败: {e}")
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Monthly Report
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "report:monthly")
async def cb_report_monthly(callback: types.CallbackQuery):
    """Generate monthly report."""
    await safe_answer(callback, "生成月报中...")

    try:
        try:
            await callback.message.edit_text("📈 正在生成月报...\n\n⏳ 需要AI分析，请稍候", parse_mode="HTML")
        except TelegramBadRequest:
            pass

        report = await market_report_service.generate_monthly_report()

        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 刷新", callback_data="report:monthly")
        builder.button(text="◀️ 返回", callback_data="report:main")
        builder.adjust(2)

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


# ─────────────────────────────────────────────────────────────────────────────
# Days Report
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("report:days:"))
async def cb_report_days(callback: types.CallbackQuery):
    """Generate N-day report."""
    days = int(callback.data.split(":")[2])
    await safe_answer(callback, f"生成{days}日报告...")

    try:
        try:
            await callback.message.edit_text(f"📋 正在生成近{days}日市场报告...\n\n⏳ 需要AI分析，请稍候", parse_mode="HTML")
        except TelegramBadRequest:
            pass

        report = await market_report_service.generate_on_demand_report(days=days)

        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 刷新", callback_data=f"report:days:{days}")
        builder.button(text="◀️ 返回", callback_data="report:main")
        builder.adjust(2)

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
