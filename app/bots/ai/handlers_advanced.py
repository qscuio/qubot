"""
Advanced AI Bot handlers for agent and tool features.
"""

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
    
    # List agents
    agents = advanced_ai_service.list_agents()
    user_settings = await advanced_ai_storage.get_agent_settings(message.from_user.id)
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
    
    await message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("adv:agent:"))
async def cb_agent_switch(callback: types.CallbackQuery):
    agent_name = callback.data.split(":")[2]
    await advanced_ai_storage.update_agent_settings(
        callback.from_user.id,
        default_agent=agent_name
    )
    await callback.answer(f"✅ Switched to {agent_name}")


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


# ─────────────────────────────────────────────────────────────────────────────
# Tool Commands
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("tools"))
async def cmd_tools(message: types.Message):
    """List available tools."""
    if not is_allowed(message.from_user.id):
        return
    
    await advanced_ai_service.initialize()
    tools = advanced_ai_service.list_tools()
    
    text = f"🔧 <b>Available Tools</b> ({len(tools)})\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    # Group by category (based on prefix)
    categories = {}
    for tool in tools:
        name = tool["name"]
        if "_" in name:
            category = name.split("_")[0]
        else:
            category = "general"
        
        if category not in categories:
            categories[category] = []
        categories[category].append(tool)
    
    for category, cat_tools in categories.items():
        text += f"<b>{category.upper()}</b>\n"
        for t in cat_tools:
            text += f"  • <code>{t['name']}</code>\n"
        text += "\n"
    
    await message.answer(text, parse_mode="HTML")


# ─────────────────────────────────────────────────────────────────────────────
# Skills Commands
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("skills"))
async def cmd_skills(message: types.Message):
    """List available Claude-style skills from SKILL.md files."""
    if not is_allowed(message.from_user.id):
        return
    
    from app.services.ai.skills import skill_registry
    skill_registry.load_skills(reload=True)
    skills = skill_registry.get_skill_info()
    
    if not skills:
        await message.answer(
            "📚 <b>No Skills Found</b>\n\n"
            "Create skills in:\n"
            "• <code>~/.ai/skills/skill-name/SKILL.md</code> (personal)\n"
            "• <code>.ai/skills/skill-name/SKILL.md</code> (project)\n\n"
            "Format:\n<pre>"
            "---\n"
            "name: Skill Name\n"
            "description: When to use this skill\n"
            "---\n"
            "\n# Instructions here\n"
            "</pre>",
            parse_mode="HTML"
        )
        return
    
    text = f"📚 <b>Available Skills</b> ({len(skills)})\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    # Group by category
    by_category = {}
    for s in skills:
        cat = s.get("category", "custom")
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(s)
    
    for category, cat_skills in by_category.items():
        text += f"<b>{category.upper()}</b>\n"
        for s in cat_skills:
            text += f"  • <b>{s['name']}</b>: {s['description'][:40]}...\n"
        text += "\n"
    
    text += "\n<i>Skills are auto-matched based on your message content.</i>"
    await message.answer(text, parse_mode="HTML")


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

@router.message(Command("advstatus"))
async def cmd_advstatus(message: types.Message):
    """Show advanced AI status."""
    if not is_allowed(message.from_user.id):
        return
    
    await advanced_ai_service.initialize()
    status = advanced_ai_service.get_status()
    user_settings = await advanced_ai_storage.get_agent_settings(message.from_user.id)
    
    text = (
        "🚀 <b>Advanced AI Status</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔌 Provider: <b>{status.get('provider', 'N/A')}</b>\n"
        f"🔧 Tools: <b>{status.get('tools_count', 0)}</b>\n"
        f"🤖 Agents: <b>{status.get('agents_count', 0)}</b>\n"
        f"⚙️ Tool Support: {'✅' if status.get('supports_tools') else '❌'}\n"
        f"🧠 Thinking Support: {'✅' if status.get('supports_thinking') else '❌'}\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Your Agent: <b>{user_settings.get('default_agent', 'chat')}</b>\n"
        f"🔄 Auto-Route: {'✅' if user_settings.get('auto_route') else '❌'}\n"
        f"🧠 Show Thinking: {'✅' if user_settings.get('show_thinking') else '❌'}\n"
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
    
    if not advanced_ai_service.is_available():
        await message.answer("❌ Advanced AI is not configured")
        return
    
    user_settings = await advanced_ai_storage.get_agent_settings(message.from_user.id)
    agent_name = user_settings.get("default_agent", "chat")
    auto_route = user_settings.get("auto_route", False)
    show_thinking = user_settings.get("show_thinking", True)
    show_tool_calls = user_settings.get("show_tool_calls", True)
    
    status = await message.answer(f"🤔 <b>{agent_name}</b> is thinking...", parse_mode="HTML")
    
    try:
        result = await advanced_ai_service.chat(
            message=prompt,
            agent_name=agent_name if not auto_route else None,
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
        agent_used = result.get("agent", agent_name)
        builder = InlineKeyboardBuilder()
        builder.button(text=f"🤖 {agent_used}", callback_data="adv:noop")
        builder.button(text="🔧 Tools", callback_data="adv:show_tools")
        
        await message.answer(
            f"<code>{agent_used}</code>",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
        
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
