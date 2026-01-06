from aiogram import Router, F, types
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.services.rss import rss_service
from app.core.config import settings

router = Router()

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def is_allowed(user_id: int) -> bool:
    if not settings.allowed_users_list:
        return True
    return user_id in settings.allowed_users_list

# ─────────────────────────────────────────────────────────────────────────────
# Main Menu
# ─────────────────────────────────────────────────────────────────────────────

from app.core.logger import Logger
logger = Logger("RSSBot")

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    logger.info(f"RSS /start from user {message.from_user.id}")
    if not is_allowed(message.from_user.id):
        logger.warn(f"User {message.from_user.id} not allowed")
        return
    try:
        await send_main_menu(message)
    except Exception as e:
        logger.error(f"Error in RSS /start: {e}")
        await message.answer(f"❌ Error: {e}")

async def send_main_menu(message: types.Message):
    user_id = str(message.from_user.id)
    text, markup = await get_main_menu_ui(user_id)
    await message.answer(text, parse_mode="HTML", reply_markup=markup)

async def edit_main_menu(message: types.Message, user_id: str):
    text, markup = await get_main_menu_ui(user_id)
    try:
        await message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except:
        pass

async def get_main_menu_ui(user_id: str):
    subs = await rss_service.get_subscriptions(user_id)
    status_icon = "🟢" if rss_service.is_running else "🔴"
    
    text = (
        "📰 <b>RSS Bot</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Status: {status_icon} <b>{'Running' if rss_service.is_running else 'Stopped'}</b>\n"
        f"📚 Subscriptions: <b>{len(subs)}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Use /sub &lt;url&gt; to subscribe to feeds</i>"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📚 My Feeds", callback_data="rss:list")
    builder.button(text="🔄 Refresh", callback_data="rss:refresh")
    builder.adjust(2)
    
    return text, builder.as_markup()

@router.callback_query(F.data == "rss:refresh")
async def cb_refresh(callback: types.CallbackQuery):
    await callback.answer("🔄 Refreshed")
    await edit_main_menu(callback.message, str(callback.from_user.id))

@router.callback_query(F.data == "rss:main")
async def cb_main(callback: types.CallbackQuery):
    await callback.answer()
    await edit_main_menu(callback.message, str(callback.from_user.id))

# ─────────────────────────────────────────────────────────────────────────────
# Subscriptions List
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("list"))
async def cmd_list(message: types.Message):
    if not is_allowed(message.from_user.id):
        return
    text, markup = await get_subs_ui(str(message.from_user.id))
    await message.answer(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)

@router.callback_query(F.data == "rss:list")
async def cb_list(callback: types.CallbackQuery):
    await callback.answer()
    text, markup = await get_subs_ui(str(callback.from_user.id))
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
    except:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)

async def get_subs_ui(user_id: str):
    subs = await rss_service.get_subscriptions(user_id)
    
    if not subs:
        text = (
            "📚 <b>My Feeds</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "📭 No subscriptions yet.\n\n"
            "Use <code>/sub &lt;url&gt;</code> to add a feed."
        )
        builder = InlineKeyboardBuilder()
        builder.button(text="◀️ Back", callback_data="rss:main")
        return text, builder.as_markup()
    
    text = f"📚 <b>My Feeds</b> ({len(subs)})\n━━━━━━━━━━━━━━━━━━━━━\n"
    
    for i, sub in enumerate(subs[:10], 1):
        title = sub.get('title', 'Unknown')[:30]
        text += f"{i}. <a href=\"{sub['url']}\">{title}</a>\n"
    
    builder = InlineKeyboardBuilder()
    for sub in subs[:10]:
        title = sub.get('title', 'Unknown')[:18]
        builder.button(text=f"🗑️ {title}", callback_data=f"rss:unsub:{sub['id']}")
    
    builder.adjust(1)
    
    kb = builder.as_markup()
    kb.inline_keyboard.append([
        types.InlineKeyboardButton(text="🗑️ Remove All", callback_data="rss:clear_confirm"),
        types.InlineKeyboardButton(text="◀️ Back", callback_data="rss:main"),
    ])
    
    return text, kb

# ─────────────────────────────────────────────────────────────────────────────
# Subscribe / Unsubscribe
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("sub"))
async def cmd_sub(message: types.Message, command: CommandObject):
    if not is_allowed(message.from_user.id):
        return
    
    url = command.args
    if not url:
        text = (
            "📰 <b>Subscribe to Feed</b>\n\n"
            "Usage: <code>/sub &lt;url&gt;</code>\n\n"
            "Examples:\n"
            "• <code>/sub https://news.ycombinator.com/rss</code>\n"
            "• <code>/sub https://blog.example.com/feed</code>"
        )
        await message.answer(text, parse_mode="HTML")
        return

    status = await message.answer(f"⏳ Checking {url}...")
    
    try:
        res = await rss_service.subscribe(str(message.from_user.id), url, str(message.chat.id))
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📚 My Feeds", callback_data="rss:list")
        builder.button(text="🏠 Menu", callback_data="rss:main")
        builder.adjust(2)
        
        await status.edit_text(
            f"✅ Subscribed to <b>{res['title']}</b>",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        await status.edit_text(f"❌ Error: {e}")

@router.message(Command("unsub"))
async def cmd_unsub(message: types.Message, command: CommandObject):
    if not is_allowed(message.from_user.id):
        return
    
    url_or_id = command.args
    if not url_or_id:
        # Show list with unsub buttons
        text, markup = await get_subs_ui(str(message.from_user.id))
        await message.answer(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
        return

    res = await rss_service.unsubscribe(str(message.from_user.id), url_or_id)
    if res.get("removed"):
        await message.answer(f"✅ Unsubscribed from <b>{res.get('title', 'feed')}</b>", parse_mode="HTML")
    else:
        await message.answer(f"❌ {res.get('error', 'Not found')}")

@router.callback_query(F.data.startswith("rss:unsub:"))
async def cb_unsub(callback: types.CallbackQuery):
    source_id = callback.data.split(":", 2)[2]
    res = await rss_service.unsubscribe(str(callback.from_user.id), source_id)
    
    if res.get("removed"):
        await callback.answer(f"✅ Unsubscribed")
        # Refresh list
        text, markup = await get_subs_ui(str(callback.from_user.id))
        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
        except:
            pass
    else:
        await callback.answer(res.get("error", "Error"), show_alert=True)

# ─────────────────────────────────────────────────────────────────────────────
# Clear All
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "rss:clear_confirm")
async def cb_clear_confirm(callback: types.CallbackQuery):
    subs = await rss_service.get_subscriptions(str(callback.from_user.id))
    
    builder = InlineKeyboardBuilder()
    builder.button(text="⚠️ Yes, remove all", callback_data="rss:clear_yes")
    builder.button(text="❌ Cancel", callback_data="rss:list")
    builder.adjust(1)
    
    await callback.answer()
    try:
        await callback.message.edit_text(
            f"⚠️ <b>Remove All Subscriptions?</b>\n\n"
            f"This will remove <b>{len(subs)}</b> feeds.\n"
            f"This action cannot be undone.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
    except:
        pass

@router.callback_query(F.data == "rss:clear_yes")
async def cb_clear_yes(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    subs = await rss_service.get_subscriptions(user_id)
    
    for sub in subs:
        await rss_service.unsubscribe(user_id, str(sub['id']))
    
    await callback.answer("🗑️ All feeds removed")
    await edit_main_menu(callback.message, user_id)

# ─────────────────────────────────────────────────────────────────────────────
# Help & Status
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("status"))
async def cmd_status(message: types.Message):
    if not is_allowed(message.from_user.id):
        return
    
    subs = await rss_service.get_subscriptions(str(message.from_user.id))
    status_icon = "🟢" if rss_service.is_running else "🔴"
    
    text = (
        "📊 <b>RSS Bot Status</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"Service: {status_icon} <b>{'Running' if rss_service.is_running else 'Stopped'}</b>\n"
        f"Subscriptions: <b>{len(subs)}</b>"
    )
    await message.answer(text, parse_mode="HTML")

@router.message(Command("help"))
async def cmd_help(message: types.Message):
    if not is_allowed(message.from_user.id):
        return
    
    text = (
        "📰 <b>RSS Bot Commands</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "/start - Main menu\n"
        "/sub &lt;url&gt; - Subscribe to feed\n"
        "/unsub - Unsubscribe from feed\n"
        "/list - List subscriptions\n"
        "/status - Service status\n"
        "/help - This message"
    )
    await message.answer(text, parse_mode="HTML")
