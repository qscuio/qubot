from aiogram import Bot

from app.bots.bot_spec import BotSpec
from app.core.config import settings
from app.core.logger import Logger

logger = Logger("WebhookSetup")


async def setup_webhook_for_bot(spec: BotSpec) -> None:
    base_url = (settings.WEBHOOK_URL or "").strip().rstrip("/")
    if not base_url:
        logger.error("WEBHOOK_URL not set in environment")
        return

    token = spec.token
    if not token:
        logger.warn(f"{spec.name} token not configured")
        return

    bot_secret = (settings.BOT_SECRET or "").strip() or None
    webhook_url = f"{base_url}/webhook/{spec.name}"
    bot = Bot(token=token)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.set_webhook(
            webhook_url,
            drop_pending_updates=True,
            secret_token=bot_secret
        )
        if spec.commands:
            await bot.set_my_commands(spec.commands)
        logger.info(f"Webhook set for {spec.name}: {webhook_url} ({len(spec.commands)} commands)")
    except Exception as e:
        logger.error(f"Failed to set webhook for {spec.name}: {e}")
    finally:
        await bot.session.close()
