from aiogram import Router, F, types
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.services.ai import ai_service
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
logger = Logger("AIBot")

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    logger.info(f"AI /start from user {message.from_user.id}")
    if not is_allowed(message.from_user.id):
        logger.warn(f"User {message.from_user.id} not allowed")
        return
    try:
        await send_main_menu(message)
    except Exception as e:
        logger.error(f"Error in AI /start: {e}")
        await message.answer(f"❌ Error: {e}")

async def send_main_menu(message: types.Message):
    text, markup = await get_main_menu_ui(message.from_user.id)
    await message.answer(text, parse_mode="HTML", reply_markup=markup)

async def edit_main_menu(message: types.Message, user_id: int):
    text, markup = await get_main_menu_ui(user_id)
    try:
        await message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except:
        pass

async def get_main_menu_ui(user_id: int):
    user_settings = await ai_service.get_settings(user_id)
    providers = ai_service.list_providers()
    active = next((p for p in providers if p["active"]), None)
    chats = await ai_service.get_chats(user_id, 1)
    active_chat = next((c for c in chats if c.get("is_active")), None)
    
    provider_name = active['name'] if active else 'Not configured'
    model_name = user_settings.get('model', 'default')
    chat_title = active_chat.get('title', 'None')[:25] if active_chat else 'None'
    
    text = (
        "🧠 <b>AI Bot</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔌 Provider: <b>{provider_name}</b>\n"
        f"📝 Model: <code>{model_name[:30]}</code>\n"
        f"💬 Chat: <b>{chat_title}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Send any message to chat with AI!</i>"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✨ New Chat", callback_data="ai:new")
    builder.button(text="💬 My Chats", callback_data="ai:chats")
    builder.button(text="🔌 Providers", callback_data="ai:providers")
    builder.button(text="📝 Models", callback_data="ai:models")
    builder.button(text="🚀 Advanced", callback_data="ai:advanced")
    builder.button(text="📤 Export", callback_data="ai:export")
    builder.button(text="🔄 Refresh", callback_data="ai:refresh")
    builder.adjust(2, 2, 2, 1)
    
    return text, builder.as_markup()

@router.callback_query(F.data == "ai:refresh")
async def cb_refresh(callback: types.CallbackQuery):
    await callback.answer("🔄 Refreshed")
    await edit_main_menu(callback.message, callback.from_user.id)

@router.callback_query(F.data == "ai:main")
async def cb_main(callback: types.CallbackQuery):
    await callback.answer()
    await edit_main_menu(callback.message, callback.from_user.id)

@router.callback_query(F.data == "ai:advanced")
async def cb_advanced(callback: types.CallbackQuery):
    """Show advanced AI menu with agents, tools, skills."""
    await callback.answer()
    
    from app.services.ai.advanced_service import advanced_ai_service
    from app.services.ai.advanced_storage import advanced_ai_storage
    await advanced_ai_service.initialize()
    
    status = advanced_ai_service.get_status()
    user_settings = await advanced_ai_storage.get_agent_settings(callback.from_user.id)
    current_agent = user_settings.get("default_agent", "chat")
    
    from app.services.ai.skills import skill_registry
    skill_registry.load_skills()
    skills_count = len(skill_registry.list_all())
    
    text = (
        "🚀 <b>Advanced AI</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔌 Provider: <b>{status.get('provider', 'N/A')}</b>\n"
        f"🤖 Agent: <b>{current_agent}</b>\n"
        f"🔧 Tools: <b>{status.get('tools_count', 0)}</b> | "
        f"📚 Skills: <b>{skills_count}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Tap an agent to switch, then use /ask</i>"
    )
    
    builder = InlineKeyboardBuilder()
    # Quick agent switch buttons
    agents = ["chat", "research", "code", "devops", "writer"]
    for agent in agents:
        icon = "✅" if agent == current_agent else "⚪"
        builder.button(text=f"{icon} {agent}", callback_data=f"adv:switch:{agent}")
    builder.button(text="🔧 Tools", callback_data="adv:tools")
    builder.button(text="📚 Skills", callback_data="adv:skills")
    builder.button(text="⬅️ Back", callback_data="ai:main")
    builder.adjust(3, 2, 2, 1)
    
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    except:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("adv:switch:"))
async def cb_adv_switch_agent(callback: types.CallbackQuery):
    """Quick switch agent from Advanced menu."""
    agent_name = callback.data.split(":")[2]
    
    from app.services.ai.advanced_storage import advanced_ai_storage
    await advanced_ai_storage.update_agent_settings(callback.from_user.id, default_agent=agent_name)
    
    await callback.answer(f"✅ Switched to {agent_name}")
    # Refresh the advanced menu
    await cb_advanced(callback)

@router.callback_query(F.data == "adv:agents")
async def cb_adv_agents(callback: types.CallbackQuery):
    """Redirect to advanced menu (agents are shown there now)."""
    await cb_advanced(callback)

@router.callback_query(F.data == "adv:tools")
async def cb_adv_tools(callback: types.CallbackQuery):
    from app.services.ai.advanced_service import advanced_ai_service
    await advanced_ai_service.initialize()
    tools = advanced_ai_service.list_tools()
    
    text = f"🔧 <b>Available Tools</b> ({len(tools)})\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    # Group by prefix
    by_cat = {}
    for t in tools:
        cat = t['name'].split('_')[0] if '_' in t['name'] else 'general'
        by_cat.setdefault(cat, []).append(t['name'])
    for cat, names in list(by_cat.items())[:5]:
        text += f"<b>{cat}</b>: {', '.join(names[:3])}\n"
    text += f"\n<i>+{len(tools) - 10} more. Use /tools for full list</i>"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Back", callback_data="ai:advanced")
    
    await callback.answer()
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    except:
        pass

@router.callback_query(F.data == "adv:skills")
async def cb_adv_skills(callback: types.CallbackQuery):
    from app.services.ai.skills import skill_registry
    skill_registry.load_skills()
    skills = skill_registry.get_skill_info()
    
    text = f"📚 <b>Available Skills</b> ({len(skills)})\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    for s in skills[:8]:
        text += f"• <b>{s['name']}</b>\n"
    if len(skills) > 8:
        text += f"\n<i>+{len(skills) - 8} more. Use /skills for full list</i>"
    text += "\n\n<i>Skills auto-match based on your message</i>"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Back", callback_data="ai:advanced")
    
    await callback.answer()
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    except:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Chats
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("chats"))
async def cmd_chats(message: types.Message):
    if not is_allowed(message.from_user.id):
        return
    text, markup = await get_chats_ui(message.from_user.id)
    await message.answer(text, parse_mode="HTML", reply_markup=markup)

@router.callback_query(F.data == "ai:chats")
async def cb_chats(callback: types.CallbackQuery):
    await callback.answer()
    text, markup = await get_chats_ui(callback.from_user.id)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=markup)

async def get_chats_ui(user_id: int):
    chats = await ai_service.get_chats(user_id, 10)
    
    if not chats:
        text = (
            "💬 <b>My Chats</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "📭 No chats yet.\n\n"
            "<i>Send any message to start chatting!</i>"
        )
        builder = InlineKeyboardBuilder()
        builder.button(text="✨ New Chat", callback_data="ai:new")
        builder.button(text="◀️ Back", callback_data="ai:main")
        builder.adjust(2)
        return text, builder.as_markup()
    
    text = f"💬 <b>My Chats</b> ({len(chats)})\n━━━━━━━━━━━━━━━━━━━━━\n"
    
    builder = InlineKeyboardBuilder()
    for chat in chats:
        title = chat.get("title", "Untitled")[:22]
        is_active = chat.get("is_active")
        icon = "✅" if is_active else "💬"
        builder.button(text=f"{icon} {title}", callback_data=f"chat:switch:{chat['id']}")
        builder.button(text="🗑️", callback_data=f"chat:delete:{chat['id']}")
    
    builder.adjust(2)  # Chat button + delete button per row
    
    # Add navigation
    kb = builder.as_markup()
    kb.inline_keyboard.append([
        types.InlineKeyboardButton(text="✨ New", callback_data="ai:new"),
        types.InlineKeyboardButton(text="◀️ Back", callback_data="ai:main"),
    ])
    
    return text, kb

@router.callback_query(F.data == "ai:new")
async def cb_new(callback: types.CallbackQuery):
    await ai_service.create_chat(callback.from_user.id)
    await callback.answer("✨ New chat started!")
    await edit_main_menu(callback.message, callback.from_user.id)

@router.message(Command("new"))
async def cmd_new(message: types.Message):
    if not is_allowed(message.from_user.id):
        return
    await ai_service.create_chat(message.from_user.id)
    await message.answer("✨ New chat started! Send any message to begin.")

@router.callback_query(F.data.startswith("chat:switch:"))
async def cb_chat_switch(callback: types.CallbackQuery):
    chat_id = int(callback.data.split(":")[2])
    chat = await ai_service.switch_chat(callback.from_user.id, chat_id)
    await callback.answer(f"Switched to: {chat.get('title', 'Chat')}" if chat else "Chat not found")
    await edit_main_menu(callback.message, callback.from_user.id)

@router.callback_query(F.data.startswith("chat:delete:"))
async def cb_chat_delete(callback: types.CallbackQuery):
    chat_id = int(callback.data.split(":")[2])
    await ai_service.clear_chat(chat_id)
    await callback.answer("🗑️ Chat deleted")
    text, markup = await get_chats_ui(callback.from_user.id)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except:
        pass

# ─────────────────────────────────────────────────────────────────────────────
# Providers
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("providers"))
async def cmd_providers(message: types.Message):
    if not is_allowed(message.from_user.id):
        return
    text, markup = get_providers_ui()
    await message.answer(text, parse_mode="HTML", reply_markup=markup)

@router.callback_query(F.data == "ai:providers")
async def cb_providers(callback: types.CallbackQuery):
    await callback.answer()
    text, markup = get_providers_ui()
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=markup)

def get_providers_ui():
    providers = ai_service.list_providers()
    
    text = (
        "🔌 <b>AI Providers</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
    )
    
    builder = InlineKeyboardBuilder()
    for p in providers:
        if p["configured"]:
            status = "✅"
        else:
            status = "❌"
        active = " ⬅️" if p["active"] else ""
        builder.button(text=f"{status} {p['name']}{active}", callback_data=f"prov:select:{p['key']}")
    
    builder.adjust(1)
    
    kb = builder.as_markup()
    kb.inline_keyboard.append([
        types.InlineKeyboardButton(text="◀️ Back", callback_data="ai:main"),
    ])
    
    return text, kb

@router.callback_query(F.data.startswith("prov:select:"))
async def cb_provider_select(callback: types.CallbackQuery):
    provider_key = callback.data.split(":")[2]
    providers = ai_service.list_providers()
    provider = next((p for p in providers if p["key"] == provider_key), None)
    
    if not provider:
        await callback.answer("Unknown provider")
        return
    
    if not provider["configured"]:
        await callback.answer("⚠️ Not configured (missing API key)", show_alert=True)
        return
    
    models = await ai_service.get_models(provider_key)
    default_model = models[0]["id"] if models else "default"
    
    await ai_service.update_settings(callback.from_user.id, provider_key, default_model)
    await callback.answer(f"✅ Switched to {provider['name']}")
    await edit_main_menu(callback.message, callback.from_user.id)

# ─────────────────────────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("models"))
async def cmd_models(message: types.Message, command: CommandObject):
    if not is_allowed(message.from_user.id):
        return
    
    status = await message.answer("⏳ Fetching models...")
    text, markup = await get_models_ui(message.from_user.id, command.args)
    try:
        await status.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception as e:
        await status.edit_text(f"❌ Error: {e}")

@router.callback_query(F.data == "ai:models")
async def cb_models(callback: types.CallbackQuery):
    await callback.answer()
    text, markup = await get_models_ui(callback.from_user.id)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=markup)

async def get_models_ui(user_id: int, provider_override: str = None):
    user_settings = await ai_service.get_settings(user_id)
    provider_key = provider_override or user_settings.get("provider", "groq")
    
    models = await ai_service.get_models(provider_key)
    
    if not models:
        text = (
            "📝 <b>Models</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "❌ No models found or provider not configured."
        )
        builder = InlineKeyboardBuilder()
        builder.button(text="◀️ Back", callback_data="ai:main")
        return text, builder.as_markup()
    
    text = f"📝 <b>Models</b> ({provider_key})\n━━━━━━━━━━━━━━━━━━━━━\n"
    
    builder = InlineKeyboardBuilder()
    for m in models[:8]:
        current = "✅ " if m["id"] == user_settings.get("model") else ""
        display = m["id"][:28]
        builder.button(text=f"{current}{display}", callback_data=f"model:select:{m['id'][:45]}")
    
    builder.adjust(1)
    
    kb = builder.as_markup()
    kb.inline_keyboard.append([
        types.InlineKeyboardButton(text="◀️ Back", callback_data="ai:main"),
    ])
    
    return text, kb

@router.callback_query(F.data.startswith("model:select:"))
async def cb_model_select(callback: types.CallbackQuery):
    model_id = callback.data.split(":", 2)[2]
    user_settings = await ai_service.get_settings(callback.from_user.id)
    
    await ai_service.update_settings(callback.from_user.id, user_settings.get("provider", "groq"), model_id)
    await callback.answer(f"✅ Model: {model_id[:30]}")
    await edit_main_menu(callback.message, callback.from_user.id)

# ─────────────────────────────────────────────────────────────────────────────
# Export
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("export"))
async def cmd_export(message: types.Message):
    if not is_allowed(message.from_user.id):
        return
    await do_export(message.from_user.id, message)

@router.callback_query(F.data == "ai:export")
async def cb_export(callback: types.CallbackQuery):
    await callback.answer("📤 Exporting...")
    await do_export(callback.from_user.id, callback.message, is_callback=True)

async def do_export(user_id: int, message: types.Message, is_callback: bool = False):
    chats = await ai_service.get_chats(user_id, 1)
    active_chat = next((c for c in chats if c.get("is_active")), None)
    
    if not active_chat:
        await message.answer("❌ No active chat to export")
        return
    
    status = await message.answer("📤 Exporting chat...")
    
    try:
        result = await ai_service.export_chat(user_id, active_chat["id"])
        
        if result.get("urls"):
            text = (
                "✅ <b>Chat Exported!</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                f"📄 <a href=\"{result['urls']['raw']}\">Raw Conversation</a>\n"
                f"📝 <a href=\"{result['urls']['notes']}\">AI Notes</a>\n"
                f"\n<i>{result['message_count']} messages exported</i>"
            )
            await status.edit_text(text, parse_mode="HTML", disable_web_page_preview=True)
        else:
            from io import BytesIO
            file_content = result.get("raw_markdown", "No content")
            file_bytes = BytesIO(file_content.encode("utf-8"))
            file_bytes.name = result.get("filename", "chat.md")
            
            await status.edit_text("📤 Preparing file...")
            await message.answer_document(file_bytes, caption="ℹ️ GitHub not configured. Set NOTES_REPO to enable cloud export.")
    except Exception as e:
        await status.edit_text(f"❌ Export failed: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# Help & Status
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("help"))
async def cmd_help(message: types.Message):
    if not is_allowed(message.from_user.id):
        return
    text = (
        "🧠 <b>AI Bot Commands</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "/start - Main menu\n"
        "/new - Start new chat\n"
        "/chats - List/switch chats\n"
        "/rename &lt;title&gt; - Rename chat\n"
        "/clear - Clear chat history\n"
        "/export - Export to GitHub\n"
        "/providers - Select provider\n"
        "/models - Select model\n"
        "/status - Bot status\n"
        "/help - This message"
    )
    await message.answer(text, parse_mode="HTML")

@router.message(Command("status"))
async def cmd_status(message: types.Message):
    if not is_allowed(message.from_user.id):
        return
    
    providers = ai_service.list_providers()
    user_settings = await ai_service.get_settings(message.from_user.id)
    active = next((p for p in providers if p["active"]), None)
    configured = [p for p in providers if p["configured"]]
    
    text = (
        "📊 <b>AI Bot Status</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔌 Provider: <b>{active['name'] if active else 'None'}</b>\n"
        f"📝 Model: <code>{user_settings.get('model', 'default')}</code>\n"
        f"✅ Configured: {len(configured)}/{len(providers)} providers"
    )
    await message.answer(text, parse_mode="HTML")

@router.message(Command("rename"))
async def cmd_rename(message: types.Message, command: CommandObject):
    if not is_allowed(message.from_user.id):
        return
    
    title = command.args
    if not title:
        await message.answer("Usage: /rename &lt;new title&gt;", parse_mode="HTML")
        return
    
    chats = await ai_service.get_chats(message.from_user.id, 1)
    active_chat = next((c for c in chats if c.get("is_active")), None)
    
    if not active_chat:
        await message.answer("❌ No active chat to rename")
        return
    
    await ai_service.rename_chat(active_chat["id"], title)
    await message.answer(f"✅ Renamed to: <b>{title}</b>", parse_mode="HTML")

@router.message(Command("clear"))
async def cmd_clear(message: types.Message):
    if not is_allowed(message.from_user.id):
        return
    
    chats = await ai_service.get_chats(message.from_user.id, 1)
    active_chat = next((c for c in chats if c.get("is_active")), None)
    
    if not active_chat:
        await message.answer("❌ No active chat to clear")
        return
    
    await ai_service.clear_chat(active_chat["id"])
    await message.answer("🗑️ Chat history cleared")

# ─────────────────────────────────────────────────────────────────────────────
# Chat Handler (catch-all for AI messages)
# ─────────────────────────────────────────────────────────────────────────────

@router.message()
async def handle_chat(message: types.Message):
    """Handle all text messages as chat input."""
    if not is_allowed(message.from_user.id):
        return
    
    prompt = message.text
    if not prompt:
        return

    status = await message.answer("🤔 Thinking...")
    
    try:
        # Get user settings for context display
        user_settings = await ai_service.get_settings(message.from_user.id)
        provider_name = user_settings.get("provider", "groq")
        model_name = user_settings.get("model", "default")
        
        # Get active chat info
        chats = await ai_service.get_chats(message.from_user.id, 1)
        active_chat = next((c for c in chats if c.get("is_active")), None)
        chat_title = active_chat.get("title", "Chat")[:15] if active_chat else "Chat"
        
        result = await ai_service.chat(message.from_user.id, prompt)
        response = result.get("content", "No response")
        
        if len(response) > 4000:
            response = response[:4000] + "\n\n...(truncated)"
        
        try:
            await status.edit_text(response, parse_mode="Markdown")
        except Exception:
            # Fallback to plain text if markdown parsing fails
            await status.edit_text(response)
        
        # Quick actions with context info
        builder = InlineKeyboardBuilder()
        builder.button(text="✨ New", callback_data="ai:new")
        builder.button(text="💬 Chats", callback_data="ai:chats")
        builder.button(text="📤 Export", callback_data="ai:export")
        builder.adjust(3)
        
        # Show context in the quick actions message
        context_info = f"<code>{chat_title}</code> • <code>{model_name[:20]}</code>"
        await message.answer(context_info, parse_mode="HTML", reply_markup=builder.as_markup())
    except Exception as e:
        await status.edit_text(f"❌ Error: {str(e)}")
