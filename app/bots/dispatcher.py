import asyncio
from typing import Dict, List
from aiogram import Bot, Dispatcher
from app.bots.bot_spec import BotSpec
from app.bots.registry import BOT_SPECS
from app.bots.middleware import AllowedUsersMiddleware
from app.core.config import settings
from app.core.logger import Logger

logger = Logger("BotDispatcher")

class BotDispatcher:
    def __init__(self):
        self.apps: List[Dict] = [] # List of {bot: Bot, dp: Dispatcher}

    async def start(self):
        for spec in BOT_SPECS:
            if spec.token:
                await self._setup_bot(spec)
            else:
                logger.info(f"{spec.name} skipped (token not configured)")

        # Automatic Webhook Setup (with error handling)
        if settings.WEBHOOK_URL:
            try:
                await self._register_webhooks()
            except Exception as e:
                logger.error(f"⚠️ Webhook registration failed, will use polling: {e}")

    async def _setup_bot(self, spec: BotSpec):
        try:
            bot = Bot(token=spec.token)
            dp = Dispatcher()

            # Apply access control middleware to ALL event types
            allowed_middleware = AllowedUsersMiddleware()
            dp.message.middleware(allowed_middleware)
            dp.callback_query.middleware(allowed_middleware)
            dp.inline_query.middleware(allowed_middleware)
            dp.edited_message.middleware(allowed_middleware)
            dp.channel_post.middleware(allowed_middleware)
            dp.edited_channel_post.middleware(allowed_middleware)
            dp.chosen_inline_result.middleware(allowed_middleware)
            
            import importlib
            module = importlib.import_module(spec.router_module)
            if hasattr(module, "router"):
                dp.include_router(module.router)
            else:
                logger.warn(f"⚠️ {spec.name}: no router found in {spec.router_module}")

            if spec.commands:
                try:
                    await bot.set_my_commands(spec.commands)
                    logger.info(f"✅ {spec.name} commands registered ({len(spec.commands)})")
                except Exception as e:
                    logger.warn(f"⚠️ {spec.name} command registration failed: {e}")

            self.apps.append({"bot": bot, "dp": dp, "name": spec.name})
            logger.info(f"✅ {spec.name} initialized")
        except Exception as e:
            import traceback
            logger.error(f"❌ Failed to setup {spec.name}: {e}\n{traceback.format_exc()}")
    
    async def _add_router_to_bot(self, bot_name: str, router_module: str):
        """Add an additional router to an existing bot."""
        app = next((a for a in self.apps if a['name'] == bot_name), None)
        if not app:
            logger.warn(f"⚠️ Cannot add router: bot {bot_name} not found")
            return
        
        try:
            import importlib
            module = importlib.import_module(router_module)
            if hasattr(module, "router"):
                app['dp'].include_router(module.router)
                logger.info(f"✅ Added {router_module} to {bot_name}")
            else:
                logger.warn(f"⚠️ No router found in {router_module}")
        except Exception as e:
            logger.error(f"❌ Failed to add router {router_module}: {e}")

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
