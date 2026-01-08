"""
Limit-Up Stock Tracker Service (涨停股追踪)

Tracks daily limit-up stocks, monitors next-day price movements,
and maintains consecutive limit-up (连板) statistics.
"""

import asyncio
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional
import pytz

from app.core.logger import Logger
from app.core.database import db
from app.core.config import settings

logger = Logger("LimitUpService")

# China timezone
CHINA_TZ = pytz.timezone("Asia/Shanghai")


class LimitUpService:
    """Service for tracking limit-up stocks."""
    
    def __init__(self):
        self.is_running = False
        self._scheduler_task = None
        self._ak = None  # AkShare module (lazy load)
    
    def _get_akshare(self):
        """Lazy load akshare module."""
        if self._ak is None:
            try:
                import akshare as ak
                self._ak = ak
            except ImportError:
                logger.error("AkShare not installed. Run: pip install akshare")
                return None
        return self._ak
    
    async def start(self):
        """Start the limit-up tracker service."""
        if self.is_running or not settings.ENABLE_LIMIT_UP:
            return
        
        if not settings.STOCK_ALERT_CHANNEL:
            logger.warn("STOCK_ALERT_CHANNEL not configured, limit-up alerts disabled")
            return
        
        self.is_running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("✅ Limit-Up Tracker started")
    
    async def stop(self):
        """Stop the service."""
        self.is_running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        logger.info("Limit-Up Tracker stopped")
    
    # ─────────────────────────────────────────────────────────────────────────
    # Data Collection (4PM Daily)
    # ─────────────────────────────────────────────────────────────────────────
    
    async def collect_limit_ups(self, target_date: date = None) -> List[Dict]:
        """Collect today's limit-up stocks from AkShare."""
        ak = self._get_akshare()
        if not ak:
            return []
        
        target_date = target_date or date.today()
        date_str = target_date.strftime("%Y%m%d")
        
        try:
            # Get limit-up pool from EastMoney via AkShare
            df = await asyncio.to_thread(ak.stock_zt_pool_em, date=date_str)
            
            if df is None or df.empty:
                logger.info(f"No limit-up stocks found for {date_str}")
                return []
            
            stocks = []
            for _, row in df.iterrows():
                stock = {
                    "code": str(row.get("代码", "")),
                    "name": str(row.get("名称", "")),
                    "close_price": float(row.get("最新价", 0)),
                    "change_pct": float(row.get("涨跌幅", 0)),
                    "turnover_rate": float(row.get("换手率", 0)),
                    "limit_times": int(row.get("连板数", 1)),
                }
                stocks.append(stock)
            
            # Save to database
            await self._save_limit_ups(target_date, stocks)
            
            # Update streak stats
            await self._update_streaks(target_date, stocks)
            
            logger.info(f"Collected {len(stocks)} limit-up stocks for {date_str}")
            return stocks
            
        except Exception as e:
            logger.error(f"Failed to collect limit-ups: {e}")
            return []
    
    async def _save_limit_ups(self, target_date: date, stocks: List[Dict]):
        """Save limit-up stocks to database."""
        if not db.pool:
            return
        
        for stock in stocks:
            try:
                await db.pool.execute("""
                    INSERT INTO limit_up_stocks 
                    (code, name, date, close_price, change_pct, turnover_rate, limit_times)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (code, date) DO UPDATE SET
                        close_price = EXCLUDED.close_price,
                        change_pct = EXCLUDED.change_pct,
                        limit_times = EXCLUDED.limit_times
                """, 
                    stock["code"], stock["name"], target_date,
                    stock["close_price"], stock["change_pct"],
                    stock["turnover_rate"], stock["limit_times"]
                )
            except Exception as e:
                logger.warn(f"Failed to save {stock['code']}: {e}")
    
    async def _update_streaks(self, target_date: date, stocks: List[Dict]):
        """Update consecutive limit-up streak statistics."""
        if not db.pool:
            return
        
        # 2-month cycle start
        cycle_start = target_date.replace(day=1)
        if target_date.day < 15:
            cycle_start = (cycle_start - timedelta(days=1)).replace(day=1)
        
        for stock in stocks:
            try:
                existing = await db.pool.fetchrow("""
                    SELECT * FROM limit_up_streaks WHERE code = $1
                """, stock["code"])
                
                if existing:
                    # Check if consecutive (within 3 trading days)
                    last_date = existing["last_limit_date"]
                    days_diff = (target_date - last_date).days
                    
                    if days_diff <= 3:  # Consecutive
                        new_streak = existing["streak_count"] + 1
                    else:
                        new_streak = 1  # Reset
                    
                    await db.pool.execute("""
                        UPDATE limit_up_streaks SET
                            streak_count = $2,
                            last_limit_date = $3,
                            updated_at = NOW()
                        WHERE code = $1
                    """, stock["code"], new_streak, target_date)
                else:
                    # New entry
                    await db.pool.execute("""
                        INSERT INTO limit_up_streaks 
                        (code, name, streak_count, first_limit_date, last_limit_date, cycle_start)
                        VALUES ($1, $2, $3, $4, $5, $6)
                    """, stock["code"], stock["name"], stock["limit_times"],
                        target_date, target_date, cycle_start)
                        
            except Exception as e:
                logger.warn(f"Failed to update streak for {stock['code']}: {e}")
    
    # ─────────────────────────────────────────────────────────────────────────
    # Morning Price Updates
    # ─────────────────────────────────────────────────────────────────────────
    
    async def get_previous_limit_prices(self) -> List[Dict]:
        """Get real-time prices of yesterday's limit-up stocks."""
        ak = self._get_akshare()
        if not ak or not db.pool:
            return []
        
        # Get yesterday's limit-up stocks
        yesterday = date.today() - timedelta(days=1)
        # Skip weekends
        if yesterday.weekday() >= 5:
            yesterday = yesterday - timedelta(days=yesterday.weekday() - 4)
        
        stocks = await db.pool.fetch("""
            SELECT code, name, close_price, limit_times
            FROM limit_up_stocks
            WHERE date = $1
            ORDER BY limit_times DESC, close_price DESC
        """, yesterday)
        
        if not stocks:
            return []
        
        try:
            # Get real-time quotes
            df = await asyncio.to_thread(ak.stock_zh_a_spot_em)
            if df is None or df.empty:
                return []
            
            # Build lookup
            price_map = {}
            for _, row in df.iterrows():
                code = str(row.get("代码", ""))
                price_map[code] = {
                    "current_price": float(row.get("最新价", 0)),
                    "change_pct": float(row.get("涨跌幅", 0)),
                }
            
            result = []
            for stock in stocks:
                code = stock["code"]
                if code in price_map:
                    result.append({
                        "code": code,
                        "name": stock["name"],
                        "prev_close": float(stock["close_price"]),
                        "limit_times": stock["limit_times"],
                        **price_map[code],
                    })
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get prices: {e}")
            return []
    
    # ─────────────────────────────────────────────────────────────────────────
    # Reports
    # ─────────────────────────────────────────────────────────────────────────
    
    async def get_strong_stocks(self, days: int = 7) -> List[Dict]:
        """Get strong stocks (multiple limit-ups in recent days)."""
        if not db.pool:
            return []
        
        rows = await db.pool.fetch("""
            SELECT code, name, COUNT(*) as limit_count,
                   MAX(limit_times) as max_streak
            FROM limit_up_stocks
            WHERE date >= CURRENT_DATE - INTERVAL '%s days'
            GROUP BY code, name
            HAVING COUNT(*) >= 2
            ORDER BY limit_count DESC, max_streak DESC
            LIMIT 20
        """ % days)
        
        return [dict(r) for r in rows]
    
    async def get_streak_leaders(self) -> List[Dict]:
        """Get current consecutive limit-up leaders (连板榜)."""
        if not db.pool:
            return []
        
        rows = await db.pool.fetch("""
            SELECT code, name, streak_count, first_limit_date, last_limit_date
            FROM limit_up_streaks
            WHERE streak_count >= 2
              AND last_limit_date >= CURRENT_DATE - INTERVAL '3 days'
            ORDER BY streak_count DESC
            LIMIT 20
        """)
        
        return [dict(r) for r in rows]
    
    async def send_afternoon_report(self):
        """Send 4PM report with limit-ups, strong stocks, and streak leaders."""
        from app.core.bot import telegram_service
        
        if not settings.STOCK_ALERT_CHANNEL:
            return
        
        # Collect today's limit-ups
        stocks = await self.collect_limit_ups()
        strong = await self.get_strong_stocks()
        streaks = await self.get_streak_leaders()
        
        now = datetime.now(CHINA_TZ)
        
        # Build report
        lines = [
            f"📊 <b>涨停股日报</b> {now.strftime('%Y-%m-%d %H:%M')}",
            "━━━━━━━━━━━━━━━━━━━━━",
            f"\n🔴 <b>今日涨停</b> ({len(stocks)}只)\n",
        ]
        
        # Today's limit-ups (top 15)
        for i, s in enumerate(stocks[:15], 1):
            streak = f"[{s['limit_times']}板]" if s['limit_times'] > 1 else ""
            lines.append(f"{i}. {s['name']} ({s['code']}) {streak}")
        
        if len(stocks) > 15:
            lines.append(f"...及其他 {len(stocks)-15} 只")
        
        # Streak leaders
        if streaks:
            lines.append(f"\n🔥 <b>连板榜</b>\n")
            for s in streaks[:10]:
                lines.append(f"• {s['name']} ({s['code']}) - {s['streak_count']}连板")
        
        # Strong stocks
        if strong:
            lines.append(f"\n💪 <b>近期强势股</b> (7日多次涨停)\n")
            for s in strong[:10]:
                lines.append(f"• {s['name']} ({s['code']}) - {s['limit_count']}次涨停")
        
        text = "\n".join(lines)
        await telegram_service.send_message(settings.STOCK_ALERT_CHANNEL, text, parse_mode="html")
        logger.info("Sent afternoon limit-up report")
    
    async def send_morning_price_update(self):
        """Send morning price update for yesterday's limit-up stocks."""
        from app.core.bot import telegram_service
        
        if not settings.STOCK_ALERT_CHANNEL:
            return
        
        prices = await self.get_previous_limit_prices()
        if not prices:
            return
        
        now = datetime.now(CHINA_TZ)
        
        lines = [
            f"📈 <b>昨日涨停股实时</b> {now.strftime('%H:%M')}",
            "━━━━━━━━━━━━━━━━━━━━━\n",
        ]
        
        for p in prices[:20]:
            change = p["change_pct"]
            icon = "🔴" if change > 5 else ("🟢" if change > 0 else "🟢" if change == 0 else "⚪")
            streak = f"[{p['limit_times']}板]" if p['limit_times'] > 1 else ""
            lines.append(
                f"{icon} {p['name']} {streak}\n"
                f"   {p['current_price']:.2f} ({change:+.2f}%)"
            )
        
        text = "\n".join(lines)
        await telegram_service.send_message(settings.STOCK_ALERT_CHANNEL, text, parse_mode="html")
        logger.info(f"Sent morning price update at {now.strftime('%H:%M')}")
    
    # ─────────────────────────────────────────────────────────────────────────
    # Scheduler
    # ─────────────────────────────────────────────────────────────────────────
    
    async def _scheduler_loop(self):
        """Background scheduler for timed tasks."""
        # Morning report times
        morning_times = ["09:25", "09:30", "09:35", "09:45", "09:50", "09:55", "10:00"]
        afternoon_time = "16:00"
        
        triggered_today = set()
        
        while self.is_running:
            try:
                now = datetime.now(CHINA_TZ)
                time_str = now.strftime("%H:%M")
                date_str = now.strftime("%Y-%m-%d")
                
                # Reset triggered set at midnight
                if time_str == "00:00":
                    triggered_today.clear()
                
                key = f"{date_str}_{time_str}"
                
                # Skip weekends
                if now.weekday() < 5:
                    # Morning updates
                    if time_str in morning_times and key not in triggered_today:
                        triggered_today.add(key)
                        asyncio.create_task(self.send_morning_price_update())
                    
                    # Afternoon report
                    if time_str == afternoon_time and key not in triggered_today:
                        triggered_today.add(key)
                        asyncio.create_task(self.send_afternoon_report())
                
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
            
            # Check every 30 seconds
            await asyncio.sleep(30)


# Singleton
limit_up_service = LimitUpService()
