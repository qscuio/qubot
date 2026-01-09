"""
Crawler Bot Handlers

Telegram bot interface for web crawler and limit-up stock tracking.
"""

from aiogram import Router, F, types
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
from datetime import date

from app.services.crawler import crawler_service
from app.services.limit_up import limit_up_service
from app.services.stock_scanner import stock_scanner
from app.services.sector import sector_service
from app.services.market_report import market_report_service
from app.services.watchlist import watchlist_service
from app.core.config import settings
from app.core.database import db
from app.core.logger import Logger
from app.core.stock_links import get_chart_url

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
    builder.button(text="📊 板块分析", callback_data="sector:main")
    builder.button(text="📋 市场报告", callback_data="report:main")
    builder.button(text="⭐ 自选列表", callback_data="watch:list")
    builder.adjust(2, 2, 1)
    
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
    except:
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
    builder.button(text="📊 板块分析", callback_data="sector:main")
    builder.button(text="📋 市场报告", callback_data="report:main")
    builder.button(text="⭐ 自选列表", callback_data="watch:list")
    builder.adjust(2, 2, 1)
    
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    except:
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
    except:
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
        except:
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
    except:
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
        "<i>每日16:00自动收集</i>"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📈 今日涨停", callback_data="lu:today")
    builder.button(text="🆕 首板", callback_data="lu:first")
    builder.button(text="� 曾涨停", callback_data="lu:burst")
    builder.button(text="�🔥 连板榜", callback_data="lu:streak")
    builder.button(text="💪 强势股", callback_data="lu:strong")
    builder.button(text="👀 启动追踪", callback_data="lu:watch")
    builder.button(text="🔍 信号扫描", callback_data="lu:scan")
    builder.button(text="🔄 同步涨停", callback_data="lu:sync")
    builder.button(text="◀️ 返回", callback_data="main")
    builder.adjust(2, 2, 2, 2, 1)
    
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    except:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Today's Limit-Ups
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("today"))
async def cmd_today(message: types.Message):
    if not await is_allowed(message.from_user.id):
        return
    text, markup = await get_today_ui()
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "lu:today")
async def cb_today(callback: types.CallbackQuery):
    await safe_answer(callback)
    text, markup = await get_today_ui()
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except:
        pass


async def get_today_ui():
    if not db.pool:
        return "❌ 数据库未连接", None
    
    today = date.today()
    rows = await db.pool.fetch("""
        SELECT code, name, close_price, change_pct, limit_times
        FROM limit_up_stocks WHERE date = $1
        ORDER BY limit_times DESC, close_price DESC LIMIT 15
    """, today)
    
    if not rows:
        text = "📈 <b>今日涨停</b>\n━━━━━━━━━━━━━━━━━━━━━\n📭 暂无数据\n\n点击同步获取"
    else:
        text = f"📈 <b>今日涨停</b> ({len(rows)})\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        for i, r in enumerate(rows, 1):
            streak = f" [{r['limit_times']}板]" if r['limit_times'] > 1 else ""
            chart_url = await get_chart_url(r['code'], r.get('name'))
            text += f"{i}. <a href=\"{chart_url}\">{r['name']}</a> ({r['code']}){streak}\n"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 刷新", callback_data="lu:today")
    builder.button(text="◀️ 返回", callback_data="lu:main")
    builder.adjust(2)
    
    return text, builder.as_markup()


# ─────────────────────────────────────────────────────────────────────────────
# First-Board (首板 - First-time Limit-up)
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("first"))
async def cmd_first(message: types.Message):
    if not await is_allowed(message.from_user.id):
        return
    text, markup = await get_first_ui()
    await message.answer(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)


@router.callback_query(F.data == "lu:first")
async def cb_first(callback: types.CallbackQuery):
    await safe_answer(callback)
    text, markup = await get_first_ui()
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
    except:
        pass


async def get_first_ui():
    """Get today's first-time limit-up stocks (首板 - 收盘涨停 limit_times=1)."""
    if not db.pool:
        return "❌ 数据库未连接", None
    
    today = date.today()
    # First-board: stocks with limit_times = 1 AND is_sealed = true (收盘涨停)
    rows = await db.pool.fetch("""
        SELECT code, name, close_price, change_pct, turnover_rate
        FROM limit_up_stocks WHERE date = $1 AND limit_times = 1 AND is_sealed = TRUE
        ORDER BY turnover_rate DESC LIMIT 15
    """, today)
    
    if not rows:
        text = "🆕 <b>首板</b> (收盘封板)\n━━━━━━━━━━━━━━━━━━━━━\n📭 暂无首板数据\n\n点击同步获取"
    else:
        text = f"🆕 <b>首板</b> (收盘封板, {len(rows)})\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        for i, r in enumerate(rows, 1):
            chart_url = await get_chart_url(r['code'], r.get('name'))
            turnover = f"换手{r['turnover_rate']:.1f}%" if r['turnover_rate'] else ""
            text += f"{i}. <a href=\"{chart_url}\">{r['name']}</a> ({r['code']}) {turnover}\n"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 刷新", callback_data="lu:first")
    builder.button(text="◀️ 返回", callback_data="lu:main")
    builder.adjust(2)
    
    return text, builder.as_markup()


# ─────────────────────────────────────────────────────────────────────────────
# Burst Limit-Ups (曾涨停/炸板)
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("burst"))
async def cmd_burst(message: types.Message):
    if not await is_allowed(message.from_user.id):
        return
    text, markup = await get_burst_ui()
    await message.answer(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)


@router.callback_query(F.data == "lu:burst")
async def cb_burst(callback: types.CallbackQuery):
    await safe_answer(callback)
    text, markup = await get_burst_ui()
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
    except:
        pass


async def get_burst_ui():
    """Get today's burst limit-up stocks (曾涨停/炸板 - 触及涨停但收盘未封住)."""
    if not db.pool:
        return "❌ 数据库未连接", None
    
    today = date.today()
    # Burst: stocks with is_sealed = false (曾涨停/炸板)
    rows = await db.pool.fetch("""
        SELECT code, name, close_price, change_pct, turnover_rate
        FROM limit_up_stocks WHERE date = $1 AND is_sealed = FALSE
        ORDER BY change_pct DESC LIMIT 20
    """, today)
    
    if not rows:
        text = "💥 <b>曾涨停</b> (炸板)\n━━━━━━━━━━━━━━━━━━━━━\n📭 暂无炸板数据\n\n点击同步获取"
    else:
        text = f"💥 <b>曾涨停</b> (炸板, {len(rows)})\n━━━━━━━━━━━━━━━━━━━━━\n<i>日内涨停但收盘未封住</i>\n\n"
        for i, r in enumerate(rows, 1):
            chart_url = await get_chart_url(r['code'], r.get('name'))
            change = f"{r['change_pct']:.1f}%" if r['change_pct'] else ""
            text += f"{i}. <a href=\"{chart_url}\">{r['name']}</a> ({r['code']}) {change}\n"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 刷新", callback_data="lu:burst")
    builder.button(text="◀️ 返回", callback_data="lu:main")
    builder.adjust(2)
    
    return text, builder.as_markup()


# ─────────────────────────────────────────────────────────────────────────────
# Streak Leaders
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("streak"))
async def cmd_streak(message: types.Message):
    if not await is_allowed(message.from_user.id):
        return
    text, markup = await get_streak_ui()
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "lu:streak")
async def cb_streak(callback: types.CallbackQuery):
    await safe_answer(callback)
    text, markup = await get_streak_ui()
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except:
        pass


async def get_streak_ui():
    streaks = await limit_up_service.get_streak_leaders()
    
    if not streaks:
        text = "🔥 <b>连板榜</b>\n━━━━━━━━━━━━━━━━━━━━━\n📭 暂无连板股"
    else:
        text = f"🔥 <b>连板榜</b> ({len(streaks)})\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        for i, s in enumerate(streaks, 1):
            chart_url = await get_chart_url(s['code'], s.get('name'))
            text += f"{i}. <a href=\"{chart_url}\">{s['name']}</a> ({s['code']}) - <b>{s['streak_count']}连板</b>\n"
    
    builder = InlineKeyboardBuilder()
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
    text, markup = await get_strong_ui()
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "lu:strong")
async def cb_strong(callback: types.CallbackQuery):
    await safe_answer(callback)
    text, markup = await get_strong_ui()
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except:
        pass


async def get_strong_ui():
    strong = await limit_up_service.get_strong_stocks()
    
    if not strong:
        text = "💪 <b>强势股</b> (7日)\n━━━━━━━━━━━━━━━━━━━━━\n📭 暂无强势股"
    else:
        text = f"💪 <b>强势股</b> (7日, {len(strong)})\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        for i, s in enumerate(strong, 1):
            chart_url = await get_chart_url(s['code'], s.get('name'))
            text += f"{i}. <a href=\"{chart_url}\">{s['name']}</a> ({s['code']}) - {s['limit_count']}次涨停\n"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 刷新", callback_data="lu:strong")
    builder.button(text="◀️ 返回", callback_data="lu:main")
    builder.adjust(2)
    
    return text, builder.as_markup()


# ─────────────────────────────────────────────────────────────────────────────
# Startup Watchlist (启动追踪)
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("watch"))
async def cmd_watch(message: types.Message):
    if not await is_allowed(message.from_user.id):
        return
    text, markup = await get_watch_ui()
    await message.answer(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)


@router.callback_query(F.data == "lu:watch")
async def cb_watch(callback: types.CallbackQuery):
    await safe_answer(callback)
    text, markup = await get_watch_ui()
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
    except:
        pass


async def get_watch_ui():
    """Get startup watchlist (一个月内涨停一次的股票)."""
    watchlist = await limit_up_service.get_startup_watchlist()
    
    if not watchlist:
        text = "👀 <b>启动追踪</b>\n━━━━━━━━━━━━━━━━━━━━━\n📭 暂无观察股\n\n<i>一个月内涨停一次的股票会加入观察</i>"
    else:
        text = f"👀 <b>启动追踪</b> ({len(watchlist)})\n━━━━━━━━━━━━━━━━━━━━━\n<i>一个月涨停一次，再次涨停将剔除</i>\n\n"
        for i, w in enumerate(watchlist, 1):
            chart_url = await get_chart_url(w['code'], w.get('name'))
            limit_date = w['first_limit_date'].strftime('%m/%d') if w['first_limit_date'] else ''
            text += f"{i}. <a href=\"{chart_url}\">{w['name']}</a> ({w['code']}) {limit_date}\n"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 刷新", callback_data="lu:watch")
    builder.button(text="◀️ 返回", callback_data="lu:main")
    builder.adjust(2)
    
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
    "volume": "放量信号", 
    "ma_bullish": "多头排列",
    "small_bullish_5": "底部5小阳"
}

SIGNAL_ICONS = {
    "breakout": "🔺",
    "volume": "📊",
    "ma_bullish": "📈",
    "small_bullish_5": "🌅"
}


@router.message(Command("scan"))
async def cmd_scan(message: types.Message):
    if not await is_allowed(message.from_user.id):
        return
    
    status = await message.answer("🔍 正在扫描全A股启动信号...\n\n⏳ 需要几分钟，请稍候")
    
    try:
        signals = await stock_scanner.scan_all_stocks(limit=300)
        
        if not signals or all(len(v) == 0 for v in signals.values()):
            await status.edit_text("🔍 扫描完成\n\n📭 暂无信号")
            return
        
        # Cache results for pagination
        user_id = message.from_user.id if hasattr(message, 'from_user') else 0
        _scan_results_cache[user_id] = signals
        
        text = "🔍 <b>启动信号扫描</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for signal_type, stocks in signals.items():
            if not stocks:
                continue
            
            icon = SIGNAL_ICONS.get(signal_type, "•")
            name = SIGNAL_NAMES.get(signal_type, signal_type)
            
            text += f"{icon} <b>{name}</b> ({len(stocks)})\n"
            for s in stocks[:5]:
                chart_url = await get_chart_url(s['code'], s.get('name'))
                text += f"  • <a href=\"{chart_url}\">{s['name']}</a> ({s['code']})\n"
            if len(stocks) > 5:
                text += f"  <i>...及其他 {len(stocks) - 5} 只</i>\n"
            text += "\n"
        
        builder = InlineKeyboardBuilder()
        # Add buttons to view full list for each signal type
        for signal_type, stocks in signals.items():
            if stocks:
                name = SIGNAL_NAMES.get(signal_type, signal_type)
                builder.button(text=f"📋 {name}全部", callback_data=f"scan:list:{signal_type}:0")
        builder.button(text="🔄 重新扫描", callback_data="lu:scan")
        builder.button(text="◀️ 返回", callback_data="lu:main")
        builder.adjust(2, 2, 2)
        
        await status.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup(), disable_web_page_preview=True)
    except Exception as e:
        await status.edit_text(f"❌ 扫描失败: {e}")


@router.callback_query(F.data == "lu:scan")
async def cb_scan(callback: types.CallbackQuery):
    await safe_answer(callback, "扫描中...")
    
    # Create a mock message object for cmd_scan
    class MockMessage:
        def __init__(self, msg):
            self.from_user = callback.from_user
            self._msg = msg
        
        async def answer(self, text, **kwargs):
            try:
                await self._msg.edit_text(text, **kwargs)
            except:
                pass
            return self._msg
    
    mock_msg = MockMessage(callback.message)
    await cmd_scan(mock_msg)


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
    text += f"━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"<i>第 {page + 1}/{total_pages} 页</i>\n\n"
    
    for i, s in enumerate(page_stocks, start + 1):
        chart_url = await get_chart_url(s['code'], s.get('name'))
        text += f"{i}. <a href=\"{chart_url}\">{s['name']}</a> ({s['code']})\n"
    
    builder = InlineKeyboardBuilder()
    
    # Pagination buttons
    if page > 0:
        builder.button(text="⬅️ 上一页", callback_data=f"scan:list:{signal_type}:{page-1}")
    if page < total_pages - 1:
        builder.button(text="➡️ 下一页", callback_data=f"scan:list:{signal_type}:{page+1}")
    
    builder.button(text="◀️ 返回扫描", callback_data="scan:back")
    builder.adjust(2, 1)
    
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup(), disable_web_page_preview=True)
    except:
        pass


@router.callback_query(F.data == "scan:back")
async def cb_scan_back(callback: types.CallbackQuery):
    """Return to scan results summary."""
    await safe_answer(callback)
    
    user_id = callback.from_user.id
    signals = _scan_results_cache.get(user_id, {})
    
    if not signals or all(len(v) == 0 for v in signals.values()):
        # No cached results, trigger new scan
        await callback.message.edit_text("📭 缓存已失效，请重新扫描")
        return
    
    text = "🔍 <b>启动信号扫描</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    for signal_type, stocks in signals.items():
        if not stocks:
            continue
        
        icon = SIGNAL_ICONS.get(signal_type, "•")
        name = SIGNAL_NAMES.get(signal_type, signal_type)
        
        text += f"{icon} <b>{name}</b> ({len(stocks)})\n"
        for s in stocks[:5]:
            chart_url = await get_chart_url(s['code'], s.get('name'))
            text += f"  • <a href=\"{chart_url}\">{s['name']}</a> ({s['code']})\n"
        if len(stocks) > 5:
            text += f"  <i>...及其他 {len(stocks) - 5} 只</i>\n"
        text += "\n"
    
    builder = InlineKeyboardBuilder()
    for signal_type, stocks in signals.items():
        if stocks:
            name = SIGNAL_NAMES.get(signal_type, signal_type)
            builder.button(text=f"📋 {name}全部", callback_data=f"scan:list:{signal_type}:0")
    builder.button(text="🔄 重新扫描", callback_data="lu:scan")
    builder.button(text="◀️ 返回", callback_data="lu:main")
    builder.adjust(2, 2, 2)
    
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup(), disable_web_page_preview=True)
    except:
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
    except:
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
    except:
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
    except:
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
    except:
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
    except:
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
    except:
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
        except:
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
        except:
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
    except:
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
        except:
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
        except:
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
        except:
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
        # Show usage
        text = (
            "⭐ <b>自选列表</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "用法:\n"
            "• <code>/watch 600519</code> - 添加股票\n"
            "• <code>/unwatch 600519</code> - 删除股票\n"
            "• <code>/mywatch</code> - 查看自选列表\n\n"
            "<i>每天下午17:00自动发送自选报告</i>"
        )
        await message.answer(text, parse_mode="HTML")
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
        text, markup = await get_watchlist_ui(message.from_user.id)
        await status.edit_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
    except Exception as e:
        await status.edit_text(f"❌ 加载失败: {e}")


@router.callback_query(F.data == "watch:list")
async def cb_watch_list(callback: types.CallbackQuery):
    """View watchlist."""
    await safe_answer(callback)
    
    try:
        await callback.message.edit_text("⏳ 正在加载...", parse_mode="HTML")
        text, markup = await get_watchlist_ui(callback.from_user.id)
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
    except Exception as e:
        await callback.message.edit_text(f"❌ 加载失败: {e}")


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
        text, markup = await get_watchlist_ui(callback.from_user.id)
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
    except:
        pass


async def get_watchlist_ui(user_id: int):
    """Get watchlist UI with real-time prices."""
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
    
    text = f"⭐ <b>自选列表</b> ({len(stocks)})\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    for s in stocks:
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
        
        chart_url = await get_chart_url(code, name)
        date_str = add_date.strftime('%m/%d') if add_date else ""
        
        text += (
            f"{icon} <a href=\"{chart_url}\"><b>{name}</b></a> ({code})\n"
            f"   💰 {current:.2f} | 今日 {today:+.2f}% | 累计 <b>{total:+.2f}%</b>\n"
            f"   <i>加入: {date_str}</i>\n\n"
        )
    
    builder = InlineKeyboardBuilder()
    
    # Add delete buttons for each stock (limit to 8)
    for s in stocks[:8]:
        name_short = s.get('name', s['code'])[:6]
        builder.button(text=f"❌ {name_short}", callback_data=f"watch:del:{s['code']}")
    
    builder.button(text="🔄 刷新", callback_data="watch:list")
    builder.button(text="◀️ 返回", callback_data="main")
    builder.adjust(2, 2, 2, 2, 2)
    
    return text, builder.as_markup()
