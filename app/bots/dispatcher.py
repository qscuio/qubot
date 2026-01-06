import asyncio
from typing import Dict, List
from aiogram import Bot, Dispatcher
from app.core.config import settings
from app.core.logger import Logger

logger = Logger("BotDispatcher")

class BotDispatcher:
    def __init__(self):
        self.apps: List[Dict] = [] # List of {bot: Bot, dp: Dispatcher}

    async def start(self):
        # 1. Monitor Bot
        if settings.MONITOR_BOT_TOKEN:
            await self._setup_bot("monitor-bot", settings.MONITOR_BOT_TOKEN, "app.bots.monitor.handlers")

        # 2. AI Bot
        if settings.AI_BOT_TOKEN:
            await self._setup_bot("ai-bot", settings.AI_BOT_TOKEN, "app.bots.ai.handlers")

        # 3. RSS Bot
        if settings.RSS_BOT_TOKEN:
            await self._setup_bot("rss-bot", settings.RSS_BOT_TOKEN, "app.bots.rss.handlers")

        # Automatic Webhook Setup (with error handling)
        if settings.WEBHOOK_URL:
            try:
                await self._register_webhooks()
            except Exception as e:
                logger.error(f"⚠️ Webhook registration failed, will use polling: {e}")

    async def _setup_bot(self, name, token, router_module):
        try:
            bot = Bot(token=token)
            dp = Dispatcher()
            
            import importlib
            module = importlib.import_module(router_module)
            if hasattr(module, "router"):
                dp.include_router(module.router)
            else:
                logger.warn(f"⚠️ {name}: no router found in {router_module}")

            self.apps.append({"bot": bot, "dp": dp, "name": name})
            logger.info(f"✅ {name} initialized")
        except Exception as e:
            import traceback
            logger.error(f"❌ Failed to setup {name}: {e}\n{traceback.format_exc()}")

    async def _register_webhooks(self):
        """Register webhooks with retry logic."""
        base_url = settings.WEBHOOK_URL.rstrip('/')
        max_retries = 3
        bot_secret = (settings.BOT_SECRET or "").strip() or None
        
        for app in self.apps:
            webhook_url = f"{base_url}/webhook/{app['name']}"
            
            for attempt in range(max_retries):
                try:
                    # Delete old webhook first to force re-registration with new secret
                    await app['bot'].delete_webhook(drop_pending_updates=True)
                    
                    logger.info(f"🔗 Setting webhook for {app['name']}: {webhook_url}")
                    await app['bot'].set_webhook(
                        webhook_url, 
                        drop_pending_updates=True,
                        secret_token=bot_secret
                    )
                    break
                except Exception as e:
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 5
                        logger.warn(f"⚠️ Webhook setup failed for {app['name']}, retrying in {wait_time}s: {e}")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"❌ Failed to set webhook for {app['name']} after {max_retries} attempts: {e}")
                        logger.info(f"ℹ️ {app['name']} will use polling as fallback")

    async def feed_update(self, bot_name: str, update_data: dict):
        app = next((a for a in self.apps if a['name'] == bot_name), None)
        if not app:
            logger.warn(f"Received webhook for unknown bot: {bot_name}")
            return
        
        # Manually constructing update object for aiogram 3.x
        # Update.model_validate(update_data, context={"bot": app['bot']})
        from aiogram.types import Update
        update = Update.model_validate(update_data, context={"bot": app['bot']})
        await app['dp'].feed_update(app['bot'], update)

    async def start_polling(self):
        # Only poll if NO webhook configured
        if settings.WEBHOOK_URL:
             logger.info("⏭️ Webhook configured, skipping polling.")
             return

        coros = []
        for app in self.apps:
            logger.info(f"🚀 Starting polling for {app['name']}...")
            coros.append(app['dp'].start_polling(app['bot'], handle_signals=False))
        
        if coros:
            await asyncio.gather(*coros)

    async def stop(self):
        for app in self.apps:
            # Maybe delete webhook on stop?
            # await app['bot'].delete_webhook()
            await app['bot'].session.close()
            logger.info(f"🛑 Stopped {app['name']}")

bot_dispatcher = BotDispatcher()
