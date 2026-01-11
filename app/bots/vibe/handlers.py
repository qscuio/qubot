"""
Vibe Remote Telegram Bot Handlers.

Provides commands for AI coding agents and Git/GitHub operations.
Uses aiogram Router pattern consistent with other qubot bots.
"""

from aiogram import Router, F, types
from aiogram.filters import Command, CommandObject

from app.core.config import settings
from app.core.logger import Logger
from app.services.vibe_remote.service import vibe_remote_service

router = Router()
logger = Logger("VibeBot")


def is_allowed(user_id: int) -> bool:
    """Check if user is allowed to use the bot."""
    allowed = getattr(settings, "VIBE_ALLOWED_USERS", None)
    if not allowed:
        return True
    
    allowed_list = [int(x.strip()) for x in allowed.split(",") if x.strip()]
    return user_id in allowed_list


# =============================================================================
# Agent Commands
# =============================================================================

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    """Handle /start command."""
    if not is_allowed(message.from_user.id):
        await message.answer("⛔ You are not authorized to use this bot.")
        return
    
    welcome = (
        "🚀 <b>Vibe Remote Bot</b>\n\n"
        "<b>Agent Commands:</b>\n"
        "• /vibe &lt;msg&gt; - Send to AI agent\n"
        "• /agent [name] - Switch agent (claude/gemini/codex)\n"
        "• /cwd [path] - Show/set working directory\n"
        "• /stop - Stop current task\n"
        "• /clear - Clear session\n\n"
        "<b>Git Commands:</b>\n"
        "• /clone &lt;url&gt; - Clone repository\n"
        "• /status - Git status\n"
        "• /commit &lt;msg&gt; - Commit changes\n"
        "• /push, /pull - Push/pull\n"
        "• /merge &lt;branch&gt; - Merge\n"
        "• /branch [name] - List/create branch\n\n"
        "<b>GitHub Actions:</b>\n"
        "• /actions &lt;repo&gt; - List runs\n"
        "• /trigger &lt;repo&gt; &lt;workflow&gt; - Trigger\n"
        "• /logs &lt;repo&gt; &lt;run_id&gt; - Get logs"
    )
    await message.answer(welcome, parse_mode="HTML")


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


@router.message(Command("agent"))
async def cmd_agent(message: types.Message, command: CommandObject):
    """Handle /agent command - switch or show current agent."""
    if not is_allowed(message.from_user.id):
        return
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if not command.args:
        session = vibe_remote_service.get_session(user_id, chat_id)
        current = session.agent if session else "gemini"
        available = vibe_remote_service.get_available_agents()
        
        lines = [f"<b>Current agent:</b> <code>{current}</code>\n\n<b>Available agents:</b>"]
        for name, is_avail in available.items():
            emoji = "✅" if is_avail else "❌"
            lines.append(f"  {emoji} <code>{name}</code>")
        
        await message.answer("\n".join(lines), parse_mode="HTML")
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
