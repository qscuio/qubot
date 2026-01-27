"""
History Router

Handles chat history operations: saving, retrieving, and forwarding videos.
"""

import asyncio

from aiogram import Router, F, types
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.services.history_service import history_service
from app.core.config import settings

from .common import is_allowed, safe_answer, safe_edit_text, logger

router = Router()


# ─────────────────────────────────────────────────────────────────────────────
# Forward Videos
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("forward_videos"))
@router.message(Command("fv"))
async def cmd_forward_videos(message: types.Message, command: CommandObject):
    """Forward videos from a source chat."""
    if not await is_allowed(message.from_user.id):
        return

    args = command.args
    if not args:
        await message.answer("用法: /fv <source_id_or_username>")
        return

    source = args.strip()
    status = await message.answer(f"⏳ 正在从 {source} 转发视频...")

    async def run_forward():
        try:
            logger.info(f"Task started: forward_history_videos from {source}")
            result = await history_service.forward_history_videos(source)
            if result.get("status") == "ok":
                await status.edit_text(
                    f"✅ 转发完成\n"
                    f"源: {source}\n"
                    f"目标: {result['target']}\n"
                    f"扫描: {result['scanned']}\n"
                    f"转发: {result['forwarded']}"
                )
                logger.info(f"Task completed: forward_history_videos from {source}")
            else:
                error_msg = result.get('message', 'Unknown error')
                await status.edit_text(f"❌ 失败: {error_msg}")
                logger.error(f"Task failed: forward_history_videos from {source} - {error_msg}")
        except Exception as e:
            logger.error(f"Task crashed: forward_history_videos from {source} - {e}", exc_info=True)
            await safe_edit_text(status, f"❌ 任务崩溃: {str(e)}")

    asyncio.create_task(run_forward())


# ─────────────────────────────────────────────────────────────────────────────
# Forward Videos Target
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("fv_target"))
async def cmd_fv_target(message: types.Message, command: CommandObject):
    """Set target channel/group for forward videos."""
    if not await is_allowed(message.from_user.id):
        return

    args = command.args
    current_target = settings.FILE_TARGET_GROUP or "未设置"

    if not args:
        await message.answer(
            "用法: /fv_target <target_id_or_username>\n"
            f"当前目标: {current_target}\n"
            "示例: /fv_target -1001234567890 或 /fv_target @channelname"
        )
        return

    target = args.strip()
    if target.lower() in ("none", "off", "clear"):
        settings.FILE_TARGET_GROUP = None
        await message.answer("✅ 已清空 forward_videos 目标 (FILE_TARGET_GROUP).")
        return

    settings.FILE_TARGET_GROUP = target
    await message.answer(
        "✅ 已更新 forward_videos 目标\n"
        f"目标: {target}\n"
        "提示: 重启后会恢复为环境变量 FILE_TARGET_GROUP 的值"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Save History
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("save_history"))
async def cmd_save_history(message: types.Message, command: CommandObject):
    """Save chat history from a source."""
    if not await is_allowed(message.from_user.id):
        return

    args = command.args
    if not args:
        await message.answer("用法: /save_history <source_id_or_username>")
        return

    source = args.strip()
    status = await message.answer(f"⏳ 正在保存 {source} 的聊天记录...")

    async def run_save():
        try:
            logger.info(f"Task started: fetch_and_save_history from {source}")
            result = await history_service.fetch_and_save_history(source)
            if result.get("status") == "ok":
                await status.edit_text(
                    f"✅ 保存完成\n"
                    f"源: {source}\n"
                    f"扫描: {result['scanned']}\n"
                    f"保存: {result['saved']}"
                )
                logger.info(f"Task completed: fetch_and_save_history from {source}")
            else:
                error_msg = result.get('message', 'Unknown error')
                await status.edit_text(f"❌ 失败: {error_msg}")
                logger.error(f"Task failed: fetch_and_save_history from {source} - {error_msg}")
        except Exception as e:
            logger.error(f"Task crashed: fetch_and_save_history from {source} - {e}", exc_info=True)
            await safe_edit_text(status, f"❌ 任务崩溃: {str(e)}")

    asyncio.create_task(run_save())


# ─────────────────────────────────────────────────────────────────────────────
# Get History
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("get_history"))
async def cmd_get_history(message: types.Message, command: CommandObject):
    """Get chat history from database."""
    if not await is_allowed(message.from_user.id):
        return

    args = command.args
    if not args:
        await message.answer("用法: /get_history <source_id_or_username> [limit]")
        return

    parts = args.split()
    source = parts[0]
    limit = int(parts[1]) if len(parts) > 1 else 10

    history = await history_service.get_chat_history(source, limit)

    if not history:
        await message.answer(f"📭 {source} 没有找到记录")
        return

    text = f"📋 <b>{source} 历史记录</b> ({len(history)})\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    for msg in history:
        sender = msg.get('sender_name') or msg.get('sender_id') or "?"
        content = msg.get('text') or f"[{msg.get('media_type')}]"
        date = msg.get('created_at').strftime("%Y-%m-%d %H:%M")
        text += f"<b>{sender}</b> ({date}):\n{content[:100]}\n\n"

    # Split if too long
    if len(text) > 4000:
        text = text[:4000] + "\n...(truncated)"

    await message.answer(text, parse_mode="HTML")
