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

    # Stock History Service (A股历史数据)
    if settings.ENABLE_STOCK_HISTORY:
        from app.services.stock_history import stock_history_service
        await stock_history_service.initialize()
        await stock_history_service.start()

    # Watchlist Service (用户自选列表)
    await watchlist_service.start()

    # Trading Simulator (模拟交易)
    if settings.ENABLE_TRADING_SIM:
        await trading_simulator.start()

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
    await watchlist_service.stop()
    if settings.ENABLE_TRADING_SIM:
        await trading_simulator.stop()
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
