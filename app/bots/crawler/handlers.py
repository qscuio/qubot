"""
Crawler Bot Handlers

Telegram bot interface for web crawler and limit-up stock tracking.
"""

from aiogram import Router, F, types
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import date

from app.services.crawler import crawler_service
from app.services.limit_up import limit_up_service
from app.services.stock_scanner import stock_scanner
from app.core.config import settings
from app.core.database import db
from app.core.logger import Logger

logger = Logger("CrawlerBot")
router = Router()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def is_allowed(user_id: int) -> bool:
    if not settings.allowed_users_list:
        return True
    return user_id in settings.allowed_users_list


def get_chart_url(code: str) -> str:
    """Generate EastMoney K-line chart URL for a stock code.
    
    Shanghai stocks (6xxxxx) use 'sh' prefix
    Shenzhen stocks (0xxxxx, 3xxxxx) use 'sz' prefix
    """
    code = str(code).zfill(6)
    if code.startswith('6'):
        market = 'sh'
    else:
        market = 'sz'
    return f"http://quote.eastmoney.com/{market}{code}.html"


# ─────────────────────────────────────────────────────────────────────────────
# Main Menu
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    if not is_allowed(message.from_user.id):
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
    builder.adjust(2)
    
    await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())


# ─────────────────────────────────────────────────────────────────────────────
# Crawler Section
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "crawler:main")
async def cb_crawler_main(callback: types.CallbackQuery):
    await callback.answer()
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
    await callback.answer()
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
    builder.adjust(2)
    
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    except:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Add Source
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("add"))
async def cmd_add(message: types.Message, command: CommandObject):
    if not is_allowed(message.from_user.id):
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
    if not is_allowed(message.from_user.id):
        return
    text, markup = await get_sources_ui()
    await message.answer(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)


@router.callback_query(F.data == "crawler:list")
async def cb_list(callback: types.CallbackQuery):
    await callback.answer()
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
    if not is_allowed(message.from_user.id):
        return
    text, markup = await get_sources_ui()
    await message.answer(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)


@router.callback_query(F.data.startswith("crawler:del:"))
async def cb_delete(callback: types.CallbackQuery):
    source_id = int(callback.data.split(":")[2])
    result = await crawler_service.remove_source(source_id)
    if result:
        await callback.answer("✅ 已删除")
        text, markup = await get_sources_ui()
        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
        except:
            pass
    else:
        await callback.answer("❌ 删除失败", show_alert=True)


# ─────────────────────────────────────────────────────────────────────────────
# Crawl (Manual)
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("crawl"))
async def cmd_crawl(message: types.Message):
    if not is_allowed(message.from_user.id):
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
    await callback.answer("⏳ 爬取中...")
    
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
    if not is_allowed(message.from_user.id):
        return
    text, markup = await get_recent_ui()
    await message.answer(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)


@router.callback_query(F.data == "crawler:recent")
async def cb_recent(callback: types.CallbackQuery):
    await callback.answer()
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
    await callback.answer()
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
    builder.button(text="🔥 连板榜", callback_data="lu:streak")
    builder.button(text="💪 强势股", callback_data="lu:strong")
    builder.button(text="👀 启动追踪", callback_data="lu:watch")
    builder.button(text="� 信号扫描", callback_data="lu:scan")
    builder.button(text="�🔄 同步涨停", callback_data="lu:sync")
    builder.button(text="◀️ 返回", callback_data="main")
    builder.adjust(2, 2, 2, 2)
    
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    except:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Today's Limit-Ups
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("today"))
async def cmd_today(message: types.Message):
    if not is_allowed(message.from_user.id):
        return
    text, markup = await get_today_ui()
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "lu:today")
async def cb_today(callback: types.CallbackQuery):
    await callback.answer()
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
            chart_url = get_chart_url(r['code'])
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
    if not is_allowed(message.from_user.id):
        return
    text, markup = await get_first_ui()
    await message.answer(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)


@router.callback_query(F.data == "lu:first")
async def cb_first(callback: types.CallbackQuery):
    await callback.answer()
    text, markup = await get_first_ui()
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
    except:
        pass


async def get_first_ui():
    """Get today's first-time limit-up stocks (首板)."""
    if not db.pool:
        return "❌ 数据库未连接", None
    
    today = date.today()
    # First-board: stocks with limit_times = 1 (first limit-up)
    rows = await db.pool.fetch("""
        SELECT code, name, close_price, change_pct, turnover_rate
        FROM limit_up_stocks WHERE date = $1 AND limit_times = 1
        ORDER BY turnover_rate DESC LIMIT 15
    """, today)
    
    if not rows:
        text = "🆕 <b>首板</b>\n━━━━━━━━━━━━━━━━━━━━━\n📭 暂无首板数据\n\n点击同步获取"
    else:
        text = f"🆕 <b>首板</b> ({len(rows)})\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        for i, r in enumerate(rows, 1):
            chart_url = get_chart_url(r['code'])
            turnover = f"换手{r['turnover_rate']:.1f}%" if r['turnover_rate'] else ""
            text += f"{i}. <a href=\"{chart_url}\">{r['name']}</a> ({r['code']}) {turnover}\n"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 刷新", callback_data="lu:first")
    builder.button(text="◀️ 返回", callback_data="lu:main")
    builder.adjust(2)
    
    return text, builder.as_markup()


# ─────────────────────────────────────────────────────────────────────────────
# Streak Leaders
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("streak"))
async def cmd_streak(message: types.Message):
    if not is_allowed(message.from_user.id):
        return
    text, markup = await get_streak_ui()
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "lu:streak")
async def cb_streak(callback: types.CallbackQuery):
    await callback.answer()
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
            chart_url = get_chart_url(s['code'])
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
    if not is_allowed(message.from_user.id):
        return
    text, markup = await get_strong_ui()
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "lu:strong")
async def cb_strong(callback: types.CallbackQuery):
    await callback.answer()
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
            chart_url = get_chart_url(s['code'])
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
    if not is_allowed(message.from_user.id):
        return
    text, markup = await get_watch_ui()
    await message.answer(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)


@router.callback_query(F.data == "lu:watch")
async def cb_watch(callback: types.CallbackQuery):
    await callback.answer()
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
            chart_url = get_chart_url(w['code'])
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
    if not is_allowed(message.from_user.id):
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
    await callback.answer("⏳ 同步中...")
    
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

@router.message(Command("scan"))
async def cmd_scan(message: types.Message):
    if not is_allowed(message.from_user.id):
        return
    
    status = await message.answer("🔍 正在扫描全A股启动信号...\n\n⏳ 需要几分钟，请稍候")
    
    try:
        signals = await stock_scanner.scan_all_stocks(limit=300)
        
        if not signals or all(len(v) == 0 for v in signals.values()):
            await status.edit_text("🔍 扫描完成\n\n📭 暂无信号")
            return
        
        text = "🔍 <b>启动信号扫描</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for signal_type, stocks in signals.items():
            if not stocks:
                continue
            
            icon = {"breakout": "🔺", "volume": "📊", "ma_bullish": "📈"}.get(signal_type, "•")
            name = {"breakout": "突破信号", "volume": "放量信号", "ma_bullish": "多头排列"}.get(signal_type, signal_type)
            
            text += f"{icon} <b>{name}</b> ({len(stocks)})\n"
            for s in stocks[:6]:
                chart_url = get_chart_url(s['code'])
                text += f"  • <a href=\"{chart_url}\">{s['name']}</a> ({s['code']})\n"
            if len(stocks) > 6:
                text += f"  ...及其他 {len(stocks) - 6} 只\n"
            text += "\n"
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 重新扫描", callback_data="lu:scan")
        builder.button(text="◀️ 返回", callback_data="lu:main")
        builder.adjust(2)
        
        await status.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup(), disable_web_page_preview=True)
    except Exception as e:
        await status.edit_text(f"❌ 扫描失败: {e}")


@router.callback_query(F.data == "lu:scan")
async def cb_scan(callback: types.CallbackQuery):
    await callback.answer("扫描中...")
    await cmd_scan(callback.message)


# ─────────────────────────────────────────────────────────────────────────────
# Help
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("help"))
async def cmd_help(message: types.Message):
    if not is_allowed(message.from_user.id):
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
        "/streak - 连板榜\n"
        "/strong - 强势股\n"
        "/sync - 同步涨停"
    )
    await message.answer(text, parse_mode="HTML")

