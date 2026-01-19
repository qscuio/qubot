"""
AI Market Analysis Router

Handles commands and callbacks for AI market analysis feature.
- /ai_analysis [period] - Manual trigger for market analysis
- Callback handlers for menu buttons
"""

from aiogram import Router, F, types
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest

from app.services.market_ai_analysis import market_ai_analysis_service

from .common import is_allowed, safe_answer, safe_edit_text

router = Router()


# ─────────────────────────────────────────────────────────────────────────────
# Main Menu
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "ai_analysis:main")
async def cb_ai_analysis_main(callback: types.CallbackQuery):
    """Show AI analysis main menu."""
    await safe_answer(callback)
    
    # Status check (simplified)
    # The new service structure might not expose get_status directly yet, 
    # but let's assume we want to just show the menu.
    
    text = (
        "🤖 <b>AI 行情复盘</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "基于每日收盘数据，生成深度复盘报告。\n\n"
        "⏰ <b>自动发送</b>：每日 15:30 (交易日)\n"
        "🎯 <b>分析内容</b>：指数, 板块, 龙头股深度技剖"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 生成今日复盘", callback_data="ai_analysis:daily")
    builder.button(text="◀️ 返回", callback_data="main")
    builder.adjust(1)
    
    await safe_edit_text(callback.message, text, reply_markup=builder.as_markup())


# ─────────────────────────────────────────────────────────────────────────────
# Manual Command
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("ai_analysis"))
async def cmd_ai_analysis(message: types.Message):
    """
    Generate AI market analysis on-demand (Daily).
    """
    if not await is_allowed(message.from_user.id):
        return
    
    status_msg = await message.answer(
        "🤖 正在生成<b>今日A股复盘报告</b>...\n\n"
        "⏳ 正在采集全市场数据并进行AI深度分析，耗时约30秒..."
    )
    
    try:
        # Use the specific daily report method
        report = await market_ai_analysis_service.generate_daily_report()
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 刷新", callback_data="ai_analysis:daily")
        builder.button(text="◀️ 返回菜单", callback_data="ai_analysis:main")
        builder.adjust(2)
        
        await status_msg.edit_text(report, parse_mode="HTML", reply_markup=builder.as_markup())
    except Exception as e:
        await status_msg.edit_text(f"❌ 分析生成失败: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Callbacks
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "ai_analysis:daily")
async def cb_ai_analysis_daily(callback: types.CallbackQuery):
    """Generate daily analysis."""
    await safe_answer(callback, "正在生成报告...")
    
    try:
        try:
            await callback.message.edit_text(
                "🤖 正在生成<b>今日A股复盘报告</b>...\n\n⏳ 正在采集数据与AI分析，请稍候...",
                parse_mode="HTML"
            )
        except TelegramBadRequest:
            pass
        
        report = await market_ai_analysis_service.generate_daily_report()
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 刷新", callback_data="ai_analysis:daily")
        builder.button(text="◀️ 返回菜单", callback_data="ai_analysis:main")
        builder.adjust(2)
        
        try:
            await callback.message.edit_text(
                report, 
                parse_mode="HTML", 
                reply_markup=builder.as_markup()
            )
        except TelegramBadRequest as e:
            if "not modified" not in str(e):
                raise
    except Exception as e:
        try:
            await callback.message.edit_text(f"❌ 报告生成失败: {e}")
        except Exception:
            pass
