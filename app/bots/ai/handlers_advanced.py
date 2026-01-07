"""
Advanced AI Bot handlers for agent and tool features.
"""

import html

from aiogram import Router, F, types
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.services.ai.advanced_service import advanced_ai_service
from app.services.ai.advanced_storage import advanced_ai_storage
from app.core.config import settings
from app.core.logger import Logger

router = Router()
logger = Logger("AdvancedAIBot")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def is_allowed(user_id: int) -> bool:
    if not settings.allowed_users_list:
        return True
    return user_id in settings.allowed_users_list


def _truncate(text: str, max_len: int) -> str:
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _escape(text: str) -> str:
    return html.escape(text or "")


# ─────────────────────────────────────────────────────────────────────────────
# Main Menu
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    if not is_allowed(message.from_user.id):
        return
    await send_main_menu(message)

@router.callback_query(F.data == "adv:main")
async def cb_main(callback: types.CallbackQuery):
    await callback.answer()
    await edit_main_menu(callback.message, callback.from_user.id)

@router.callback_query(F.data == "adv:refresh")
async def cb_refresh(callback: types.CallbackQuery):
    await callback.answer("🔄 Refreshed")
    await edit_main_menu(callback.message, callback.from_user.id)

async def send_main_menu(message: types.Message):
    text, markup = await get_main_menu_ui(message.from_user.id)
    await message.answer(text, parse_mode="HTML", reply_markup=markup)

async def edit_main_menu(message: types.Message, user_id: int):
    text, markup = await get_main_menu_ui(user_id)
    try:
        await message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        await message.answer(text, parse_mode="HTML", reply_markup=markup)

async def get_main_menu_ui(user_id: int):
    await advanced_ai_service.initialize()
    user_settings = await advanced_ai_storage.get_agent_settings(user_id)
    provider_key = (user_settings.get("provider") or settings.AI_ADVANCED_PROVIDER or "groq").lower()
    model_name = user_settings.get("model") or "default"
    agent_name = user_settings.get("default_agent", "chat")
    auto_route = user_settings.get("auto_route", False)

    chats = await advanced_ai_storage.get_user_chats(user_id, 1)
    active_chat = next((c for c in chats if c.get("is_active")), None)
    chat_title = active_chat.get("title", "None")[:25] if active_chat else "None"

    text = (
        "🚀 <b>Advanced AI Bot</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔌 Provider: <b>{provider_key}</b>\n"
        f"📝 Model: <code>{model_name[:30]}</code>\n"
        f"🤖 Agent: <b>{agent_name}</b>\n"
        f"💬 Chat: <b>{chat_title}</b>\n"
        f"🔄 Auto-Route: {'✅' if auto_route else '❌'}\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Send any message to chat with agents and tools.</i>"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="✨ New Chat", callback_data="adv:chat:new")
    builder.button(text="💬 My Chats", callback_data="adv:chat:list")
    builder.button(text="🔌 Providers", callback_data="adv:providers")
    builder.button(text="📝 Models", callback_data="adv:models")
    builder.button(text="🤖 Agents", callback_data="adv:agents")
    builder.button(text="🔄 Auto-Route", callback_data="adv:autoroute:menu")
    builder.button(text="🔧 Tools", callback_data="adv:tools")
    builder.button(text="📚 Skills", callback_data="adv:skills")
    builder.button(text="📤 Export", callback_data="adv:export")
    builder.button(text="🔄 Refresh", callback_data="adv:refresh")
    builder.adjust(2, 2, 2, 2, 2)

    return text, builder.as_markup()


# ─────────────────────────────────────────────────────────────────────────────
# Agent Commands
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("agent"))
async def cmd_agent(message: types.Message, command: CommandObject):
    """List or switch agents."""
    if not is_allowed(message.from_user.id):
        return
    
    await advanced_ai_service.initialize()
    
    if command.args:
        # Switch to specified agent
        agent_name = command.args.strip().lower()
        agents = advanced_ai_service.list_agents()
        agent_names = [a["name"] for a in agents]
        
        if agent_name in agent_names:
            await advanced_ai_storage.update_agent_settings(
                message.from_user.id, 
                default_agent=agent_name
            )
            await message.answer(f"✅ Switched to <b>{agent_name}</b> agent", parse_mode="HTML")
        else:
            await message.answer(
                f"❌ Unknown agent: {agent_name}\n"
                f"Available: {', '.join(agent_names)}"
            )
        return
    
    text, markup = await get_agents_ui(message.from_user.id)
    await message.answer(text, parse_mode="HTML", reply_markup=markup)

@router.callback_query(F.data == "adv:agents")
async def cb_agents(callback: types.CallbackQuery):
    await callback.answer()
    text, markup = await get_agents_ui(callback.from_user.id)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=markup)

async def get_agents_ui(user_id: int):
    await advanced_ai_service.initialize()
    agents = advanced_ai_service.list_agents()
    user_settings = await advanced_ai_storage.get_agent_settings(user_id)
    current = user_settings.get("default_agent", "chat")
    
    text = "🤖 <b>Available Agents</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
    
    builder = InlineKeyboardBuilder()
    for agent in agents:
        icon = "✅" if agent["name"] == current else "💬"
        text += f"\n{icon} <b>{agent['name']}</b>\n   <i>{agent['description'][:50]}...</i>\n"
        builder.button(text=f"{icon} {agent['name']}", callback_data=f"adv:agent:{agent['name']}")
    
    builder.adjust(2)
    kb = builder.as_markup()
    kb.inline_keyboard.append([
        types.InlineKeyboardButton(text="🔄 Auto-Route", callback_data="adv:autoroute")
    ])
    kb.inline_keyboard.append([
        types.InlineKeyboardButton(text="⬅️ Back", callback_data="adv:main")
    ])
    
    return text, kb


@router.callback_query(F.data.startswith("adv:agent:"))
async def cb_agent_switch(callback: types.CallbackQuery):
    agent_name = callback.data.split(":")[2]
    await advanced_ai_storage.update_agent_settings(
        callback.from_user.id,
        default_agent=agent_name
    )
    await callback.answer(f"✅ Switched to {agent_name}")
    if callback.message and "Available Agents" in (callback.message.text or ""):
        text, markup = await get_agents_ui(callback.from_user.id)
        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
        except Exception:
            pass
    elif callback.message and "Advanced AI Bot" in (callback.message.text or ""):
        await edit_main_menu(callback.message, callback.from_user.id)


@router.callback_query(F.data == "adv:autoroute")
async def cb_autoroute(callback: types.CallbackQuery):
    user_settings = await advanced_ai_storage.get_agent_settings(callback.from_user.id)
    new_value = not user_settings.get("auto_route", False)
    await advanced_ai_storage.update_agent_settings(
        callback.from_user.id,
        auto_route=new_value
    )
    status = "enabled" if new_value else "disabled"
    await callback.answer(f"🔄 Auto-routing {status}")
    if callback.message and "Available Agents" in (callback.message.text or ""):
        text, markup = await get_agents_ui(callback.from_user.id)
        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
        except Exception:
            pass
    elif callback.message and "Advanced AI Bot" in (callback.message.text or ""):
        await edit_main_menu(callback.message, callback.from_user.id)

@router.callback_query(F.data == "adv:autoroute:menu")
async def cb_autoroute_menu(callback: types.CallbackQuery):
    await cb_autoroute(callback)


# ─────────────────────────────────────────────────────────────────────────────
# Chats
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("chats"))
async def cmd_chats(message: types.Message):
    if not is_allowed(message.from_user.id):
        return
    await advanced_ai_service.initialize()
    text, markup = await get_chats_ui(message.from_user.id)
    await message.answer(text, parse_mode="HTML", reply_markup=markup)

@router.callback_query(F.data == "adv:chat:list")
async def cb_chats(callback: types.CallbackQuery):
    await callback.answer()
    await advanced_ai_service.initialize()
    text, markup = await get_chats_ui(callback.from_user.id)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=markup)

@router.callback_query(F.data == "adv:chat:new")
async def cb_new_chat(callback: types.CallbackQuery):
    await advanced_ai_service.initialize()
    await advanced_ai_storage.create_new_chat(callback.from_user.id)
    await callback.answer("✨ New chat started!")
    await edit_main_menu(callback.message, callback.from_user.id)

@router.message(Command("new"))
async def cmd_new(message: types.Message):
    if not is_allowed(message.from_user.id):
        return
    await advanced_ai_service.initialize()
    await advanced_ai_storage.create_new_chat(message.from_user.id)
    await message.answer("✨ New chat started! Send any message to begin.")

@router.callback_query(F.data.startswith("advchat:switch:"))
async def cb_chat_switch(callback: types.CallbackQuery):
    chat_id = int(callback.data.split(":")[2])
    await advanced_ai_service.initialize()
    await advanced_ai_storage.set_active_chat(callback.from_user.id, chat_id)
    chat = await advanced_ai_storage.get_chat_by_id(chat_id)
    await callback.answer(f"Switched to: {chat.get('title', 'Chat')}" if chat else "Chat not found")
    await edit_main_menu(callback.message, callback.from_user.id)

@router.callback_query(F.data.startswith("advchat:delete:"))
async def cb_chat_delete(callback: types.CallbackQuery):
    chat_id = int(callback.data.split(":")[2])
    await advanced_ai_service.initialize()
    await advanced_ai_storage.delete_chat(chat_id)
    await callback.answer("🗑️ Chat deleted")
    text, markup = await get_chats_ui(callback.from_user.id)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        pass

async def get_chats_ui(user_id: int):
    await advanced_ai_service.initialize()
    chats = await advanced_ai_storage.get_user_chats(user_id, 10)
    
    if not chats:
        text = (
            "💬 <b>Advanced Chats</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "📭 No chats yet.\n\n"
            "<i>Send any message to start chatting!</i>"
        )
        builder = InlineKeyboardBuilder()
        builder.button(text="✨ New Chat", callback_data="adv:chat:new")
        builder.button(text="◀️ Back", callback_data="adv:main")
        builder.adjust(2)
        return text, builder.as_markup()
    
    text = f"💬 <b>Advanced Chats</b> ({len(chats)})\n━━━━━━━━━━━━━━━━━━━━━\n"
    
    builder = InlineKeyboardBuilder()
    for chat in chats:
        title = chat.get("title", "Untitled")[:22]
        is_active = chat.get("is_active")
        icon = "✅" if is_active else "💬"
        builder.button(text=f"{icon} {title}", callback_data=f"advchat:switch:{chat['id']}")
        builder.button(text="🗑️", callback_data=f"advchat:delete:{chat['id']}")
    
    builder.adjust(2)
    
    kb = builder.as_markup()
    kb.inline_keyboard.append([
        types.InlineKeyboardButton(text="✨ New", callback_data="adv:chat:new"),
        types.InlineKeyboardButton(text="◀️ Back", callback_data="adv:main"),
    ])
    
    return text, kb


@router.message(Command("rename"))
async def cmd_rename(message: types.Message, command: CommandObject):
    if not is_allowed(message.from_user.id):
        return
    await advanced_ai_service.initialize()
    
    title = command.args
    if not title:
        await message.answer("Usage: /rename &lt;new title&gt;", parse_mode="HTML")
        return
    
    chats = await advanced_ai_storage.get_user_chats(message.from_user.id, 1)
    active_chat = next((c for c in chats if c.get("is_active")), None)
    
    if not active_chat:
        await message.answer("❌ No active chat to rename")
        return
    
    await advanced_ai_storage.rename_chat(active_chat["id"], title)
    await message.answer(f"✅ Renamed to: <b>{title}</b>", parse_mode="HTML")


@router.message(Command("clear"))
async def cmd_clear(message: types.Message):
    if not is_allowed(message.from_user.id):
        return
    await advanced_ai_service.initialize()
    
    chats = await advanced_ai_storage.get_user_chats(message.from_user.id, 1)
    active_chat = next((c for c in chats if c.get("is_active")), None)
    
    if not active_chat:
        await message.answer("❌ No active chat to clear")
        return
    
    await advanced_ai_storage.delete_chat(active_chat["id"])
    await message.answer("🗑️ Chat history cleared")


# ─────────────────────────────────────────────────────────────────────────────
# Providers / Models
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("providers"))
async def cmd_providers(message: types.Message):
    if not is_allowed(message.from_user.id):
        return
    text, markup = await get_providers_ui(message.from_user.id)
    await message.answer(text, parse_mode="HTML", reply_markup=markup)

@router.callback_query(F.data == "adv:providers")
async def cb_providers(callback: types.CallbackQuery):
    await callback.answer()
    text, markup = await get_providers_ui(callback.from_user.id)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=markup)

async def get_providers_ui(user_id: int):
    await advanced_ai_service.initialize()
    providers = advanced_ai_service.list_providers()
    user_settings = await advanced_ai_storage.get_agent_settings(user_id)
    current_provider = (user_settings.get("provider") or settings.AI_ADVANCED_PROVIDER or "groq").lower()
    
    text = (
        "🔌 <b>Advanced Providers</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
    )
    
    builder = InlineKeyboardBuilder()
    for p in providers:
        status = "✅" if p["configured"] else "❌"
        tools = " 🧰" if p.get("supports_tools") else ""
        active = " ⬅️" if p["key"] == current_provider else ""
        builder.button(
            text=f"{status} {p['name']}{tools}{active}",
            callback_data=f"advprov:select:{p['key']}"
        )
    
    builder.adjust(1)
    kb = builder.as_markup()
    kb.inline_keyboard.append([
        types.InlineKeyboardButton(text="◀️ Back", callback_data="adv:main"),
    ])
    
    return text, kb

@router.callback_query(F.data.startswith("advprov:select:"))
async def cb_provider_select(callback: types.CallbackQuery):
    provider_key = callback.data.split(":")[2]
    await advanced_ai_service.initialize()
    providers = advanced_ai_service.list_providers()
    provider = next((p for p in providers if p["key"] == provider_key), None)
    
    if not provider:
        await callback.answer("Unknown provider")
        return
    
    if not provider["configured"]:
        await callback.answer("⚠️ Not configured (missing API key)", show_alert=True)
        return
    
    models = await advanced_ai_service.get_models(provider_key)
    provider_obj = advanced_ai_service.get_provider(provider_key)
    default_model = getattr(provider_obj, "default_model", None) if provider_obj else None
    if models:
        default_model = next((m["id"] for m in models if m["id"] == default_model), None) or models[0]["id"]
    if not default_model:
        default_model = "default"
    
    await advanced_ai_storage.update_agent_settings(
        callback.from_user.id,
        provider=provider_key,
        model=default_model
    )
    await callback.answer(f"✅ Switched to {provider['name']}")
    await edit_main_menu(callback.message, callback.from_user.id)


@router.message(Command("models"))
async def cmd_models(message: types.Message):
    if not is_allowed(message.from_user.id):
        return
    text, markup = await get_models_ui(message.from_user.id)
    await message.answer(text, parse_mode="HTML", reply_markup=markup)

@router.callback_query(F.data == "adv:models")
async def cb_models(callback: types.CallbackQuery):
    await callback.answer()
    text, markup = await get_models_ui(callback.from_user.id)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=markup)

async def get_models_ui(user_id: int):
    await advanced_ai_service.initialize()
    user_settings = await advanced_ai_storage.get_agent_settings(user_id)
    provider_key = (user_settings.get("provider") or settings.AI_ADVANCED_PROVIDER or "groq").lower()
    current_model = user_settings.get("model")
    
    models = await advanced_ai_service.get_models(provider_key)
    
    if not models:
        text = (
            "📝 <b>Advanced Models</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "❌ No models found or provider not configured."
        )
        builder = InlineKeyboardBuilder()
        builder.button(text="◀️ Back", callback_data="adv:main")
        return text, builder.as_markup()
    
    text = f"📝 <b>Advanced Models</b> ({provider_key})\n━━━━━━━━━━━━━━━━━━━━━\n"
    builder = InlineKeyboardBuilder()
    for m in models[:8]:
        current = "✅ " if m["id"] == current_model else ""
        display = m.get("name") or m["id"]
        builder.button(text=f"{current}{display}", callback_data=f"advmodel:select:{m['id'][:45]}")
    
    builder.adjust(1)
    kb = builder.as_markup()
    kb.inline_keyboard.append([
        types.InlineKeyboardButton(text="◀️ Back", callback_data="adv:main"),
    ])
    
    return text, kb

@router.callback_query(F.data.startswith("advmodel:select:"))
async def cb_model_select(callback: types.CallbackQuery):
    model_id = callback.data.split(":", 2)[2]
    user_settings = await advanced_ai_storage.get_agent_settings(callback.from_user.id)
    provider_key = (user_settings.get("provider") or settings.AI_ADVANCED_PROVIDER or "groq").lower()
    
    await advanced_ai_storage.update_agent_settings(
        callback.from_user.id,
        provider=provider_key,
        model=model_id
    )
    await callback.answer(f"✅ Model: {model_id[:30]}")
    await edit_main_menu(callback.message, callback.from_user.id)


# ─────────────────────────────────────────────────────────────────────────────
# Tool Commands
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("tools"))
async def cmd_tools(message: types.Message):
    """List available tools."""
    if not is_allowed(message.from_user.id):
        return
    text, markup = await get_tools_ui()
    await message.answer(text, parse_mode="HTML", reply_markup=markup)

@router.callback_query(F.data == "adv:tools")
async def cb_tools(callback: types.CallbackQuery):
    await callback.answer()
    text, markup = await get_tools_ui()
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=markup)

async def get_tools_ui():
    await advanced_ai_service.initialize()
    tools = advanced_ai_service.list_tools()

    text = (
        f"🔧 <b>Tools</b> • <b>{len(tools)}</b> total\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
    )

    if not tools:
        text += "\n<i>No tools are registered right now.</i>"
        builder = InlineKeyboardBuilder()
        builder.button(text="⬅️ Back", callback_data="adv:main")
        return text, builder.as_markup()

    # Group by category (based on prefix)
    categories = {}
    for tool in tools:
        name = tool.get("name", "")
        category = name.split("_", 1)[0] if "_" in name else "general"
        categories.setdefault(category, []).append(tool)

    for category in sorted(categories.keys()):
        cat_tools = sorted(categories[category], key=lambda t: t.get("name", ""))
        text += f"\n<b>{category.upper()}</b> <code>{len(cat_tools)}</code>\n"
        for t in cat_tools:
            name = _escape(t.get("name", ""))
            desc = _escape(_truncate(t.get("description", ""), 72))
            if desc:
                text += f"• <code>{name}</code> — {desc}\n"
            else:
                text += f"• <code>{name}</code>\n"

    text += "\n<i>Tools run automatically when they help.</i>"

    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Back", callback_data="adv:main")
    return text, builder.as_markup()


# ─────────────────────────────────────────────────────────────────────────────
# Skills Commands
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("skills"))
async def cmd_skills(message: types.Message):
    """List available Claude-style skills from SKILL.md files."""
    if not is_allowed(message.from_user.id):
        return
    text, markup = await get_skills_ui()
    await message.answer(text, parse_mode="HTML", reply_markup=markup)

@router.callback_query(F.data == "adv:skills")
async def cb_skills(callback: types.CallbackQuery):
    await callback.answer()
    text, markup = await get_skills_ui()
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=markup)

async def get_skills_ui():
    from app.services.ai.skills import skill_registry
    skill_registry.load_skills(reload=True)
    skills = skill_registry.get_skill_info()
    
    if not skills:
        text = (
            "📚 <b>Skills</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "<i>No skills found yet.</i>\n\n"
            "Create skills here:\n"
            "• <code>~/.ai/skills/skill-name/SKILL.md</code> (personal)\n"
            "• <code>.ai/skills/skill-name/SKILL.md</code> (project)\n\n"
            "Format:\n<pre>"
            "---\n"
            "name: Skill Name\n"
            "description: When to use this skill\n"
            "---\n"
            "\n# Instructions here\n"
            "</pre>"
        )
        builder = InlineKeyboardBuilder()
        builder.button(text="⬅️ Back", callback_data="adv:main")
        return text, builder.as_markup()

    text = (
        f"📚 <b>Skills</b> • <b>{len(skills)}</b> total\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Auto-matched to your message.</i>\n"
    )

    # Group by category
    by_category = {}
    for s in skills:
        cat = s.get("category", "custom")
        by_category.setdefault(cat, []).append(s)

    for category in sorted(by_category.keys()):
        cat_skills = sorted(by_category[category], key=lambda s: s.get("name", ""))
        text += f"\n<b>{category.upper()}</b> <code>{len(cat_skills)}</code>\n"
        for s in cat_skills:
            name = _escape(s.get("name", ""))
            desc = _escape(_truncate(s.get("description", ""), 72))
            if desc:
                text += f"• <b>{name}</b> — {desc}\n"
            else:
                text += f"• <b>{name}</b>\n"

    text += "\n<i>Add or update skills in your SKILL.md files.</i>"
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Back", callback_data="adv:main")
    return text, builder.as_markup()


# ─────────────────────────────────────────────────────────────────────────────
# Export
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("export"))
async def cmd_export(message: types.Message):
    if not is_allowed(message.from_user.id):
        return
    await do_export(message.from_user.id, message)

@router.callback_query(F.data == "adv:export")
async def cb_export(callback: types.CallbackQuery):
    await callback.answer("📤 Exporting...")
    await do_export(callback.from_user.id, callback.message, is_callback=True)

async def do_export(user_id: int, message: types.Message, is_callback: bool = False):
    await advanced_ai_service.initialize()
    user_settings = await advanced_ai_storage.get_agent_settings(user_id)
    provider_key = (user_settings.get("provider") or settings.AI_ADVANCED_PROVIDER or "groq").lower()
    model_name = user_settings.get("model")
    
    chats = await advanced_ai_storage.get_user_chats(user_id, 1)
    active_chat = next((c for c in chats if c.get("is_active")), None)
    
    if not active_chat:
        await message.answer("❌ No active chat to export")
        return
    
    status = await message.answer("📤 Exporting chat...")
    
    try:
        result = await advanced_ai_service.export_chat(
            user_id,
            active_chat["id"],
            provider_key=provider_key,
            model=model_name
        )
        
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


@router.message(Command("tool"))
async def cmd_tool_exec(message: types.Message, command: CommandObject):
    """Execute a tool directly."""
    if not is_allowed(message.from_user.id):
        return
    
    if not command.args:
        await message.answer(
            "Usage: /tool <tool_name> [args...]\n"
            "Example: /tool datetime action=now"
        )
        return
    
    await advanced_ai_service.initialize()
    
    parts = command.args.split()
    tool_name = parts[0]
    
    # Parse key=value arguments
    kwargs = {}
    for part in parts[1:]:
        if "=" in part:
            key, value = part.split("=", 1)
            # Try to parse as JSON for booleans/numbers
            try:
                import json
                kwargs[key] = json.loads(value)
            except:
                kwargs[key] = value
    
    status = await message.answer(f"⏳ Executing <code>{tool_name}</code>...", parse_mode="HTML")
    
    result = await advanced_ai_service.execute_tool(tool_name, **kwargs)
    
    if result.get("success"):
        import json
        output = result.get("output", "")
        if isinstance(output, (dict, list)):
            output = json.dumps(output, indent=2, default=str)[:3000]
        await status.edit_text(
            f"✅ <b>{tool_name}</b>\n\n<pre>{output}</pre>",
            parse_mode="HTML"
        )
    else:
        await status.edit_text(
            f"❌ <b>{tool_name}</b>\n\nError: {result.get('error')}",
            parse_mode="HTML"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Thinking Commands
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("think"))
async def cmd_think(message: types.Message, command: CommandObject):
    """Toggle extended thinking display."""
    if not is_allowed(message.from_user.id):
        return
    
    user_settings = await advanced_ai_storage.get_agent_settings(message.from_user.id)
    
    if command.args and command.args.strip().lower() in ["on", "off"]:
        new_value = command.args.strip().lower() == "on"
    else:
        new_value = not user_settings.get("show_thinking", True)
    
    await advanced_ai_storage.update_agent_settings(
        message.from_user.id,
        show_thinking=new_value
    )
    
    status = "enabled" if new_value else "disabled"
    await message.answer(f"🧠 Extended thinking display: <b>{status}</b>", parse_mode="HTML")


# ─────────────────────────────────────────────────────────────────────────────
# Status
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("status"))
async def cmd_status(message: types.Message):
    if not is_allowed(message.from_user.id):
        return
    await cmd_advstatus(message)

@router.message(Command("advstatus"))
async def cmd_advstatus(message: types.Message):
    """Show advanced AI status."""
    if not is_allowed(message.from_user.id):
        return
    
    await advanced_ai_service.initialize()
    status = advanced_ai_service.get_status()
    user_settings = await advanced_ai_storage.get_agent_settings(message.from_user.id)
    provider_key = (user_settings.get("provider") or settings.AI_ADVANCED_PROVIDER or "groq").lower()
    model_name = user_settings.get("model") or "default"
    providers = advanced_ai_service.list_providers()
    provider_info = next((p for p in providers if p["key"] == provider_key), None)
    supports_tools = provider_info["supports_tools"] if provider_info else status.get("supports_tools")
    supports_thinking = provider_info["supports_thinking"] if provider_info else status.get("supports_thinking")
    
    text = (
        "🚀 <b>Advanced AI Status</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔌 Provider: <b>{provider_key}</b>\n"
        f"📝 Model: <code>{model_name}</code>\n"
        f"🔧 Tools: <b>{status.get('tools_count', 0)}</b>\n"
        f"🤖 Agents: <b>{status.get('agents_count', 0)}</b>\n"
        f"⚙️ Tool Support: {'✅' if supports_tools else '❌'}\n"
        f"🧠 Thinking Support: {'✅' if supports_thinking else '❌'}\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Your Agent: <b>{user_settings.get('default_agent', 'chat')}</b>\n"
        f"🔄 Auto-Route: {'✅' if user_settings.get('auto_route') else '❌'}\n"
        f"🧠 Show Thinking: {'✅' if user_settings.get('show_thinking') else '❌'}\n"
    )
    
    await message.answer(text, parse_mode="HTML")

@router.message(Command("help"))
async def cmd_help(message: types.Message):
    if not is_allowed(message.from_user.id):
        return
    text = (
        "🚀 <b>Advanced AI Bot Commands</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "/start - Main menu\n"
        "/new - Start new chat\n"
        "/chats - List/switch chats\n"
        "/rename &lt;title&gt; - Rename chat\n"
        "/clear - Clear chat history\n"
        "/export - Export to GitHub\n"
        "/providers - Select provider\n"
        "/models - Select model\n"
        "/agent [name] - Select agent\n"
        "/tools - List tools\n"
        "/skills - List skills\n"
        "/tool - Execute a tool\n"
        "/think on|off - Toggle thinking display\n"
        "/ask &lt;message&gt; - Advanced chat\n"
        "/status - Bot status\n"
        "/help - This message"
    )
    await message.answer(text, parse_mode="HTML")


# ─────────────────────────────────────────────────────────────────────────────
# Advanced Chat Handler
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("ask"))
async def cmd_ask(message: types.Message, command: CommandObject):
    """Send a message to the advanced AI with agents."""
    if not is_allowed(message.from_user.id):
        return
    
    if not command.args:
        await message.answer("Usage: /ask <your message>")
        return
    
    await handle_advanced_chat(message, command.args)


async def handle_advanced_chat(message: types.Message, prompt: str):
    """Handle advanced chat with agents and tools."""
    await advanced_ai_service.initialize()
    
    user_settings = await advanced_ai_storage.get_agent_settings(message.from_user.id)
    agent_name = user_settings.get("default_agent", "chat")
    auto_route = user_settings.get("auto_route", False)
    show_thinking = user_settings.get("show_thinking", True)
    show_tool_calls = user_settings.get("show_tool_calls", True)
    provider_key = (user_settings.get("provider") or settings.AI_ADVANCED_PROVIDER or "groq").lower()
    model_name = user_settings.get("model")
    
    provider = advanced_ai_service.get_provider(provider_key)
    if not provider or not provider.is_configured():
        await message.answer("❌ Advanced AI provider is not configured")
        return
    
    # Load recent history before saving current prompt
    history = []
    active_chat = await advanced_ai_storage.get_or_create_active_chat(message.from_user.id)
    chat_id = active_chat.get("id") if active_chat else None
    if chat_id:
        recent = await advanced_ai_storage.get_chat_messages(chat_id, 4)
        history = [{"role": m["role"], "content": m["content"]} for m in reversed(recent)]
        msg_count = await advanced_ai_storage.get_message_count(chat_id)
        if msg_count == 0 and active_chat.get("title") == "New Chat":
            short_title = prompt[:40] + ("..." if len(prompt) > 40 else "")
            await advanced_ai_storage.rename_chat(chat_id, short_title)
        await advanced_ai_storage.save_message(chat_id, "user", prompt)
    
    status = await message.answer(f"🤔 <b>{agent_name}</b> is thinking...", parse_mode="HTML")
    
    try:
        result = await advanced_ai_service.chat(
            message=prompt,
            agent_name=agent_name if not auto_route else None,
            history=history,
            model=model_name,
            provider_key=provider_key,
            auto_route=auto_route
        )
        
        response_parts = []
        
        # Add thinking if enabled and present
        if show_thinking and result.get("thinking"):
            thinking = result["thinking"][:500] + "..." if len(result.get("thinking", "")) > 500 else result.get("thinking", "")
            response_parts.append(f"<blockquote>🧠 {thinking}</blockquote>")
        
        # Add tool calls if enabled
        if show_tool_calls and result.get("tool_calls"):
            tools_text = "🔧 Tools used: " + ", ".join(
                f"<code>{tc['name']}</code>" for tc in result["tool_calls"]
            )
            response_parts.append(tools_text)
        
        # Add main content
        content = result.get("content", "No response")
        if len(content) > 3500:
            content = content[:3500] + "\n\n...(truncated)"
        response_parts.append(content)
        
        full_response = "\n\n".join(response_parts)
        
        try:
            await status.edit_text(full_response, parse_mode="HTML")
        except:
            await status.edit_text(full_response)
        
        # Add footer with context
        metadata = result.get("metadata", {}) or {}
        agent_used = result.get("agent", agent_name)
        provider_used = metadata.get("provider", provider_key)
        model_used = metadata.get("model", model_name or "default")
        builder = InlineKeyboardBuilder()
        builder.button(text=f"🤖 {agent_used}", callback_data="adv:noop")
        builder.button(text="🔧 Tools", callback_data="adv:show_tools")
        builder.button(text="📤 Export", callback_data="adv:export")
        builder.adjust(2, 1)
        
        await message.answer(
            f"<code>{agent_used}</code> • <code>{provider_used}</code> • <code>{str(model_used)[:20]}</code>",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
        
        if chat_id and content:
            await advanced_ai_storage.save_message(chat_id, "assistant", content)
        
    except Exception as e:
        logger.error(f"Advanced chat error: {e}")
        await status.edit_text(f"❌ Error: {str(e)}")


@router.callback_query(F.data == "adv:noop")
async def cb_noop(callback: types.CallbackQuery):
    await callback.answer()


@router.callback_query(F.data == "adv:show_tools")
async def cb_show_tools(callback: types.CallbackQuery):
    await advanced_ai_service.initialize()
    tools = advanced_ai_service.list_tools()
    names = [t["name"] for t in tools[:15]]
    await callback.answer(f"Tools: {', '.join(names)}...", show_alert=True)


@router.message(F.text & ~F.text.startswith("/"))
async def handle_chat(message: types.Message):
    """Handle all text messages as advanced chat input."""
    if not is_allowed(message.from_user.id):
        return
    prompt = message.text
    if not prompt:
        return
    await handle_advanced_chat(message, prompt)
