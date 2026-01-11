"""
Vibe Remote Telegram Bot Handlers.

Provides commands for AI coding agents and Git/GitHub operations.
Uses aiogram Router pattern with inline keyboard UI.
"""

from aiogram import Router, F, types
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.config import settings
from app.core.logger import Logger
from app.services.vibe_remote.service import vibe_remote_service

router = Router()
logger = Logger("VibeBot")


def is_allowed(user_id: int) -> bool:
    """Check if user is allowed to use the bot."""
    allowed = getattr(settings, "ALLOWED_USERS", None)
    if not allowed:
        return True
    
    allowed_list = [int(x.strip()) for x in allowed.split(",") if x.strip()]
    return user_id in allowed_list


# =============================================================================
# UI Helper Functions
# =============================================================================

async def get_main_menu_ui(user_id: int, chat_id: int):
    """Build main menu UI with inline keyboard."""
    session = vibe_remote_service.get_session(user_id, chat_id)
    current_agent = session.agent if session else settings.VIBE_DEFAULT_AGENT
    cwd = session.working_path if session else "No session"
    
    # Get available agents
    available = vibe_remote_service.get_available_agents()
    agent_status = "✅" if available.get(current_agent, False) else "❌"
    
    text = (
        "🤖 <b>Vibe Remote Bot</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔧 Agent: <code>{current_agent}</code> {agent_status}\n"
        f"📁 Directory: <code>{cwd[:40]}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Send any message to chat with AI agent</i>"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🤖 Select Agent", callback_data="vibe:agents")
    builder.button(text="📁 Session Info", callback_data="vibe:session")
    builder.button(text="🔧 Git Ops", callback_data="vibe:git")
    builder.button(text="🚀 Actions", callback_data="vibe:actions_menu")
    builder.button(text="🔄 Refresh", callback_data="vibe:refresh")
    builder.button(text="ℹ️ Help", callback_data="vibe:help")
    builder.adjust(2, 2, 2)
    
    return text, builder.as_markup()


async def get_agents_ui(user_id: int, chat_id: int):
    """Build agent selection UI."""
    session = vibe_remote_service.get_session(user_id, chat_id)
    current_agent = session.agent if session else settings.VIBE_DEFAULT_AGENT
    available = vibe_remote_service.get_available_agents()
    
    text = (
        "🤖 <b>Select AI Agent</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"Current: <code>{current_agent}</code>\n"
    )
    
    builder = InlineKeyboardBuilder()
    for name, is_avail in available.items():
        emoji = "✅" if name == current_agent else "🤖"
        status = "" if is_avail else " (unavailable)"
        builder.button(text=f"{emoji} {name.capitalize()}{status}", callback_data=f"agent:select:{name}")
    
    builder.adjust(1)
    kb = builder.as_markup()
    kb.inline_keyboard.append([
        types.InlineKeyboardButton(text="◀️ Back", callback_data="vibe:main")
    ])
    
    return text, kb


async def get_session_ui(user_id: int, chat_id: int):
    """Build session info UI."""
    session = vibe_remote_service.get_session(user_id, chat_id)
    
    if not session:
        text = (
            "📊 <b>Session Info</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "❌ No active session\n\n"
            "<i>Send a message with /vibe to start</i>"
        )
    else:
        text = (
            "📊 <b>Session Info</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 Agent: <code>{session.agent}</code>\n"
            f"📁 CWD: <code>{session.working_path}</code>\n"
            f"🕒 Last activity: {session.last_activity.strftime('%H:%M:%S')}\n"
        )
    
    builder = InlineKeyboardBuilder()
    if session:
        builder.button(text="🗑 Clear Session", callback_data="session:clear")
        builder.button(text="⏹ Stop Task", callback_data="session:stop")
    builder.button(text="◀️ Back", callback_data="vibe:main")
    builder.adjust(2, 1)
    
    return text, builder.as_markup()


async def get_git_menu_ui(user_id: int, chat_id: int):
    """Build git operations menu."""
    session = vibe_remote_service.get_session(user_id, chat_id)
    
    if not session:
        text = "🔧 <b>Git Operations</b>\n\n❌ No active session"
        builder = InlineKeyboardBuilder()
        builder.button(text="◀️ Back", callback_data="vibe:main")
        return text, builder.as_markup()
    
    # Check if we're in a git repo
    is_repo, _ = vibe_remote_service.git.is_git_repository(session.working_path)
    branch = vibe_remote_service.git.get_current_branch(session.working_path) if is_repo else None
    
    text = (
        "🔧 <b>Git Operations</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"📁 <code>{session.working_path[:35]}</code>\n"
    )
    
    if is_repo and branch:
        text += f"🌿 Branch: <code>{branch}</code>\n"
    else:
        text += "⚠️ Not a git repository\n"
    
    builder = InlineKeyboardBuilder()
    if is_repo:
        builder.button(text="📊 Status", callback_data="git:status")
        builder.button(text="⬆️ Push", callback_data="git:push")
        builder.button(text="⬇️ Pull", callback_data="git:pull")
        builder.button(text="🌿 Branches", callback_data="git:branches")
        builder.adjust(2, 2)
    
    kb = builder.as_markup()
    kb.inline_keyboard.append([
        types.InlineKeyboardButton(text="◀️ Back", callback_data="vibe:main")
    ])
    
    return text, kb


# =============================================================================
# Main Menu & Navigation
# =============================================================================

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    """Handle /start command with main menu."""
    if not is_allowed(message.from_user.id):
        await message.answer("⛔ You are not authorized to use this bot.")
        return
    
    text, markup = await get_main_menu_ui(message.from_user.id, message.chat.id)
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "vibe:main")
async def cb_main(callback: types.CallbackQuery):
    """Return to main menu."""
    await callback.answer()
    text, markup = await get_main_menu_ui(callback.from_user.id, callback.message.chat.id)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "vibe:refresh")
async def cb_refresh(callback: types.CallbackQuery):
    """Refresh main menu."""
    await callback.answer("🔄 Refreshed")
    text, markup = await get_main_menu_ui(callback.from_user.id, callback.message.chat.id)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except:
        pass


@router.callback_query(F.data == "vibe:help")
async def cb_help(callback: types.CallbackQuery):
    """Show help message."""
    await callback.answer()
    help_text = (
        "ℹ️ <b>Vibe Remote Bot Help</b>\n\n"
        "<b>💬 Chat with AI:</b>\n"
        "Just send a message directly!\n\n"
        "<b>🔧 Commands:</b>\n"
        "• /vibe &lt;msg&gt; - Send to AI\n"
        "• /agent [name] - Switch agent\n"
        "• /cwd [path] - Set directory\n"
        "• /clone &lt;url&gt; - Clone repo\n"
        "• /status - Git status\n"
        "• /commit &lt;msg&gt; - Commit\n"
        "• /push, /pull - Git sync\n"
        "• /stop - Stop task\n"
        "• /clear - Clear session"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Back", callback_data="vibe:main")
    
    try:
        await callback.message.edit_text(help_text, parse_mode="HTML", reply_markup=builder.as_markup())
    except:
        await callback.message.answer(help_text, parse_mode="HTML", reply_markup=builder.as_markup())


# =============================================================================
# Agent Selection
# =============================================================================

@router.callback_query(F.data == "vibe:agents")
async def cb_agents(callback: types.CallbackQuery):
    """Show agent selection menu."""
    await callback.answer()
    text, markup = await get_agents_ui(callback.from_user.id, callback.message.chat.id)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data.startswith("agent:select:"))
async def cb_agent_select(callback: types.CallbackQuery):
    """Handle agent selection."""
    agent_name = callback.data.split(":")[-1]
    
    if vibe_remote_service.set_agent(callback.from_user.id, callback.message.chat.id, agent_name):
        await callback.answer(f"✅ Switched to {agent_name}")
        text, markup = await get_main_menu_ui(callback.from_user.id, callback.message.chat.id)
        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
        except:
            pass
    else:
        await callback.answer(f"❌ Agent {agent_name} not available", show_alert=True)


# =============================================================================
# Session Management
# =============================================================================

@router.callback_query(F.data == "vibe:session")
async def cb_session(callback: types.CallbackQuery):
    """Show session info."""
    await callback.answer()
    text, markup = await get_session_ui(callback.from_user.id, callback.message.chat.id)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "session:clear")
async def cb_session_clear(callback: types.CallbackQuery):
    """Clear session."""
    if await vibe_remote_service.clear_session(callback.from_user.id, callback.message.chat.id):
        await callback.answer("🗑 Session cleared")
        text, markup = await get_main_menu_ui(callback.from_user.id, callback.message.chat.id)
        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
        except:
            pass
    else:
        await callback.answer("No session to clear")


@router.callback_query(F.data == "session:stop")
async def cb_session_stop(callback: types.CallbackQuery):
    """Stop current task."""
    if await vibe_remote_service.handle_stop(callback.from_user.id, callback.message.chat.id):
        await callback.answer("⏹ Task stopped")
    else:
        await callback.answer("No running task")


# =============================================================================
# Git Operations UI
# =============================================================================

@router.callback_query(F.data == "vibe:git")
async def cb_git_menu(callback: types.CallbackQuery):
    """Show git operations menu."""
    await callback.answer()
    text, markup = await get_git_menu_ui(callback.from_user.id, callback.message.chat.id)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "git:status")
async def cb_git_status(callback: types.CallbackQuery):
    """Show git status."""
    await callback.answer()
    
    session = vibe_remote_service.get_session(callback.from_user.id, callback.message.chat.id)
    if not session:
        await callback.answer("No active session", show_alert=True)
        return
    
    success, output = vibe_remote_service.git.status(session.working_path)
    if success:
        branch = vibe_remote_service.git.get_current_branch(session.working_path) or "?"
        await callback.message.answer(
            f"📊 <b>Git Status</b> (<code>{branch}</code>):\n<pre>{output[:1500]}</pre>",
            parse_mode="HTML"
        )
    else:
        await callback.message.answer(f"❌ Error:\n{output[:500]}")


@router.callback_query(F.data == "git:push")
async def cb_git_push(callback: types.CallbackQuery):
    """Push to remote."""
    await callback.answer("⏳ Pushing...")
    
    session = vibe_remote_service.get_session(callback.from_user.id, callback.message.chat.id)
    if not session:
        await callback.answer("No active session", show_alert=True)
        return
    
    success, output = vibe_remote_service.git.push(session.working_path, False)
    if success:
        await callback.message.answer("✅ Pushed successfully")
    else:
        await callback.message.answer(f"❌ Push failed:\n<pre>{output[:1000]}</pre>", parse_mode="HTML")


@router.callback_query(F.data == "git:pull")
async def cb_git_pull(callback: types.CallbackQuery):
    """Pull from remote."""
    await callback.answer("⏳ Pulling...")
    
    session = vibe_remote_service.get_session(callback.from_user.id, callback.message.chat.id)
    if not session:
        await callback.answer("No active session", show_alert=True)
        return
    
    success, output = vibe_remote_service.git.pull(session.working_path)
    if success:
        await callback.message.answer(f"✅ {output or 'Already up to date'}")
    else:
        await callback.message.answer(f"❌ Pull failed:\n<pre>{output[:1000]}</pre>", parse_mode="HTML")


@router.callback_query(F.data == "git:branches")
async def cb_git_branches(callback: types.CallbackQuery):
    """List branches."""
    await callback.answer()
    
    session = vibe_remote_service.get_session(callback.from_user.id, callback.message.chat.id)
    if not session:
        await callback.answer("No active session", show_alert=True)
        return
    
    success, output = vibe_remote_service.git.branch(session.working_path)
    if success:
        await callback.message.answer(f"🌿 <b>Branches:</b>\n<pre>{output[:1500]}</pre>", parse_mode="HTML")
    else:
        await callback.message.answer(f"❌ Error:\n{output[:500]}")


@router.callback_query(F.data == "vibe:actions_menu")
async def cb_actions_menu(callback: types.CallbackQuery):
    """Show GitHub Actions menu."""
    await callback.answer()
    
    text = (
        "🚀 <b>GitHub Actions</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Use commands for actions:\n\n"
        "• /actions &lt;repo&gt; - List runs\n"
        "• /trigger &lt;repo&gt; &lt;workflow&gt;\n"
        "• /logs &lt;repo&gt; &lt;run_id&gt;"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Back", callback_data="vibe:main")
    
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    except:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())


# =============================================================================
# Command Handlers (kept for compatibility)
# =============================================================================

@router.message(Command("help"))
async def cmd_help(message: types.Message):
    """Handle /help command."""
    await cmd_start(message)


@router.message(Command("vibe"))
async def cmd_vibe(message: types.Message, command: CommandObject):
    """Handle /vibe command - send message to AI agent."""
    if not is_allowed(message.from_user.id):
        return
    
    if not command.args:
        await message.answer("Usage: <code>/vibe &lt;your message&gt;</code>", parse_mode="HTML")
        return
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    status = await message.answer("⏳ Processing...")
    
    async def reply_callback(text: str) -> None:
        try:
            await message.answer(text[:4000], parse_mode="Markdown")
        except Exception:
            try:
                await message.answer(text[:4000])
            except Exception as e:
                logger.error(f"Failed to send reply: {e}")
    
    await vibe_remote_service.handle_message(user_id, chat_id, command.args, reply_callback)
    
    try:
        await status.delete()
    except Exception:
        pass
    
    # Show quick actions
    builder = InlineKeyboardBuilder()
    builder.button(text="🏠 Main Menu", callback_data="vibe:main")
    await message.answer("─────────", reply_markup=builder.as_markup())


@router.message(Command("agent"))
async def cmd_agent(message: types.Message, command: CommandObject):
    """Handle /agent command - switch or show current agent."""
    if not is_allowed(message.from_user.id):
        return
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if not command.args:
        text, markup = await get_agents_ui(user_id, chat_id)
        await message.answer(text, parse_mode="HTML", reply_markup=markup)
        return
    
    agent_name = command.args.lower().strip()
    if vibe_remote_service.set_agent(user_id, chat_id, agent_name):
        await message.answer(f"✅ Switched to <code>{agent_name}</code> agent", parse_mode="HTML")
    else:
        await message.answer(f"❌ Unknown agent: <code>{agent_name}</code>", parse_mode="HTML")


@router.message(Command("cwd"))
async def cmd_cwd(message: types.Message, command: CommandObject):
    """Handle /cwd command - show or set working directory."""
    if not is_allowed(message.from_user.id):
        return
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if not command.args:
        session = vibe_remote_service.get_session(user_id, chat_id)
        if session:
            await message.answer(f"📁 Current directory: <code>{session.working_path}</code>", parse_mode="HTML")
        else:
            await message.answer("No active session. Send a message with /vibe first.")
        return
    
    path = command.args
    if vibe_remote_service.set_cwd(user_id, chat_id, path):
        await message.answer(f"✅ Working directory set to: <code>{path}</code>", parse_mode="HTML")
    else:
        await message.answer(f"❌ Failed to set directory: <code>{path}</code>", parse_mode="HTML")


@router.message(Command("stop"))
async def cmd_stop(message: types.Message):
    """Handle /stop command - stop current task."""
    if not is_allowed(message.from_user.id):
        return
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if await vibe_remote_service.handle_stop(user_id, chat_id):
        await message.answer("⏹ Task stopped")
    else:
        await message.answer("No running task to stop")


@router.message(Command("clear"))
async def cmd_clear(message: types.Message):
    """Handle /clear command - clear session."""
    if not is_allowed(message.from_user.id):
        return
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if await vibe_remote_service.clear_session(user_id, chat_id):
        await message.answer("🗑 Session cleared")
    else:
        await message.answer("No session to clear")


# =============================================================================
# Git Commands
# =============================================================================

@router.message(Command("clone"))
async def cmd_clone(message: types.Message, command: CommandObject):
    """Handle /clone command."""
    if not is_allowed(message.from_user.id):
        return
    
    import os
    
    if not command.args:
        await message.answer("Usage: <code>/clone &lt;repo_url&gt;</code>", parse_mode="HTML")
        return
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    repo_url = command.args.strip()
    
    session = vibe_remote_service.session_manager.get_or_create_session(user_id, chat_id)
    repo_name = repo_url.split("/")[-1].replace(".git", "")
    target_dir = os.path.join(session.working_path, repo_name)
    
    status = await message.answer(f"⏳ Cloning <code>{repo_name}</code>...", parse_mode="HTML")
    
    success, output = vibe_remote_service.git.clone(repo_url, target_dir)
    if success:
        vibe_remote_service.set_cwd(user_id, chat_id, target_dir)
        await status.edit_text(f"✅ Cloned to <code>{target_dir}</code>", parse_mode="HTML")
    else:
        await status.edit_text(f"❌ Clone failed:\n<pre>{output[:1000]}</pre>", parse_mode="HTML")


@router.message(Command("status"))
async def cmd_status(message: types.Message):
    """Handle /status command - git status."""
    if not is_allowed(message.from_user.id):
        return
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    session = vibe_remote_service.get_session(user_id, chat_id)
    if not session:
        await message.answer("No active session")
        return
    
    success, output = vibe_remote_service.git.status(session.working_path)
    if success:
        branch = vibe_remote_service.git.get_current_branch(session.working_path) or "?"
        await message.answer(f"📊 <b>Git Status</b> (<code>{branch}</code>):\n<pre>{output[:1500]}</pre>", parse_mode="HTML")
    else:
        await message.answer(f"❌ Not a git repository or error:\n{output[:500]}")


@router.message(Command("commit"))
async def cmd_commit(message: types.Message, command: CommandObject):
    """Handle /commit command."""
    if not is_allowed(message.from_user.id):
        return
    
    if not command.args:
        await message.answer("Usage: <code>/commit &lt;message&gt;</code>", parse_mode="HTML")
        return
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    session = vibe_remote_service.get_session(user_id, chat_id)
    if not session:
        await message.answer("No active session")
        return
    
    success, output = vibe_remote_service.git.commit(session.working_path, command.args)
    if success:
        await message.answer(f"✅ Committed: <code>{command.args[:50]}</code>", parse_mode="HTML")
    else:
        await message.answer(f"❌ Commit failed:\n<pre>{output[:1000]}</pre>", parse_mode="HTML")


@router.message(Command("push"))
async def cmd_push(message: types.Message, command: CommandObject):
    """Handle /push command."""
    if not is_allowed(message.from_user.id):
        return
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    session = vibe_remote_service.get_session(user_id, chat_id)
    if not session:
        await message.answer("No active session")
        return
    
    force = command.args and "-f" in command.args
    
    status = await message.answer("⏳ Pushing...")
    success, output = vibe_remote_service.git.push(session.working_path, force)
    if success:
        await status.edit_text("✅ Pushed successfully")
    else:
        await status.edit_text(f"❌ Push failed:\n<pre>{output[:1000]}</pre>", parse_mode="HTML")


@router.message(Command("pull"))
async def cmd_pull(message: types.Message):
    """Handle /pull command."""
    if not is_allowed(message.from_user.id):
        return
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    session = vibe_remote_service.get_session(user_id, chat_id)
    if not session:
        await message.answer("No active session")
        return
    
    status = await message.answer("⏳ Pulling...")
    success, output = vibe_remote_service.git.pull(session.working_path)
    if success:
        await status.edit_text(f"✅ {output or 'Already up to date'}")
    else:
        await status.edit_text(f"❌ Pull failed:\n<pre>{output[:1000]}</pre>", parse_mode="HTML")


@router.message(Command("merge"))
async def cmd_merge(message: types.Message, command: CommandObject):
    """Handle /merge command."""
    if not is_allowed(message.from_user.id):
        return
    
    if not command.args:
        await message.answer("Usage: <code>/merge &lt;branch&gt;</code>", parse_mode="HTML")
        return
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    branch = command.args.strip()
    
    session = vibe_remote_service.get_session(user_id, chat_id)
    if not session:
        await message.answer("No active session")
        return
    
    success, output = vibe_remote_service.git.merge(session.working_path, branch)
    if success:
        await message.answer(f"✅ Merged <code>{branch}</code>", parse_mode="HTML")
    else:
        await message.answer(f"❌ Merge failed:\n<pre>{output[:1000]}</pre>", parse_mode="HTML")


@router.message(Command("branch"))
async def cmd_branch(message: types.Message, command: CommandObject):
    """Handle /branch command."""
    if not is_allowed(message.from_user.id):
        return
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    session = vibe_remote_service.get_session(user_id, chat_id)
    if not session:
        await message.answer("No active session")
        return
    
    if not command.args:
        success, output = vibe_remote_service.git.branch(session.working_path)
        if success:
            await message.answer(f"🌿 <b>Branches:</b>\n<pre>{output[:1500]}</pre>", parse_mode="HTML")
        else:
            await message.answer(f"❌ Error:\n{output[:500]}")
    else:
        branch_name = command.args.strip()
        success, output = vibe_remote_service.git.branch(session.working_path, branch_name)
        if success:
            await message.answer(f"✅ Created and switched to <code>{branch_name}</code>", parse_mode="HTML")
        else:
            await message.answer(f"❌ Failed:\n{output[:500]}")


# =============================================================================
# GitHub Actions Commands
# =============================================================================

@router.message(Command("actions"))
async def cmd_actions(message: types.Message, command: CommandObject):
    """Handle /actions command - list workflow runs."""
    if not is_allowed(message.from_user.id):
        return
    
    if not command.args:
        await message.answer("Usage: <code>/actions &lt;owner/repo&gt;</code>", parse_mode="HTML")
        return
    
    repo = command.args.strip()
    runs = vibe_remote_service.github_actions.list_runs(repo, limit=5)
    
    if not runs:
        await message.answer("❌ No runs found or GitHub API unavailable")
        return
    
    lines = [f"<b>Recent runs for <code>{repo}</code>:</b>\n"]
    for run in runs:
        emoji = "✅" if run["conclusion"] == "success" else "❌" if run["conclusion"] == "failure" else "⏳"
        lines.append(f"{emoji} <code>{run['id']}</code> {run['name']} ({run['status']})")
    
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("trigger"))
async def cmd_trigger(message: types.Message, command: CommandObject):
    """Handle /trigger command - trigger workflow."""
    if not is_allowed(message.from_user.id):
        return
    
    args = command.args.split() if command.args else []
    if len(args) < 2:
        await message.answer("Usage: <code>/trigger &lt;owner/repo&gt; &lt;workflow_file&gt;</code>", parse_mode="HTML")
        return
    
    repo, workflow = args[0], args[1]
    
    result = vibe_remote_service.github_actions.trigger_workflow(repo, workflow)
    if result:
        await message.answer(f"✅ Triggered <code>{workflow}</code> on <code>{repo}</code>", parse_mode="HTML")
    else:
        await message.answer("❌ Failed to trigger workflow")


@router.message(Command("logs"))
async def cmd_logs(message: types.Message, command: CommandObject):
    """Handle /logs command - get workflow logs."""
    if not is_allowed(message.from_user.id):
        return
    
    args = command.args.split() if command.args else []
    if len(args) < 2:
        await message.answer("Usage: <code>/logs &lt;owner/repo&gt; &lt;run_id&gt;</code>", parse_mode="HTML")
        return
    
    repo = args[0]
    try:
        run_id = int(args[1])
    except ValueError:
        await message.answer("❌ Invalid run ID")
        return
    
    logs = vibe_remote_service.github_actions.get_run_logs(repo, run_id)
    if logs:
        await message.answer(f"<b>Logs for run <code>{run_id}</code>:</b>\n\n<pre>{logs[:3000]}</pre>", parse_mode="HTML")
    else:
        await message.answer("❌ Failed to get logs")


# =============================================================================
# Message Handler (catch-all for direct AI chat)
# =============================================================================

@router.message(F.text & ~F.text.startswith("/"))
async def handle_message(message: types.Message):
    """Handle direct messages as AI agent chat."""
    if not is_allowed(message.from_user.id):
        return
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    status = await message.answer("⏳ Processing...")
    
    async def reply_callback(text: str) -> None:
        try:
            await message.answer(text[:4000], parse_mode="Markdown")
        except Exception:
            try:
                await message.answer(text[:4000])
            except Exception as e:
                logger.error(f"Failed to send reply: {e}")
    
    await vibe_remote_service.handle_message(user_id, chat_id, message.text, reply_callback)
    
    try:
        await status.delete()
    except Exception:
        pass
    
    # Show quick actions after AI response
    builder = InlineKeyboardBuilder()
    builder.button(text="🏠 Menu", callback_data="vibe:main")
    builder.button(text="⏹ Stop", callback_data="session:stop")
    builder.adjust(2)
    await message.answer("─────────", reply_markup=builder.as_markup())
