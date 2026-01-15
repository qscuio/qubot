import asyncio
import signal
import sys
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.core.logger import Logger
from app.core.database import db
from app.core.bot import telegram_service
from app.bots.dispatcher import bot_dispatcher
from app.services.monitor import monitor_service
from app.services.rss import rss_service
from app.services.ai import ai_service
from app.services.github import github_service
from app.services.twitter import twitter_service
from app.services.crawler import crawler_service
from app.services.limit_up import limit_up_service
from app.services.sector import sector_service
from app.services.market_report import market_report_service
from app.services.watchlist import watchlist_service
from app.services.trading_simulator import trading_simulator
from app.api import api_router

logger = Logger("Main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("🚀 Starting Qubot (Python)...")
    await db.connect()
    
    # Initialize GitHub service in background thread (don't block startup)
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, github_service.init)
    
    # Start Userbot (Telethon) and Bots (Aiogram) in parallel
    await asyncio.gather(
        telegram_service.start(),
        bot_dispatcher.start()
    )
    asyncio.create_task(bot_dispatcher.start_polling())
    
    if settings.ENABLE_MONITOR:
        await monitor_service.initialize()
        await monitor_service.start()
    
    if settings.ENABLE_RSS:
        await rss_service.start()

    # Twitter monitoring
    if await twitter_service.initialize():
        await twitter_service.start()

    # Crawler service
    if settings.ENABLE_CRAWLER:
        await crawler_service.initialize()
        await crawler_service.start()

    # Limit-Up Tracker
    if settings.ENABLE_LIMIT_UP:
        await limit_up_service.initialize()
        await limit_up_service.start()

    # Stock Scanner (启动信号扫描)
    if settings.ENABLE_LIMIT_UP:
        from app.services.stock_scanner import stock_scanner
        await stock_scanner.start()

    # Sector Tracker (板块分析追踪)
    if settings.ENABLE_SECTOR:
        await sector_service.initialize()
        await sector_service.start()

    # Market Report Service (市场分析报告)
    if settings.ENABLE_MARKET_REPORT:
        await market_report_service.initialize()
        await market_report_service.start()

    # Stock History Service (A股历史数据) - initialize in background to avoid blocking startup
    if settings.ENABLE_STOCK_HISTORY:
        from app.services.stock_history import stock_history_service
        await stock_history_service.start()
        # Run initialization in background to avoid blocking (takes ~3 minutes for API call)
        asyncio.create_task(stock_history_service.initialize())

    # Chip Distribution Service (筹码分布) - depends on stock history
    if settings.ENABLE_STOCK_HISTORY:
        from app.services.chip_distribution import chip_distribution_service
        await chip_distribution_service.initialize()
        await chip_distribution_service.start()


    # Watchlist Service (用户自选列表)
    await watchlist_service.start()
    
    # Portfolio Service (实盘持仓)
    from app.services.portfolio import portfolio_service
    await portfolio_service.start()

    # Trading Simulator (模拟交易)
    if settings.ENABLE_TRADING_SIM:
        # Set up notification callback to send to report channel
        async def sim_notify_callback(message: str):
            from app.bots.registry import get_bot
            bot = get_bot("crawler")
            report_target = settings.REPORT_TARGET_GROUP or settings.REPORT_TARGET_CHANNEL
            if bot and report_target:
                try:
                    await bot.send_message(
                        int(report_target),
                        f"🤖 <b>模拟交易</b>\n{message}",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.warn(f"Failed to send sim notification: {e}")
        
        trading_simulator.set_notify_callback(sim_notify_callback)
        await trading_simulator.start()


    # 打板 Service & Simulator
    from app.services.daban_service import daban_service
    from app.services.daban_simulator import daban_simulator
    
    # Set up notification callback for daban_service (real-time signals)
    async def daban_signal_callback(message: str, buttons=None):
        from app.bots.registry import get_bot
        bot = get_bot("crawler")
        target_channel = settings.DABAN_GROUP or settings.DABAN_CHANNEL
        if not bot:
            logger.warn("Daban signal bot not available; cannot send via bot")
            return False
        if not target_channel:
            logger.warn("Daban signal target channel not set; cannot send via bot")
            return False

        def build_reply_markup(use_web_app: bool):
            if not buttons:
                return None, 0
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
            rows = []
            webapp_count = 0
            for row in buttons:
                button_row = []
                for btn in row:
                    text = btn.get("text", "打开")
                    url = btn.get("url")
                    web_app_url = btn.get("web_app_url")
                    if use_web_app and btn.get("web_app") and web_app_url:
                        button_row.append(
                            InlineKeyboardButton(text=text, web_app=WebAppInfo(url=web_app_url))
                        )
                        webapp_count += 1
                    elif url:
                        button_row.append(InlineKeyboardButton(text=text, url=url))
                if button_row:
                    rows.append(button_row)
            if rows:
                return InlineKeyboardMarkup(inline_keyboard=rows), webapp_count
            return None, 0

        try:
            allow_web_app = True
            try:
                chat = await bot.get_chat(int(target_channel))
                # Auto-resolve migrated group ID
                if str(chat.id) != str(target_channel):
                    logger.info(f"Target resolved to new ID: {chat.id} (was {target_channel})")
                    target_channel = str(chat.id)
                    # Update settings cache for future calls
                    if settings.DABAN_GROUP:
                        settings.DABAN_GROUP = target_channel
                    elif settings.DABAN_CHANNEL:
                        settings.DABAN_CHANNEL = target_channel

                chat_type = getattr(chat, "type", None)
                if chat_type != "private":
                    allow_web_app = False
                    logger.info(
                        f"Daban signal target chat type={chat_type}; skip WebApp buttons"
                    )
            except Exception as chat_err:
                logger.warn(f"Failed to resolve daban signal target chat type: {chat_err}")

            reply_markup, webapp_count = build_reply_markup(use_web_app=allow_web_app)
            if reply_markup:
                logger.info(
                    f"Daban signal buttons ready: rows={len(reply_markup.inline_keyboard)} "
                    f"webapp={webapp_count}"
                )
            await bot.send_message(
                int(target_channel),
                message,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
            return True
        except Exception as e:
            from aiogram.exceptions import TelegramMigrateToChat
            
            # Handle Group Migration (auto-update ID for this call)
            if isinstance(e, TelegramMigrateToChat) or "group chat was upgraded" in str(e):
                try:
                    # Try to get new ID from exception object or parse from string
                    new_chat_id = getattr(e, "migrate_to_chat_id", None)
                    if not new_chat_id:
                        import re
                        # Look for "id -100..." sequence
                        match = re.search(r"id\s+(-?\d+)", str(e))
                        if match:
                            new_chat_id = match.group(1)
                    
                    if new_chat_id:
                        logger.warn(f"Target migrated to {new_chat_id}. Retrying... (PLEASE UPDATE CONFIG)")
                        target_channel = str(new_chat_id)
                        # Update settings cache for future calls
                        if settings.DABAN_GROUP:
                            settings.DABAN_GROUP = target_channel
                        elif settings.DABAN_CHANNEL:
                            settings.DABAN_CHANNEL = target_channel

                        allow_web_app = False
                        try:
                            chat = await bot.get_chat(int(new_chat_id))
                            if getattr(chat, "type", None) == "private":
                                allow_web_app = True
                            else:
                                logger.info(
                                    f"Daban signal migrated chat type={getattr(chat, 'type', None)}; "
                                    "skip WebApp buttons"
                                )
                        except Exception as chat_err:
                            logger.warn(
                                f"Failed to resolve migrated chat type: {chat_err}"
                            )

                        reply_markup, _ = build_reply_markup(use_web_app=allow_web_app)
                        # Retry with new ID
                        await bot.send_message(
                            int(new_chat_id),
                            message,
                            parse_mode="HTML",
                            reply_markup=reply_markup
                        )
                        return True
                except Exception as migrate_err:
                    err_text = str(migrate_err)
                    if new_chat_id and "BUTTON_TYPE_INVALID" in err_text and buttons:
                        logger.warn(
                            "WebApp button invalid for migrated target; retrying with URL buttons"
                        )
                        try:
                            reply_markup, _ = build_reply_markup(use_web_app=False)
                            await bot.send_message(
                                int(new_chat_id),
                                message,
                                parse_mode="HTML",
                                reply_markup=reply_markup
                            )
                            return True
                        except Exception as retry_exc:
                            logger.error(
                                f"Failed to send daban signal after migration URL fallback: {retry_exc}"
                            )
                    logger.error(f"Failed to retry after migration: {migrate_err}")

            err_text = str(e)
            if "BUTTON_TYPE_INVALID" in err_text and buttons:
                logger.warn("WebApp button invalid for target; retrying with URL buttons")
                try:
                    reply_markup, webapp_count = build_reply_markup(use_web_app=False)
                    await bot.send_message(
                        int(target_channel),
                        message,
                        parse_mode="HTML",
                        reply_markup=reply_markup
                    )
                    return True
                except Exception as retry_exc:
                    logger.warn(f"Failed to send daban signal after URL fallback: {retry_exc}")
            else:
                logger.warn(f"Failed to send daban signal: {e}")
            return False
    
    daban_service.set_notify_callback(daban_signal_callback)
    await daban_service.start()
    
    # Set up notification callback for daban simulator
    async def daban_notify_callback(message: str):
        from app.bots.registry import get_bot
        bot = get_bot("crawler")
        report_target = settings.REPORT_TARGET_GROUP or settings.REPORT_TARGET_CHANNEL
        if bot and report_target:
            try:
                await bot.send_message(
                    int(report_target),
                    f"🎯 <b>打板模拟</b>\n{message}",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.warn(f"Failed to send daban notification: {e}")
    
    daban_simulator.set_notify_callback(daban_notify_callback)
    await daban_simulator.start()

    # Burst Monitor Service (异动监测)
    from app.services.burst_monitor import burst_monitor_service
    await burst_monitor_service.start()

    # AI Service doesn't need explicit start but is ready
    if ai_service.is_available():
        logger.info("✅ AI Service ready")
        
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down...")
    await bot_dispatcher.stop()
    await telegram_service.stop()
    await rss_service.stop()
    await twitter_service.stop()
    await crawler_service.stop()
    await limit_up_service.stop()
    if settings.ENABLE_LIMIT_UP:
        from app.services.stock_scanner import stock_scanner
        await stock_scanner.stop()
    if settings.ENABLE_SECTOR:
        await sector_service.stop()
    if settings.ENABLE_MARKET_REPORT:
        await market_report_service.stop()
    if settings.ENABLE_STOCK_HISTORY:
        from app.services.stock_history import stock_history_service
        await stock_history_service.stop()
    await portfolio_service.stop()
    await watchlist_service.stop()
    if settings.ENABLE_TRADING_SIM:
        await trading_simulator.stop()
    await daban_service.stop()
    await daban_simulator.stop()
    from app.services.burst_monitor import burst_monitor_service
    await burst_monitor_service.stop()
    await db.disconnect()

app = FastAPI(lifespan=lifespan, title="QuBot API", version="1.0.0")

# Security middleware (rate limiting + scanner blocking)
from app.core.security import SecurityMiddleware, rate_limiter
app.add_middleware(SecurityMiddleware, rate_limiter=rate_limiter)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router (if enabled)
if settings.API_ENABLED:
    app.include_router(api_router)

# Always include chart router for Mini App (public endpoint)
from app.api.routes import chart_router
app.include_router(chart_router)

# Static files (serve web/ directory if exists)
web_dir = os.path.join(os.path.dirname(__file__), "..", "web")
if os.path.isdir(web_dir):
    app.mount("/web", StaticFiles(directory=web_dir, html=True), name="web")

# Mini Apps static files (for Telegram Web Apps)
miniapps_dir = os.path.join(os.path.dirname(__file__), "miniapps")
if os.path.isdir(miniapps_dir):
    app.mount("/miniapp", StaticFiles(directory=miniapps_dir, html=True), name="miniapps")

@app.get("/health")
async def health_check():
    return {
        "status": "ok", 
        "telegram": telegram_service.connected,
        "monitor": monitor_service.is_running
    }

@app.post("/webhook/{bot_name}")
async def webhook_handler(bot_name: str, request: Request):
    """
    Handle incoming Telegram updates for specific bots via webhook.
    URL: https://<domain>/webhook/<bot_name>
    """
    # Verify secret if configured (only if BOT_SECRET has a value)
    bot_secret = (settings.BOT_SECRET or "").strip()
    if bot_secret:
        secret_header = (request.headers.get("X-Telegram-Bot-Api-Secret-Token") or "").strip()
        if secret_header != bot_secret:
            # Debug: log lengths to help diagnose mismatches
            logger.warn(f"Webhook rejected: invalid secret for {bot_name} (got {len(secret_header)} chars, expected {len(bot_secret)} chars)")
            return {"status": "error", "message": "Invalid secret"}

    try:
        data = await request.json()
        await bot_dispatcher.feed_update(bot_name, data)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Webhook processing error for {bot_name}", e)
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.BOT_PORT, reload=True)
