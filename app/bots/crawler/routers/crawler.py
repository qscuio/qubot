"""
Crawler Router

Handles web crawler functionality: adding/removing sources, crawling, viewing recent items.
"""

from aiogram import Router, F, types
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.services.crawler import crawler_service

from .common import is_allowed, safe_answer, safe_edit_text

router = Router()


# ─────────────────────────────────────────────────────────────────────────────
# Crawler Main Menu
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "crawler:main")
async def cb_crawler_main(callback: types.CallbackQuery):
    """Show crawler main menu."""
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

    await safe_edit_text(callback.message, text, reply_markup=builder.as_markup())


# ─────────────────────────────────────────────────────────────────────────────
# Add Source
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("add"))
async def cmd_add(message: types.Message, command: CommandObject):
    """Add a new crawler source."""
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

async def _get_sources_ui() -> tuple[str, types.InlineKeyboardMarkup]:
    """Build sources list UI."""
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


@router.message(Command("list"))
async def cmd_list(message: types.Message):
    """List all crawler sources."""
    if not await is_allowed(message.from_user.id):
        return
    text, markup = await _get_sources_ui()
    await message.answer(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)


@router.callback_query(F.data == "crawler:list")
async def cb_list(callback: types.CallbackQuery):
    """Show sources list via callback."""
    await safe_answer(callback)
    text, markup = await _get_sources_ui()
    await safe_edit_text(
        callback.message, text, reply_markup=markup, disable_web_page_preview=True
    )


@router.message(Command("remove"))
async def cmd_remove(message: types.Message):
    """Show remove source UI."""
    if not await is_allowed(message.from_user.id):
        return
    text, markup = await _get_sources_ui()
    await message.answer(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)


@router.callback_query(F.data.startswith("crawler:del:"))
async def cb_delete(callback: types.CallbackQuery):
    """Delete a crawler source."""
    source_id = int(callback.data.split(":")[2])
    result = await crawler_service.remove_source(source_id)

    if result:
        await safe_answer(callback, "✅ 已删除")
        text, markup = await _get_sources_ui()
        await safe_edit_text(
            callback.message, text, reply_markup=markup, disable_web_page_preview=True
        )
    else:
        await safe_answer(callback, "❌ 删除失败")


# ─────────────────────────────────────────────────────────────────────────────
# Crawl (Manual Trigger)
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("crawl"))
async def cmd_crawl(message: types.Message):
    """Manually trigger crawling all sources."""
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
    """Trigger crawl via callback."""
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

async def _get_recent_ui() -> tuple[str, types.InlineKeyboardMarkup]:
    """Build recent items UI."""
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


@router.message(Command("recent"))
async def cmd_recent(message: types.Message):
    """Show recent crawled items."""
    if not await is_allowed(message.from_user.id):
        return
    text, markup = await _get_recent_ui()
    await message.answer(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)


@router.callback_query(F.data == "crawler:recent")
async def cb_recent(callback: types.CallbackQuery):
    """Show recent items via callback."""
    await safe_answer(callback)
    text, markup = await _get_recent_ui()
    await safe_edit_text(
        callback.message, text, reply_markup=markup, disable_web_page_preview=True
    )
