"""
Ping Router

Handles the /ping command to send random emojis to a target.
"""

import asyncio
import random
from aiogram import Router, types
from aiogram.filters import Command, CommandObject
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter

from .common import is_allowed, logger

router = Router()

# ... (emojis list remains the same) ...

@router.message(Command("ping"))
async def cmd_ping(message: types.Message, command: CommandObject):
    """
    Send a random emoji to the target every 3 seconds for 1 minute.
    Usage: /ping <target_id>
    """
    if not await is_allowed(message.from_user.id):
        return

    if not command.args:
        await message.answer("Usage: /ping <target_id>")
        return

    target_id = command.args.strip()
    
    # Validate target_id (basic check)
    try:
        target_int = int(target_id)
    except ValueError:
        await message.answer("Invalid target ID. Please provide a numeric ID.")
        return

    await message.answer(f"🚀 Starting ping to {target_id} (interval: 3s)...")

    try:
        # Send 20 messages (approx 1 minute with 3s interval)
        for i in range(20):
            emoji = random.choice(EMOJIS)
            try:
                await message.bot.send_message(chat_id=target_int, text=emoji)
            except TelegramForbiddenError:
                await message.answer(f"❌ Forbidden: Cannot send message to {target_id}. Bot might be blocked or not a member.")
                break
            except TelegramBadRequest as e:
                await message.answer(f"❌ Bad Request: {e}")
                break
            except TelegramRetryAfter as e:
                logger.warning(f"Flood limit hit. Sleeping for {e.retry_after} seconds.")
                await asyncio.sleep(e.retry_after)
                # Retry once
                try:
                    await message.bot.send_message(chat_id=target_int, text=emoji)
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"Ping error: {e}")
            
            await asyncio.sleep(3)
        
        await message.answer("✅ Ping finished.")

    except Exception as e:
        logger.error(f"Ping loop error: {e}")
        await message.answer(f"❌ Error during ping: {e}")
