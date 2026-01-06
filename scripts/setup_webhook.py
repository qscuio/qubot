import asyncio
import os
import sys
from aiogram import Bot

# Add project root to path
sys.path.append(os.getcwd())

from app.core.config import settings
from app.core.logger import Logger

logger = Logger("SetupWebhook")

async def setup():
    if not settings.WEBHOOK_URL:
        logger.error("WEBHOOK_URL not set in environment")
        return

    logger.info(f"Setting up webhooks for base URL: {settings.WEBHOOK_URL}")
    
    # Get secret and strip whitespace
    bot_secret = (settings.BOT_SECRET or "").strip() or None
    if bot_secret:
        logger.info(f"Using BOT_SECRET ({len(bot_secret)} chars)")
    else:
        logger.warn("No BOT_SECRET configured - webhooks will be unsecured!")

    bots = [
        ("monitor-bot", settings.MONITOR_BOT_TOKEN),
        ("ai-bot", settings.AI_BOT_TOKEN),
        ("rss-bot", settings.RSS_BOT_TOKEN)
    ]
    
    base_url = settings.WEBHOOK_URL.rstrip('/')

    for name, token in bots:
        if not token: 
            continue
            
        try:
            bot = Bot(token=token)
            webhook_url = f"{base_url}/webhook/{name}"
            # Delete old webhook first then set new one with secret
            await bot.delete_webhook(drop_pending_updates=True)
            await bot.set_webhook(webhook_url, drop_pending_updates=True, secret_token=bot_secret)
            logger.info(f"✅ Webhook set for {name}: {webhook_url}")
            await bot.session.close()
        except Exception as e:
            logger.error(f"Failed to set webhook for {name}", e)

if __name__ == "__main__":
    asyncio.run(setup())
