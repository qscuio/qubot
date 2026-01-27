import asyncio

from aiogram import Router, types
from aiogram.filters import Command, CommandObject

from app.core.logger import Logger
from app.core.config import settings
from app.services.history_service import history_service
from app.bots.crawler.routers.common import is_allowed, safe_edit_text

logger = Logger("FileBot")

router = Router()


@router.message(Command("start"))
@router.message(Command("help"))
async def cmd_help(message: types.Message):
    if not await is_allowed(message.from_user.id):
        return

    current_target = settings.FILE_TARGET_GROUP or "未设置"
    text = (
        "📼 <b>File Bot</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "/fv - 转发历史视频\n"
        "/fv_target - 设置视频转发目标\n\n"
        f"当前目标: {current_target}\n"
        "示例: /fv_target -1001234567890"
    )
    await message.answer(text, parse_mode="HTML")


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
