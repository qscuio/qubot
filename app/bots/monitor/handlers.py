from aiogram import Router, F, types
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.services.monitor import monitor_service
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
        "/help - This message\n\n"
        "<b>📡 Channel Management</b>\n"
        "/add &lt;channel&gt; - Add source channel\n"
        "/remove &lt;channel&gt; - Remove source channel\n"
        "/clear - Remove all sources\n\n"
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
    builder.button(text="⚙️ Settings", callback_data="src:noop") # Placeholder
    
    # Utility row
    builder.button(text="🔄 Sync", callback_data="nav:refresh")
    builder.button(text="❓ Help", callback_data="nav:help") # Will need to add callback
    
    builder.adjust(1, 2, 2)
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
