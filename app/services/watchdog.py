import asyncio
import sys
import os
import time
import httpx
from app.core.config import settings
from app.core.logger import Logger

logger = Logger("Watchdog")

class WatchdogService:
    def __init__(self):
        self.is_running = False
        self._check_task = None
        self._last_tick = time.time()
        self._fail_count = 0
        self._max_fails = 3
        self._check_interval = 60  # Check every 60 seconds
        
    async def start(self):
        """Start the watchdog service."""
        if self.is_running:
            return
            
        self.is_running = True
        self._check_task = asyncio.create_task(self._monitor_loop())
        logger.info("✅ Watchdog Service started")

    async def stop(self):
        """Stop the watchdog service."""
        self.is_running = False
        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass
        logger.info("Watchdog Service stopped")

    async def _monitor_loop(self):
        """Main monitoring loop."""
        # Initial grace period
        await asyncio.sleep(60)
        
        while self.is_running:
            try:
                # 1. Check Event Loop Lag
                current_time = time.time()
                lag = current_time - self._last_tick - self._check_interval
                # Allow some small drift, but if lag is huge, loop is blocked
                if lag > 10:
                    logger.warn(f"⚠️ Event loop lag detected: {lag:.2f}s")
                self._last_tick = current_time

                # 2. Check HTTP Health Endpoint
                is_healthy = await self._check_health()
                
                if not is_healthy:
                    self._fail_count += 1
                    logger.warn(f"⚠️ Health check failed ({self._fail_count}/{self._max_fails})")
                    
                    if self._fail_count >= self._max_fails:
                        await self._trigger_emergency_restart()
                else:
                    if self._fail_count > 0:
                        logger.info("✅ Health check recovered")
                    self._fail_count = 0
                    
            except Exception as e:
                logger.error(f"Watchdog error: {e}")
                
            await asyncio.sleep(self._check_interval)

    async def _check_health(self) -> bool:
        """Ping the internal health endpoint."""
        port = settings.BOT_PORT or 6887
        url = f"http://127.0.0.1:{port}/health"
        
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    return True
                else:
                    logger.warn(f"Health endpoint returned status {resp.status_code}")
                    return False
        except Exception as e:
            logger.warn(f"Failed to connect to health endpoint: {e}")
            return False

    async def _trigger_emergency_restart(self):
        """Notify admin and kill the process."""
        logger.error("🚨 CRITICAL: Application unresponsive. Triggering restart...")
        
        # Try to send notification via Telegram if possible
        try:
            from app.core.bot import telegram_service
            if settings.BOT_TOKEN and telegram_service:
                # Assuming simple notification - hard to send if loop is stuck but worth a try
                # We can try using a fresh httpx call to Telegram API directly to bypass aiogram/telethon if they are stuck?
                # But for now, let's try the service.
                admin_id = settings.allowed_users_list[0] if settings.allowed_users_list else None
                if admin_id:
                     # Fire and forget
                    asyncio.create_task(telegram_service.send_message(
                        admin_id, 
                        "🚨 <b>System Alert</b>\nApplication is unhealthy (zombie/stuck). Watchdog is forcing a restart."
                    ))
                    # Give it a moment to send
                    await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"Failed to send restart notification: {e}")

        # Suidicide
        logger.error("☠️ Killing process now.")
        sys.exit(1)

watchdog_service = WatchdogService()
