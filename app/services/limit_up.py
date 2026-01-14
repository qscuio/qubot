"""
Limit-Up Stock Tracker Service (涨停股追踪)

Tracks daily limit-up stocks, monitors next-day price movements,
and maintains consecutive limit-up (连板) statistics.
"""

import asyncio
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional

from app.core.logger import Logger
from app.core.database import db
from app.core.config import settings
from app.core.stock_links import get_chart_url
from app.core.timezone import CHINA_TZ, china_now, china_today

logger = Logger("LimitUpService")


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
    
    async def initialize(self):
        """Initialize service - ensure at least 7 trading days of history."""
        if not db.pool:
            return
        
        # Get distinct dates we already have
        existing_dates = await db.pool.fetch("""
            SELECT DISTINCT date FROM limit_up_stocks 
            ORDER BY date DESC LIMIT 14
        """)
        existing_set = {row['date'] for row in existing_dates}
        
        if len(existing_set) >= 7:
            logger.info(f"Found {len(existing_set)} days of history, sufficient")
            return
        
        needed = 7 - len(existing_set)
        logger.info(f"Have {len(existing_set)} days, need {needed} more, backfilling...")
        
        today = china_today()
        days_collected = 0
        days_checked = 0
        
        while days_collected < needed and days_checked < 14:
            target_date = today - timedelta(days=days_checked)
            days_checked += 1
            
            # Skip weekends
            if target_date.weekday() >= 5:
                continue
            
            # Skip dates we already have
            if target_date in existing_set:
                continue
            
            try:
                stocks = await self.collect_limit_ups(target_date)
                if stocks:
                    logger.info(f"Backfilled {target_date}: {len(stocks)} stocks")
                    days_collected += 1
                else:
                    logger.info(f"No data for {target_date}")
                
                # Small delay to avoid rate limiting
                await asyncio.sleep(1)
            except Exception as e:
                logger.warn(f"Failed to backfill {target_date}: {e}")
        
        logger.info(f"Backfill complete: added {days_collected} days")
    
    
    # ─────────────────────────────────────────────────────────────────────────
    # Data Collection (4PM Daily)
    # ─────────────────────────────────────────────────────────────────────────
    
    async def get_realtime_limit_ups(self, date_str: str = None) -> List[Dict]:
        """Fetch real-time limit-up stocks from AkShare without saving to DB."""
        ak = self._get_akshare()
        if not ak:
            return []
        
        if not date_str:
            date_str = china_today().strftime("%Y%m%d")
        
        stocks = []
        try:
            # 1. Get sealed limit-up pool (收盘涨停/首板)
            df_sealed = await asyncio.to_thread(ak.stock_zt_pool_em, date=date_str)
            
            if df_sealed is not None and not df_sealed.empty:
                for _, row in df_sealed.iterrows():
                    stock = {
                        "code": str(row.get("代码", "")),
                        "name": str(row.get("名称", "")),
                        "close_price": float(row.get("最新价", 0)),
                        "change_pct": float(row.get("涨跌幅", 0)),
                        "turnover_rate": float(row.get("换手率", 0)),
                        "limit_times": int(row.get("连板数", 1)),
                        "is_sealed": True,
                    }
                    stocks.append(stock)
            
            # 2. Get burst limit-up pool (曾涨停/炸板)
            try:
                df_burst = await asyncio.to_thread(ak.stock_zt_pool_zbgc_em, date=date_str)
                
                if df_burst is not None and not df_burst.empty:
                    for _, row in df_burst.iterrows():
                        stock = {
                            "code": str(row.get("代码", "")),
                            "name": str(row.get("名称", "")),
                            "close_price": float(row.get("最新价", 0)),
                            "change_pct": float(row.get("涨跌幅", 0)),
                            "turnover_rate": float(row.get("换手率", 0)),
                            "limit_times": 1,
                            "is_sealed": False,
                        }
                        stocks.append(stock)
            except Exception as e:
                logger.warn(f"Failed to fetch burst limit-ups: {e}")
            
            return stocks
            
        except Exception as e:
            logger.error(f"Failed to fetch realtime limit-ups: {e}")
            return []

    async def collect_limit_ups(self, target_date: date = None) -> List[Dict]:
        """Collect today's limit-up stocks and save to database."""
        target_date = target_date or china_today()
        date_str = target_date.strftime("%Y%m%d")
        
        stocks = await self.get_realtime_limit_ups(date_str)
        
        if not stocks:
            logger.info(f"No limit-up stocks found for {date_str}")
            return []
        
        # Save to database (only sealed ones for streak tracking)
        await self._save_limit_ups(target_date, stocks)
        
        # Update streak stats (only for sealed limit-ups)
        sealed_stocks = [s for s in stocks if s.get("is_sealed", True)]
        await self._update_streaks(target_date, sealed_stocks)
        
        # Update startup watchlist (only for sealed limit-ups)
        await self._update_startup_watchlist(target_date, sealed_stocks)
        
        logger.info(f"Collected {len(stocks)} total limit-up stocks for {date_str}")
        return stocks
    
    async def _save_limit_ups(self, target_date: date, stocks: List[Dict]):
        """Save limit-up stocks to database."""
        if not db.pool:
            return
        
        for stock in stocks:
            try:
                await db.pool.execute("""
                    INSERT INTO limit_up_stocks 
                    (code, name, date, close_price, change_pct, turnover_rate, limit_times, is_sealed)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (code, date) DO UPDATE SET
                        close_price = EXCLUDED.close_price,
                        change_pct = EXCLUDED.change_pct,
                        limit_times = EXCLUDED.limit_times,
                        is_sealed = EXCLUDED.is_sealed
                """, 
                    stock["code"], stock["name"], target_date,
                    stock["close_price"], stock["change_pct"],
                    stock["turnover_rate"], stock["limit_times"],
                    stock.get("is_sealed", True)
                )
            except Exception as e:
                logger.warn(f"Failed to save {stock['code']}: {e}")
    

    async def _update_streaks(self, target_date: date, stocks: List[Dict]):
        """Update consecutive limit-up streak statistics.
        
        Uses AkShare's limit_times as the authoritative streak count.
        """
        if not db.pool:
            return
        
        # 2-month cycle start
        cycle_start = target_date.replace(day=1)
        if target_date.day < 15:
            cycle_start = (cycle_start - timedelta(days=1)).replace(day=1)
        
        for stock in stocks:
            try:
                # Use AkShare's limit_times as the authoritative consecutive count
                streak_count = stock.get("limit_times", 1) or 1
                
                existing = await db.pool.fetchrow("""
                    SELECT * FROM limit_up_streaks WHERE code = $1
                """, stock["code"])
                
                if existing:
                    # Update existing entry with current streak from AkShare
                    await db.pool.execute("""
                        UPDATE limit_up_streaks SET
                            streak_count = $2,
                            last_limit_date = $3,
                            name = COALESCE($4, name),
                            updated_at = NOW()
                        WHERE code = $1
                    """, stock["code"], streak_count, target_date, stock.get("name"))
                else:
                    # New entry - use AkShare's limit_times
                    first_date = target_date - timedelta(days=streak_count - 1)  # Estimate first limit date
                    await db.pool.execute("""
                        INSERT INTO limit_up_streaks 
                        (code, name, streak_count, first_limit_date, last_limit_date, cycle_start)
                        VALUES ($1, $2, $3, $4, $5, $6)
                    """, stock["code"], stock["name"], streak_count,
                        first_date, target_date, cycle_start)
                        
            except Exception as e:
                logger.warn(f"Failed to update streak for {stock['code']}: {e}")
    
    async def _update_startup_watchlist(self, target_date: date, stocks: List[Dict]):
        """Update startup watchlist (启动追踪).
        
        - Add stocks with 1 limit-up in past month
        - Remove stocks when they hit 2nd limit-up in past month
        """
        if not db.pool:
            return
        
        month_ago = target_date - timedelta(days=30)
        
        for stock in stocks:
            try:
                # Count limit-ups in past month for this stock
                count = await db.pool.fetchval("""
                    SELECT COUNT(*) FROM limit_up_stocks 
                    WHERE code = $1 AND date >= $2
                """, stock["code"], month_ago)
                
                if count == 1:
                    # First limit-up this month, add to watchlist
                    await db.pool.execute("""
                        INSERT INTO startup_watchlist 
                        (code, name, first_limit_date, first_limit_price)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT (code) DO NOTHING
                    """, stock["code"], stock["name"], target_date, stock["close_price"])
                elif count >= 2:
                    # Second limit-up this month, remove from watchlist
                    await db.pool.execute("""
                        DELETE FROM startup_watchlist WHERE code = $1
                    """, stock["code"])
                    
            except Exception as e:
                logger.warn(f"Failed to update watchlist for {stock['code']}: {e}")
    
    
    # ─────────────────────────────────────────────────────────────────────────
    # Morning Price Updates
    # ─────────────────────────────────────────────────────────────────────────
    
    async def get_previous_limit_prices(self) -> List[Dict]:
        """Get real-time prices of yesterday's limit-up stocks."""
        ak = self._get_akshare()
        if not ak or not db.pool:
            logger.warn("get_previous_limit_prices: akshare or db not available")
            return []
        
        report_date = await db.pool.fetchval("""
            SELECT MAX(date) FROM limit_up_stocks
            WHERE date < $1
        """, china_today())

        stocks = []
        if report_date:
            logger.info(f"Fetching limit-up stocks for {report_date}")
            stocks = await db.pool.fetch("""
                SELECT code, name, close_price, limit_times
                FROM limit_up_stocks
                WHERE date = $1 AND is_sealed = TRUE
                ORDER BY limit_times DESC, close_price DESC
            """, report_date)
            if not stocks:
                logger.warn(f"No sealed limit-up stocks found in DB for {report_date}")
                return []
        else:
            # Fallback: best-effort previous trading day, but avoid polluting DB
            report_date = china_today() - timedelta(days=1)
            while report_date.weekday() >= 5:
                report_date -= timedelta(days=1)

            logger.warn(
                f"No limit-up history found in DB, fetching from AkShare for {report_date}"
            )
            date_str = report_date.strftime("%Y%m%d")
            try:
                fetched = await self.get_realtime_limit_ups(date_str)
                if fetched:
                    stocks = [
                        {"code": s["code"], "name": s["name"],
                         "close_price": s["close_price"], "limit_times": s.get("limit_times", 1)}
                        for s in fetched if s.get("is_sealed", True)
                    ]
            except Exception as e:
                logger.error(f"Failed to fetch from AkShare: {e}")

        if not stocks:
            logger.warn(f"No limit-up stocks found for {report_date}")
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
    
    async def get_startup_watchlist(self) -> List[Dict]:
        """Get startup watchlist (启动追踪 - 一个月内涨停一次的股票)."""
        if not db.pool:
            return []
        
        rows = await db.pool.fetch("""
            SELECT code, name, first_limit_date, first_limit_price
            FROM startup_watchlist
            ORDER BY first_limit_date DESC
        """)
        
        return [dict(r) for r in rows]
    
    async def get_strong_stocks(self, days: int = 7) -> List[Dict]:
        """Get strong stocks (3+ limit-ups in recent days)."""
        if not db.pool:
            return []
        
        rows = await db.pool.fetch("""
            SELECT code, name, COUNT(*) as limit_count,
                   MAX(limit_times) as max_streak
            FROM limit_up_stocks
            WHERE date >= CURRENT_DATE - INTERVAL '%s days'
            GROUP BY code, name
            HAVING COUNT(*) >= 3
            ORDER BY limit_count DESC, max_streak DESC
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
        """)
        
        return [dict(r) for r in rows]
    
    async def send_afternoon_report(self):
        """Send 4PM report with limit-ups, strong stocks, and streak leaders.
        
        Sends complete lists split into multiple messages if needed.
        No truncation - all stocks are included.
        """
        from app.core.bot import telegram_service
        
        if not settings.STOCK_ALERT_CHANNEL:
            return
        
        # Collect today's limit-ups
        stocks = await self.collect_limit_ups()
        strong = await self.get_strong_stocks()
        streaks = await self.get_streak_leaders()
        
        # Separate sealed and burst stocks
        sealed_stocks = [s for s in stocks if s.get("is_sealed", True)]
        burst_stocks = [s for s in stocks if not s.get("is_sealed", True)]
        
        now = datetime.now(CHINA_TZ)
        
        # Helper to split long lists into multiple messages
        async def send_stock_list(title: str, items: List[Dict], formatter):
            """Send a stock list, splitting into multiple messages if needed."""
            if not items:
                return
            
            MAX_CHARS = 3800
            messages = []
            current_lines = [title, ""]
            current_len = len(title) + 1
            
            for i, item in enumerate(items, 1):
                line = formatter(i, item)
                line_len = len(line) + 1
                
                if current_len + line_len > MAX_CHARS:
                    messages.append("\n".join(current_lines))
                    page_num = len(messages) + 1
                    current_lines = [f"{title} (续{page_num})", ""]
                    current_len = len(current_lines[0]) + 1
                
                current_lines.append(line)
                current_len += line_len
            
            if len(current_lines) > 2:  # Has content beyond header
                messages.append("\n".join(current_lines))
            
            # Send all messages
            for msg in messages:
                await telegram_service.send_message(
                    settings.STOCK_ALERT_CHANNEL, msg, 
                    parse_mode="html", link_preview=False
                )
        
        # 1. Send header
        header = (
            f"📊 <b>涨停股日报</b> {now.strftime('%Y-%m-%d %H:%M')}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔴 收盘涨停: {len(sealed_stocks)}只\n"
            f"💥 曾涨停: {len(burst_stocks)}只\n"
            f"🔥 连板股: {len(streaks)}只\n"
            f"💪 强势股: {len(strong)}只"
        )
        await telegram_service.send_message(
            settings.STOCK_ALERT_CHANNEL, header, 
            parse_mode="html", link_preview=False
        )
        
        # 2. Send sealed limit-ups (收盘涨停) - complete list
        def format_sealed(i, s):
            streak = f"[{s['limit_times']}板]" if s['limit_times'] > 1 else ""
            chart_url = get_chart_url(s['code'], s.get('name'))
            return f"{i}. <a href=\"{chart_url}\">{s['name']}</a> ({s['code']}) {streak}"
        
        await send_stock_list(
            f"🔴 <b>收盘涨停</b> ({len(sealed_stocks)}只)",
            sealed_stocks, format_sealed
        )
        
        # 3. Send burst limit-ups (炸板) - complete list  
        def format_burst(i, s):
            chart_url = get_chart_url(s['code'], s.get('name'))
            change = f"{s['change_pct']:.1f}%" if s.get('change_pct') else ""
            return f"{i}. <a href=\"{chart_url}\">{s['name']}</a> ({s['code']}) {change}"
        
        await send_stock_list(
            f"💥 <b>曾涨停</b> (炸板, {len(burst_stocks)}只)",
            burst_stocks, format_burst
        )
        
        # 4. Send streak leaders (连板榜) - complete list
        def format_streak(i, s):
            chart_url = get_chart_url(s['code'], s.get('name'))
            return f"{i}. <a href=\"{chart_url}\">{s['name']}</a> ({s['code']}) - <b>{s['streak_count']}连板</b>"
        
        await send_stock_list(
            f"🔥 <b>连板榜</b> ({len(streaks)}只)",
            streaks, format_streak
        )
        
        # 5. Send strong stocks (强势股) - complete list
        def format_strong(i, s):
            chart_url = get_chart_url(s['code'], s.get('name'))
            return f"{i}. <a href=\"{chart_url}\">{s['name']}</a> ({s['code']}) - {s['limit_count']}次涨停"
        
        await send_stock_list(
            f"💪 <b>近期强势股</b> (7日, {len(strong)}只)",
            strong, format_strong
        )
        
        logger.info(f"Sent afternoon report: {len(sealed_stocks)} sealed, {len(burst_stocks)} burst, {len(streaks)} streaks, {len(strong)} strong")
    
    async def send_morning_price_update(self):
        """Send morning price update for yesterday's limit-up stocks.
        
        Shows ALL stocks sorted by real-time change percentage.
        Splits into multiple messages if content exceeds Telegram limit.
        """
        from app.core.bot import telegram_service
        
        logger.info("send_morning_price_update called")
        
        # Use LIMITUP_TARGET_GROUP for morning reports, fallback to STOCK_ALERT_CHANNEL
        target = settings.LIMITUP_TARGET_GROUP or settings.STOCK_ALERT_CHANNEL
        if not target:
            logger.warn("LIMITUP_TARGET_GROUP and STOCK_ALERT_CHANNEL not configured")
            return
        
        prices = await self.get_previous_limit_prices()
        if not prices:
            logger.warn("No prices available for morning update")
            return
        
        logger.info(f"Sending morning update with {len(prices)} stocks to {target}")
        
        # Sort by real-time change_pct descending
        prices.sort(key=lambda x: -x.get("change_pct", 0))
        
        now = datetime.now(CHINA_TZ)
        total = len(prices)
        
        # Build stock lines (one per stock)
        stock_lines = []
        for i, p in enumerate(prices, 1):
            change = p["change_pct"]
            icon = "🔴" if change > 5 else ("🟢" if change > 0 else "⚪")
            streak = f"[{p['limit_times']}板]"  # Always show 连板数
            chart_url = get_chart_url(p['code'], p['name'], context="morning")
            stock_lines.append(
                f"{i}. {icon} <a href=\"{chart_url}\">{p['name']}</a> {streak} {p['current_price']:.2f} ({change:+.2f}%)"
            )
        
        # Split into messages (max ~3800 chars to be safe)
        MAX_CHARS = 3800
        messages = []
        current_lines = [
            f"📈 <b>昨日涨停股实时</b> {now.strftime('%H:%M')} (共{total}只)",
            "━━━━━━━━━━━━━━━━━━━━━\n",
        ]
        current_len = sum(len(l) for l in current_lines)
        
        for line in stock_lines:
            line_len = len(line) + 1  # +1 for newline
            if current_len + line_len > MAX_CHARS:
                messages.append("\n".join(current_lines))
                current_lines = [f"📈 <b>昨日涨停股</b> (续)\n"]
                current_len = len(current_lines[0])
            current_lines.append(line)
            current_len += line_len
        
        if current_lines:
            messages.append("\n".join(current_lines))
        
        # Send all messages
        for msg in messages:
            await telegram_service.send_message(target, msg, parse_mode="html")
        
        logger.info(f"Sent morning price update at {now.strftime('%H:%M')} ({total} stocks, {len(messages)} messages)")
    
    # ─────────────────────────────────────────────────────────────────────────
    # Scheduler
    # ─────────────────────────────────────────────────────────────────────────
    
    async def _scheduler_loop(self):
        """Background scheduler for timed tasks."""
        # Morning report times: every minute from 9:15 to 10:00, skipping 9:25-9:30 (call auction)
        morning_times = []
        for hour in [9, 10]:
            for minute in range(60):
                if hour == 9 and minute < 15:
                    continue  # Start from 9:15
                if hour == 9 and 25 <= minute <= 30:
                    continue  # Skip 9:25-9:30 (call auction period)
                if hour == 10 and minute > 0:
                    continue  # Stop after 10:00
                morning_times.append(f"{hour:02d}:{minute:02d}")
        
        afternoon_time = "15:15"
        
        triggered_today = set()
        
        # On startup: immediately send report if we're in the window
        now = datetime.now(CHINA_TZ)
        time_str = now.strftime("%H:%M")
        if now.weekday() < 5:  # Weekday
            # Check if in morning window (9:15-10:00, excluding 9:25-9:30)
            hour, minute = now.hour, now.minute
            in_morning_window = (
                (hour == 9 and 15 <= minute < 25) or
                (hour == 9 and 30 < minute <= 59) or
                (hour == 10 and minute == 0)
            )
            if in_morning_window:
                logger.info(f"Startup in morning window ({time_str}), sending immediate report")
                asyncio.create_task(self.send_morning_price_update())
            
            # Check if at afternoon report time
            if time_str == afternoon_time:
                logger.info(f"Startup at afternoon report time ({time_str}), sending immediate report")
                asyncio.create_task(self.send_afternoon_report())
        
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
            
            # Check every 20 seconds (to not miss minute-based triggers)
            await asyncio.sleep(20)


# Singleton
limit_up_service = LimitUpService()
