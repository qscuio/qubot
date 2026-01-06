from aiogram import Router, F, types
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.services.monitor import monitor_service
from app.services.twitter import twitter_service
from app.core.config import settings
from app.core.logger import Logger

logger = Logger("MonitorBot")
router = Router()

def is_allowed(user_id: int) -> bool:
    if not settings.allowed_users_list: return True
    return user_id in settings.allowed_users_list

# ─────────────────────────────────────────────────────────────────────────────
# Main Menu
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    if not is_allowed(message.from_user.id): return
    await send_main_menu(message)

@router.message(Command("status"))
async def cmd_status(message: types.Message):
    if not is_allowed(message.from_user.id): return
    await send_main_menu(message)

@router.message(Command("help"))
async def cmd_help(message: types.Message):
    if not is_allowed(message.from_user.id): return
    help_text = (
        "🔔 <b>Monitor Bot Commands</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>📋 Navigation</b>\n"
        "/start - Main menu with controls\n"
        "/sources - Manage source channels\n"
        "/vips - Manage VIP users\n"
        "/help - This message\n\n"
        "<b>📡 Channel Management</b>\n"
        "/add &lt;channel&gt; - Add source channel\n"
        "/remove &lt;channel&gt; - Remove source channel\n"
        "/clear - Remove all sources\n\n"
        "<b>⭐ VIP Users</b>\n"
        "/vip &lt;user&gt; - Add VIP user (direct forward)\n"
        "/unvip &lt;user&gt; - Remove VIP user\n"
        "/vips - List VIP users\n\n"
        "<b>📊 Status & History</b>\n"
        "/status - Show current status\n"
        "/history - View recent forwards\n\n"
        "💡 <i>Use the main menu for quick access to all features!</i>"
    )
    await message.answer(help_text, parse_mode="HTML")

async def send_main_menu(message: types.Message):
    text, markup = get_main_menu_ui()
    await message.answer(text, reply_markup=markup, parse_mode="HTML")

async def edit_main_menu(message: types.Message):
    text, markup = get_main_menu_ui()
    try:
        await message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except:
        pass

def get_main_menu_ui():
    running = monitor_service.is_running
    status_icon = "🟢" if running else "🔴"
    status_text = "Active" if running else "Stopped"
    source_count = len(monitor_service.source_channels)
    disabled_count = len(monitor_service.disabled_sources)
    active_count = source_count - disabled_count
    
    text = (
        f"🕵️ <b>Monitor Bot</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Status:</b> {status_icon} <code>{status_text}</code>\n"
        f"<b>Sources:</b> <code>{active_count}</code> active <i>({disabled_count} off)</i>\n"
    )
    
    if monitor_service.target_channel:
        text += f"<b>Target:</b> <code>{monitor_service.target_channel}</code>\n"
    else:
        text += f"<b>Target:</b> ⚠️ <i>Not Configured</i>\n"
    
    # Add quick stats if available (placeholder for now)
    text += f"\n<i>Forwarded today: 0</i>"

    builder = InlineKeyboardBuilder()
    
    # Control row: Big Start/Stop button
    if running:
        builder.button(text="🛑 Stop Monitoring", callback_data="mon:stop")
    else:
        builder.button(text="▶️ Start Monitoring", callback_data="mon:start")
    
    # Management row
    builder.button(text="📡 Sources", callback_data="nav:sources")
    builder.button(text="⭐ VIPs", callback_data="nav:vips")
    builder.button(text="🐦 Twitter", callback_data="nav:twitters")
    
    # Utility row
    builder.button(text="🔄 Sync", callback_data="nav:refresh")
    builder.button(text="❓ Help", callback_data="nav:help")
    
    builder.adjust(1, 3, 2)
    return text, builder.as_markup()

# ─────────────────────────────────────────────────────────────────────────────
# Main Menu Callbacks
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "mon:start")
async def cb_start_monitor(callback: types.CallbackQuery):
    await monitor_service.start()
    await callback.answer("✅ Monitoring started")
    await edit_main_menu(callback.message)

@router.callback_query(F.data == "mon:stop")
async def cb_stop_monitor(callback: types.CallbackQuery):
    await monitor_service.stop()
    await callback.answer("⏹️ Monitoring stopped")
    await edit_main_menu(callback.message)

@router.callback_query(F.data == "nav:refresh")
async def cb_refresh(callback: types.CallbackQuery):
    await callback.answer("🔄 Syncing...")
    
    # Force sync pending updates from Telegram servers
    from app.core.bot import telegram_service
    if telegram_service.connected:
        try:
            for client in telegram_service.clients:
                if client.is_connected():
                    await client.catch_up()
        except Exception as e:
            pass  # Ignore sync errors
    
    # Refresh channel names for channels that only have IDs
    try:
        await monitor_service.refresh_channel_names()
    except:
        pass
    
    await edit_main_menu(callback.message)

@router.callback_query(F.data == "nav:sources")
async def cb_sources(callback: types.CallbackQuery):
    await callback.answer()
    await edit_sources_menu(callback.message)

@router.callback_query(F.data == "nav:main")
async def cb_main(callback: types.CallbackQuery):
    await callback.answer()
    await edit_main_menu(callback.message)

@router.callback_query(F.data == "nav:help")
async def cb_help_callback(callback: types.CallbackQuery):
    await callback.answer()
    # Reuse existing help command logic but as edit if possible or new message
    help_text = (
        "🔔 <b>Monitor Bot Commands</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>📋 Navigation</b>\n"
        "/start - Main menu with controls\n"
        "/sources - Manage source channels\n"
        "/help - This message\n\n"
        "<b>📡 Channel Management</b>\n"
        "/add &lt;channel&gt; - Add source channel\n"
        "/remove &lt;channel&gt; - Remove source channel\n"
        "/clear - Remove all sources\n\n"
        "<b>📊 Status & History</b>\n"
        "/status - Show current status\n"
        "/history - View recent forwards"
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Back", callback_data="nav:main")
    await callback.message.edit_text(help_text, parse_mode="HTML", reply_markup=builder.as_markup())

# ─────────────────────────────────────────────────────────────────────────────
# Sources Menu
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("sources"))
async def cmd_sources(message: types.Message):
    if not is_allowed(message.from_user.id): return
    text, markup = get_sources_menu_ui()
    await message.answer(text, reply_markup=markup, parse_mode="HTML")

async def edit_sources_menu(message: types.Message):
    text, markup = get_sources_menu_ui()
    try:
        await message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except:
        pass

def get_sources_menu_ui(page: int = 0):
    # Get channel info as list of dicts
    channels_list = list(monitor_service.channels.values())
    page_size = 5
    total_pages = max(1, (len(channels_list) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    
    if not channels_list:
        text = (
            "📡 <b>Source Channels</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "📭 No sources configured.\n\n"
            "💡 <i>Use /add &lt;channel&gt; to add a source.</i>"
        )
        kb = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="◀️ Back", callback_data="nav:main")]
        ])
        return text, kb
    
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, len(channels_list))
    page_channels = channels_list[start_idx:end_idx]
    
    text = f"📡 <b>Source Channels</b> ({len(channels_list)} total)\n━━━━━━━━━━━━━━━━━━━━━\n"
    
    # Build text and keyboard together
    keyboard = []
    
    for i, ch_info in enumerate(page_channels, start=start_idx + 1):
        is_disabled = not ch_info.get('enabled', True)
        icon = "🔴" if is_disabled else "🟢"
        ch_id = ch_info['id']
        name = ch_info.get('name', ch_id)
        
        # Text: show name and ID
        display_name = name[:20] + "..." if len(name) > 20 else name
        if name != ch_id:
            text += f"{i}. {icon} <b>{display_name}</b>\n    <code>{ch_id}</code>\n"
        else:
            text += f"{i}. {icon} <code>{ch_id}</code>\n"
        
        # Buttons for this channel: [#. Name] [Toggle] [Delete]
        btn_label = f"{i}. {name[:10]}"
        ch_id_short = ch_id[:30]  # Truncate for callback limit
        
        row = [
            types.InlineKeyboardButton(text=btn_label, callback_data="src:noop"),
            types.InlineKeyboardButton(
                text="✅ On" if is_disabled else "⏸️ Off",
                callback_data=f"src:{'enable' if is_disabled else 'disable'}:{ch_id_short}"
            ),
            types.InlineKeyboardButton(text="🗑️", callback_data=f"src:delete:{ch_id_short}")
        ]
        keyboard.append(row)
    
    # Pagination row (only if more than 1 page)
    if total_pages > 1:
        pagination = []
        if page > 0:
            pagination.append(types.InlineKeyboardButton(text="◀️ Prev", callback_data=f"src:page:{page-1}"))
        pagination.append(types.InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="src:noop"))
        if page < total_pages - 1:
            pagination.append(types.InlineKeyboardButton(text="Next ▶️", callback_data=f"src:page:{page+1}"))
        keyboard.append(pagination)
    
    # Navigation row
    keyboard.append([
        types.InlineKeyboardButton(text="🗑️ Clear All", callback_data="src:clear_confirm"),
        types.InlineKeyboardButton(text="◀️ Back", callback_data="nav:main"),
    ])
    
    kb = types.InlineKeyboardMarkup(inline_keyboard=keyboard)
    return text, kb

# ─────────────────────────────────────────────────────────────────────────────
# Source Action Callbacks
# ─────────────────────────────────────────────────────────────────────────────

def find_channel_by_prefix(prefix: str) -> str:
    """Find full channel ID by prefix match."""
    for cid in monitor_service.channels.keys():
        if cid.startswith(prefix):
            return cid
    return prefix

@router.callback_query(F.data.startswith("src:enable:"))
async def cb_enable_source(callback: types.CallbackQuery):
    ch_key = callback.data.split(":", 2)[2]
    ch_id = find_channel_by_prefix(ch_key)
    await monitor_service.toggle_source(ch_id, True)
    await callback.answer(f"✅ Enabled")
    await edit_sources_menu(callback.message)

@router.callback_query(F.data.startswith("src:disable:"))
async def cb_disable_source(callback: types.CallbackQuery):
    ch_key = callback.data.split(":", 2)[2]
    ch_id = find_channel_by_prefix(ch_key)
    await monitor_service.toggle_source(ch_id, False)
    await callback.answer(f"⏸️ Disabled")
    await edit_sources_menu(callback.message)

@router.callback_query(F.data.startswith("src:delete:"))
async def cb_delete_source(callback: types.CallbackQuery):
    ch_key = callback.data.split(":", 2)[2]
    ch_id = find_channel_by_prefix(ch_key)
    logger.info(f"Delete source: key={ch_key}, resolved={ch_id}")
    await monitor_service.remove_source(str(callback.from_user.id), ch_id)
    await callback.answer(f"🗑️ Deleted")
    await edit_sources_menu(callback.message)

@router.callback_query(F.data.startswith("src:page:"))
async def cb_page(callback: types.CallbackQuery):
    page = int(callback.data.split(":")[2])
    text, markup = get_sources_menu_ui(page)
    await callback.answer()
    try:
        await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except:
        pass

@router.callback_query(F.data == "src:noop")
async def cb_noop(callback: types.CallbackQuery):
    await callback.answer()

@router.callback_query(F.data == "src:clear_confirm")
async def cb_clear_confirm(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.button(text="⚠️ Yes, delete all", callback_data="src:clear_yes")
    builder.button(text="❌ Cancel", callback_data="nav:sources")
    builder.adjust(1)
    
    await callback.answer()
    try:
        await callback.message.edit_text(
            "⚠️ <b>Clear All Sources?</b>\n\n"
            "This will remove all source channels.\n"
            "This action cannot be undone.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
    except:
        pass

@router.callback_query(F.data == "src:clear_yes")
async def cb_clear_yes(callback: types.CallbackQuery):
    # Clear all sources
    user_id = str(callback.from_user.id)
    for src in list(monitor_service.source_channels):
        await monitor_service.remove_source(user_id, src)
    
    await callback.answer("🗑️ All sources cleared")
    await edit_sources_menu(callback.message)

# ─────────────────────────────────────────────────────────────────────────────
# Add Source Command
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("add"))
async def cmd_add(message: types.Message, command: CommandObject):
    if not is_allowed(message.from_user.id): return
    
    channel = command.args
    if not channel:
        await message.answer(
            "📡 <b>Add Source Channel</b>\n\n"
            "Usage: <code>/add &lt;channel&gt;</code>\n\n"
            "Examples:\n"
            "• <code>/add @channelname</code>\n"
            "• <code>/add -1001234567890</code>",
            parse_mode="HTML"
        )
        return
    
    await monitor_service.add_source(str(message.from_user.id), channel.strip())
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📡 View Sources", callback_data="nav:sources")
    builder.button(text="🏠 Main Menu", callback_data="nav:main")
    builder.adjust(2)
    
    await message.answer(
        f"✅ Added source: <code>{channel}</code>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@router.message(Command("clear"))
async def cmd_clear(message: types.Message):
    if not is_allowed(message.from_user.id): return
    
    if not monitor_service.source_channels:
        await message.answer("📭 No sources to clear.")
        return
    
    builder = InlineKeyboardBuilder()
    builder.button(text="⚠️ Yes, delete all", callback_data="src:clear_yes")
    builder.button(text="❌ Cancel", callback_data="nav:main")
    builder.adjust(1)
    
    await message.answer(
        f"⚠️ <b>Clear All Sources?</b>\n\n"
        f"This will remove <b>{len(monitor_service.source_channels)}</b> source channels.\n"
        f"This action cannot be undone.",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

# ─────────────────────────────────────────────────────────────────────────────
# VIP User Management
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("vip"))
async def cmd_vip(message: types.Message, command: CommandObject):
    if not is_allowed(message.from_user.id): return
    
    user = command.args
    if not user:
        await message.answer(
            "⭐ <b>Add VIP User</b>\n\n"
            "Usage: <code>/vip &lt;user&gt;</code>\n\n"
            "Examples:\n"
            "• <code>/vip @username</code>\n"
            "• <code>/vip 123456789</code>\n\n"
            "💡 <i>VIP users' messages are forwarded immediately without buffering.</i>",
            parse_mode="HTML"
        )
        return
    
    await monitor_service.add_vip_user(user.strip(), user.strip())
    
    builder = InlineKeyboardBuilder()
    builder.button(text="⭐ View VIPs", callback_data="nav:vips")
    builder.button(text="🏠 Main Menu", callback_data="nav:main")
    builder.adjust(2)
    
    await message.answer(
        f"⭐ Added VIP user: <code>{user}</code>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@router.message(Command("unvip"))
async def cmd_unvip(message: types.Message, command: CommandObject):
    if not is_allowed(message.from_user.id): return
    
    user = command.args
    if not user:
        await message.answer(
            "⭐ <b>Remove VIP User</b>\n\n"
            "Usage: <code>/unvip &lt;user&gt;</code>",
            parse_mode="HTML"
        )
        return
    
    await monitor_service.remove_vip_user(user.strip())
    await message.answer(f"🗑️ Removed VIP user: <code>{user}</code>", parse_mode="HTML")

@router.message(Command("vips"))
async def cmd_vips(message: types.Message):
    if not is_allowed(message.from_user.id): return
    text, markup = get_vips_menu_ui()
    await message.answer(text, reply_markup=markup, parse_mode="HTML")

async def edit_vips_menu(message: types.Message):
    text, markup = get_vips_menu_ui()
    try:
        await message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except:
        pass

def get_vips_menu_ui(page: int = 0):
    vips_list = list(monitor_service.vip_users.values())
    page_size = 5
    total_pages = max(1, (len(vips_list) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    
    if not vips_list:
        text = (
            "⭐ <b>VIP Users</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "📭 No VIP users configured.\n\n"
            "💡 <i>Use /vip &lt;user&gt; to add a VIP user.</i>"
        )
        kb = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="◀️ Back", callback_data="nav:main")]
        ])
        return text, kb
    
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, len(vips_list))
    page_vips = vips_list[start_idx:end_idx]
    
    text = f"⭐ <b>VIP Users</b> ({len(vips_list)} total)\n━━━━━━━━━━━━━━━━━━━━━\n"
    
    keyboard = []
    
    for i, vip_info in enumerate(page_vips, start=start_idx + 1):
        is_disabled = not vip_info.get('enabled', True)
        icon = "🔴" if is_disabled else "🟢"
        user_id = vip_info['id']
        name = vip_info.get('name', user_id)
        username = vip_info.get('username', '')
        
        display_name = name[:20] + "..." if len(name) > 20 else name
        if username and username != user_id:
            text += f"{i}. {icon} <b>{display_name}</b>\n    @{username} (<code>{user_id}</code>)\n"
        else:
            text += f"{i}. {icon} <code>{user_id}</code>\n"
        
        btn_label = f"{i}. {name[:10]}"
        uid_short = user_id[:30]
        
        row = [
            types.InlineKeyboardButton(text=btn_label, callback_data="vip:noop"),
            types.InlineKeyboardButton(
                text="✅ On" if is_disabled else "⏸️ Off",
                callback_data=f"vip:{'enable' if is_disabled else 'disable'}:{uid_short}"
            ),
            types.InlineKeyboardButton(text="🗑️", callback_data=f"vip:delete:{uid_short}")
        ]
        keyboard.append(row)
    
    if total_pages > 1:
        pagination = []
        if page > 0:
            pagination.append(types.InlineKeyboardButton(text="◀️ Prev", callback_data=f"vip:page:{page-1}"))
        pagination.append(types.InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="vip:noop"))
        if page < total_pages - 1:
            pagination.append(types.InlineKeyboardButton(text="Next ▶️", callback_data=f"vip:page:{page+1}"))
        keyboard.append(pagination)
    
    keyboard.append([
        types.InlineKeyboardButton(text="◀️ Back", callback_data="nav:main"),
    ])
    
    kb = types.InlineKeyboardMarkup(inline_keyboard=keyboard)
    return text, kb

@router.callback_query(F.data == "nav:vips")
async def cb_vips(callback: types.CallbackQuery):
    await callback.answer()
    await edit_vips_menu(callback.message)

def find_vip_by_prefix(prefix: str) -> str:
    for uid in monitor_service.vip_users.keys():
        if uid.startswith(prefix):
            return uid
    return prefix

@router.callback_query(F.data.startswith("vip:enable:"))
async def cb_enable_vip(callback: types.CallbackQuery):
    uid_key = callback.data.split(":", 2)[2]
    uid = find_vip_by_prefix(uid_key)
    await monitor_service.toggle_vip_user(uid, True)
    await callback.answer("✅ Enabled")
    await edit_vips_menu(callback.message)

@router.callback_query(F.data.startswith("vip:disable:"))
async def cb_disable_vip(callback: types.CallbackQuery):
    uid_key = callback.data.split(":", 2)[2]
    uid = find_vip_by_prefix(uid_key)
    await monitor_service.toggle_vip_user(uid, False)
    await callback.answer("⏸️ Disabled")
    await edit_vips_menu(callback.message)

@router.callback_query(F.data.startswith("vip:delete:"))
async def cb_delete_vip(callback: types.CallbackQuery):
    uid_key = callback.data.split(":", 2)[2]
    uid = find_vip_by_prefix(uid_key)
    await monitor_service.remove_vip_user(uid)
    await callback.answer("🗑️ Deleted")
    await edit_vips_menu(callback.message)

@router.callback_query(F.data.startswith("vip:page:"))
async def cb_vip_page(callback: types.CallbackQuery):
    page = int(callback.data.split(":")[2])
    text, markup = get_vips_menu_ui(page)
    await callback.answer()
    try:
        await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except:
        pass

@router.callback_query(F.data == "vip:noop")
async def cb_vip_noop(callback: types.CallbackQuery):
    await callback.answer()

# ─────────────────────────────────────────────────────────────────────────────
# History Command
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("history"))
async def cmd_history(message: types.Message):
    if not is_allowed(message.from_user.id): return
    
    # For now, just show a placeholder
    await message.answer(
        "📜 <b>Recent Forwards</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "<i>History feature coming soon...</i>",
        parse_mode="HTML"
    )

# ─────────────────────────────────────────────────────────────────────────────
# Twitter Monitoring
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("twitter"))
async def cmd_twitter(message: types.Message, command: CommandObject):
    if not is_allowed(message.from_user.id): return
    
    username = command.args
    if not username:
        await message.answer(
            "🐦 <b>Follow Twitter Account</b>\n\n"
            "Usage: <code>/twitter &lt;username&gt;</code>\n\n"
            "Example: <code>/twitter elonmusk</code>",
            parse_mode="HTML"
        )
        return
    
    success = await twitter_service.add_follow(username.strip())
    if success:
        await message.answer(f"🐦 Following: <code>@{username.strip().lstrip('@')}</code>", parse_mode="HTML")
    else:
        await message.answer(f"Already following @{username.strip().lstrip('@')}")

@router.message(Command("untwitter"))
async def cmd_untwitter(message: types.Message, command: CommandObject):
    if not is_allowed(message.from_user.id): return
    
    username = command.args
    if not username:
        await message.answer(
            "🐦 <b>Unfollow Twitter Account</b>\n\n"
            "Usage: <code>/untwitter &lt;username&gt;</code>",
            parse_mode="HTML"
        )
        return
    
    success = await twitter_service.remove_follow(username.strip())
    if success:
        await message.answer(f"🗑️ Unfollowed: <code>@{username.strip().lstrip('@')}</code>", parse_mode="HTML")
    else:
        await message.answer(f"Not following @{username.strip().lstrip('@')}")

@router.message(Command("twitters"))
async def cmd_twitters(message: types.Message):
    if not is_allowed(message.from_user.id): return
    text, markup = get_twitters_menu_ui()
    await message.answer(text, reply_markup=markup, parse_mode="HTML")

def get_twitters_menu_ui(page: int = 0):
    follows_list = list(twitter_service.follows.values())
    page_size = 5
    total_pages = max(1, (len(follows_list) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    
    if not follows_list:
        text = (
            "🐦 <b>Twitter Follows</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "📭 No Twitter accounts followed.\n\n"
            "💡 <i>Use /twitter &lt;username&gt; to follow.</i>"
        )
        kb = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="◀️ Back", callback_data="nav:main")]
        ])
        return text, kb
    
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, len(follows_list))
    page_follows = follows_list[start_idx:end_idx]
    
    text = f"🐦 <b>Twitter Follows</b> ({len(follows_list)} total)\n━━━━━━━━━━━━━━━━━━━━━\n"
    
    keyboard = []
    
    for i, info in enumerate(page_follows, start=start_idx + 1):
        is_disabled = not info.get('enabled', True)
        icon = "🔴" if is_disabled else "🟢"
        username = info['username']
        
        text += f"{i}. {icon} <code>@{username}</code>\n"
        
        row = [
            types.InlineKeyboardButton(text=f"{i}. @{username[:8]}", callback_data="tw:noop"),
            types.InlineKeyboardButton(
                text="✅ On" if is_disabled else "⏸️ Off",
                callback_data=f"tw:{'enable' if is_disabled else 'disable'}:{username}"
            ),
            types.InlineKeyboardButton(text="🗑️", callback_data=f"tw:delete:{username}")
        ]
        keyboard.append(row)
    
    if total_pages > 1:
        pagination = []
        if page > 0:
            pagination.append(types.InlineKeyboardButton(text="◀️ Prev", callback_data=f"tw:page:{page-1}"))
        pagination.append(types.InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="tw:noop"))
        if page < total_pages - 1:
            pagination.append(types.InlineKeyboardButton(text="Next ▶️", callback_data=f"tw:page:{page+1}"))
        keyboard.append(pagination)
    
    keyboard.append([types.InlineKeyboardButton(text="◀️ Back", callback_data="nav:main")])
    
    kb = types.InlineKeyboardMarkup(inline_keyboard=keyboard)
    return text, kb

async def edit_twitters_menu(message: types.Message):
    text, markup = get_twitters_menu_ui()
    try:
        await message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except:
        pass

@router.callback_query(F.data == "nav:twitters")
async def cb_twitters(callback: types.CallbackQuery):
    await callback.answer()
    await edit_twitters_menu(callback.message)

@router.callback_query(F.data.startswith("tw:enable:"))
async def cb_enable_twitter(callback: types.CallbackQuery):
    username = callback.data.split(":", 2)[2]
    await twitter_service.toggle_follow(username, True)
    await callback.answer("✅ Enabled")
    await edit_twitters_menu(callback.message)

@router.callback_query(F.data.startswith("tw:disable:"))
async def cb_disable_twitter(callback: types.CallbackQuery):
    username = callback.data.split(":", 2)[2]
    await twitter_service.toggle_follow(username, False)
    await callback.answer("⏸️ Disabled")
    await edit_twitters_menu(callback.message)

@router.callback_query(F.data.startswith("tw:delete:"))
async def cb_delete_twitter(callback: types.CallbackQuery):
    username = callback.data.split(":", 2)[2]
    await twitter_service.remove_follow(username)
    await callback.answer("🗑️ Deleted")
    await edit_twitters_menu(callback.message)

@router.callback_query(F.data.startswith("tw:page:"))
async def cb_twitter_page(callback: types.CallbackQuery):
    page = int(callback.data.split(":")[2])
    text, markup = get_twitters_menu_ui(page)
    await callback.answer()
    try:
        await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except:
        pass

@router.callback_query(F.data == "tw:noop")
async def cb_twitter_noop(callback: types.CallbackQuery):
    await callback.answer()
