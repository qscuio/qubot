"""
Main Menu Router

Handles the main menu, start command, and help command.
"""

from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.services.crawler import crawler_service
from app.services.limit_up import limit_up_service

from .common import is_allowed, safe_answer, safe_edit_text

router = Router()


# ─────────────────────────────────────────────────────────────────────────────
# Start Command & Main Menu
# ─────────────────────────────────────────────────────────────────────────────

async def _build_main_menu() -> tuple[str, types.InlineKeyboardMarkup]:
    """Build main menu text and keyboard."""
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
    builder.button(text="🤖 AI行情", callback_data="ai_analysis:main")
    builder.button(text="🔄 同步数据", callback_data="scanner:dbsync")
    builder.adjust(2, 2, 2, 2, 2)

    return text, builder.as_markup()


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    """Handle /start command - show main menu."""
    if not await is_allowed(message.from_user.id):
        return

    text, markup = await _build_main_menu()
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "main")
async def cb_main(callback: types.CallbackQuery):
    """Handle main menu callback."""
    await safe_answer(callback)

    text, markup = await _build_main_menu()
    await safe_edit_text(callback.message, text, reply_markup=markup)


# ─────────────────────────────────────────────────────────────────────────────
# Help Command
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("help"))
async def cmd_help(message: types.Message):
    """Handle /help command - show all available commands."""
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
        "/userlist - 用户列表\n\n"
        "<b>📼 历史</b>\n"
        "/save_history - 保存聊天记录\n"
        "/get_history - 查询聊天记录"
    )
    await message.answer(text, parse_mode="HTML")
