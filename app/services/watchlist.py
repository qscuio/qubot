"""
User Watchlist Service (用户自选列表)

Manages user's personal stock watchlist with:
- Add/remove stocks
- Daily performance report at 17:00 (5 PM)
- Real-time price and performance since added
"""

import asyncio
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional

from app.core.logger import Logger
from app.core.database import db
from app.core.config import settings
from app.core.timezone import CHINA_TZ, china_now, china_today
from app.core.telegram_utils import chunk_message

logger = Logger("WatchlistService")


class WatchlistService:
    """Service for managing user stock watchlists."""
    
    def __init__(self):
        self.is_running = False
        self._scheduler_task = None
        self._scheduler_task = None
        self._unreachable_users = set()

    async def _send_chunked_message(self, bot, user_id: int, text: str, **kwargs):
        """Send long messages in chunks to avoid Telegram length limits."""
        chunks = chunk_message(text, max_length=3800)
        for chunk in chunks:
            await bot.send_message(user_id, chunk, **kwargs)

    def _is_unreachable_error(self, err: Exception) -> bool:
        msg = str(err).lower()
        return (
            "chat not found" in msg
            or "bot was blocked" in msg
            or "blocked by the user" in msg
            or "user is deactivated" in msg
            or "forbidden" in msg
        )
    
    async def start(self):
        """Start the watchlist scheduler."""
        if self.is_running:
            return
        
        self.is_running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("✅ Watchlist Service started")
    
    async def stop(self):
        """Stop the service."""
        self.is_running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        logger.info("Watchlist Service stopped")
    
    # ─────────────────────────────────────────────────────────────────────────
    # Watchlist Management
    # ─────────────────────────────────────────────────────────────────────────
    
    async def add_stock(self, user_id: int, code: str, name: str = None) -> Dict:
        """Add a stock to user's watchlist."""
        if not db.pool:
            raise ValueError("Database not connected")
        
        from app.services.data_provider.service import data_provider
        
        # Helper to get price info
        async def fetch_info():
            try:
                 quotes = await data_provider.get_quotes([code])
                 if quotes and code in quotes:
                     q = quotes[code]
                     return float(q['price']), q['name']
            except:
                pass
            return None, None

        add_price, stock_name = await fetch_info()
        
        # If name provided by user, use it
        if name:
            stock_name = name
        
        # Default price if missing
        if add_price is None:
            add_price = 0
            
        # Default name if missing
        if not stock_name:
            stock_name = code
        
        try:
            await db.pool.execute("""
                INSERT INTO user_watchlist (user_id, code, name, add_price, add_date)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (user_id, code) DO UPDATE SET
                    name = COALESCE(EXCLUDED.name, user_watchlist.name),
                    add_price = COALESCE(EXCLUDED.add_price, user_watchlist.add_price)
            """, user_id, code, stock_name, add_price, china_today())
            
            return {
                "code": code,
                "name": stock_name or code,
                "add_price": add_price,
                "success": True
            }
        except Exception as e:
            logger.error(f"Failed to add stock to watchlist: {e}")
            raise
    
    async def remove_stock(self, user_id: int, code: str) -> bool:
        """Remove a stock from user's watchlist."""
        if not db.pool:
            return False
        
        try:
            result = await db.pool.execute("""
                DELETE FROM user_watchlist WHERE user_id = $1 AND code = $2
            """, user_id, code)
            return "DELETE" in result
        except Exception as e:
            logger.error(f"Failed to remove stock: {e}")
            return False
            
    async def clear_watchlist(self, user_id: int) -> bool:
        """Remove ALL stocks from user's watchlist."""
        if not db.pool:
            return False
        
        try:
            result = await db.pool.execute("""
                DELETE FROM user_watchlist WHERE user_id = $1
            """, user_id)
            return "DELETE" in result
        except Exception as e:
            logger.error(f"Failed to clear watchlist: {e}")
            return False

    async def get_watchlist_performance(self, user_id: int) -> List[Dict]:
        """Get watchlist sorted by today's performance (descending)."""
        # Use realtime fetch to get latest data
        stocks = await self.get_watchlist_realtime(user_id)
        # Sort by today_change descending
        stocks.sort(key=lambda x: x.get('today_change', 0), reverse=True)
        return stocks
    
    async def get_watchlist(self, user_id: int) -> List[Dict]:
        """Get user's watchlist."""
        if not db.pool:
            return []
        
        rows = await db.pool.fetch("""
            SELECT code, name, add_price, add_date, created_at
            FROM user_watchlist
            WHERE user_id = $1
            ORDER BY created_at DESC
        """, user_id)
        
        return [dict(r) for r in rows]
    
    async def get_watchlist_with_prices(self, user_id: int) -> List[Dict]:
        """Get user's watchlist with prices from local DB (fast, cached)."""
        watchlist = await self.get_watchlist(user_id)
        
        if not watchlist:
            return []
        
        if not db.pool:
            return watchlist
        
        # Use local stock_history database for prices (fast, no remote API calls)
        result = []
        for stock in watchlist:
            code = stock['code']
            add_price = float(stock.get('add_price') or 0)
            stock_name = stock.get('name') or code
            
            current_price = 0
            today_change = 0
            
            try:
                # Get latest price from local stock_history table
                row = await db.pool.fetchrow("""
                    SELECT close, change_pct
                    FROM stock_history
                    WHERE code = $1
                    ORDER BY date DESC
                    LIMIT 1
                """, code)
                
                if row:
                    current_price = float(row['close'] or 0)
                    today_change = float(row['change_pct'] or 0)
                    
            except Exception as e:
                logger.warn(f"Failed to get price for {code}: {e}")
            
            # Calculate performance since added
            if add_price > 0 and current_price > 0:
                total_change = ((current_price - add_price) / add_price) * 100
            else:
                total_change = 0
            
            result.append({
                'code': code,
                'name': stock_name,
                'add_price': add_price,
                'add_date': stock.get('add_date'),
                'current_price': current_price,
                'today_change': today_change,
                'total_change': total_change,
            })
        
        return result

    async def get_watchlist_realtime(self, user_id: int) -> List[Dict]:
        """Get user's watchlist with real-time prices from AkShare.
        
        Only fetches prices for the specific stocks in user's watchlist.
        """
        watchlist = await self.get_watchlist(user_id)
        
        if not watchlist:
            return []
        
        from app.services.data_provider.service import data_provider
        
        # Codes to fetch
        codes = [item['code'] for item in watchlist]
        
        try:
            # Use DataProvider
            quotes = await data_provider.get_quotes(codes)
            
            if not quotes:
                # Fallback to local DB prices
                return await self.get_watchlist_with_prices(user_id)
           
            result = []
            for stock in watchlist:
                code = stock['code']
                add_price = float(stock.get('add_price') or 0)
                
                info = quotes.get(code, {})
                current_price = info.get('price', 0)
                today_change = info.get('change_pct', 0)
                stock_name = info.get('name') or stock.get('name') or code
                
                # Calculate performance since added
                if add_price > 0 and current_price > 0:
                    total_change = ((current_price - add_price) / add_price) * 100
                else:
                    total_change = 0
                
                result.append({
                    'code': code,
                    'name': stock_name,
                    'add_price': add_price,
                    'add_date': stock.get('add_date'),
                    'current_price': current_price,
                    'today_change': today_change,
                    'total_change': total_change,
                    'realtime': True,
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get real-time prices: {e}")
            return await self.get_watchlist_with_prices(user_id)

    
    # ─────────────────────────────────────────────────────────────────────────
    # Reports
    # ─────────────────────────────────────────────────────────────────────────
    
    async def generate_watchlist_report(self, user_id: int) -> str:
        """Generate watchlist performance report for a user."""
        stocks = await self.get_watchlist_with_prices(user_id)
        
        if not stocks:
            return "📋 <b>自选列表</b>\n━━━━━━━━━━━━━━━━━━━━━\n📭 暂无自选股票\n\n使用 /watch <代码> 添加"
        
        lines = [
            "📋 <b>自选列表</b>",
            "━━━━━━━━━━━━━━━━━━━━━",
            f"<i>共 {len(stocks)} 只</i>\n",
        ]
        
        # Sort by total change descending
        stocks.sort(key=lambda x: x.get('total_change', 0), reverse=True)
        
        for s in stocks:
            name = s.get('name', s['code'])
            code = s['code']
            current = s.get('current_price', 0)
            today = s.get('today_change', 0)
            total = s.get('total_change', 0)
            add_date = s.get('add_date')
            
            # Icon based on total performance
            if total > 5:
                icon = "🔴"
            elif total > 0:
                icon = "🟢"
            elif total > -5:
                icon = "⚪"
            else:
                icon = "🟢"
            
            date_str = add_date.strftime('%m/%d') if add_date else ""
            
            lines.append(
                f"{icon} <b>{name}</b> ({code})\n"
                f"   💰 {current:.2f} | 今日 {today:+.2f}% | 累计 {total:+.2f}%\n"
                f"   <i>加入: {date_str}</i>"
            )
        
        return "\n".join(lines)
    
    async def send_daily_reports(self):
        """Send daily watchlist reports to all users at 17:00."""
        from app.core.bot import telegram_service
        
        if not db.pool:
            return
        
        # Get all users with watchlist
        users = await db.pool.fetch("""
            SELECT DISTINCT user_id FROM user_watchlist
        """)
        
        for row in users:
            user_id = row['user_id']
            if user_id in self._unreachable_users:
                continue
            try:
                report = await self.generate_watchlist_report(user_id)
                
                # Send to user directly (not to channel)
                # Using the crawler bot to send
                from app.bots.registry import get_bot
                bot = get_bot("crawler")
                if bot:
                    await self._send_chunked_message(bot, user_id, report, parse_mode="HTML")
                    logger.info(f"Sent watchlist report to user {user_id}")
                    
            except Exception as e:
                if self._is_unreachable_error(e):
                    self._unreachable_users.add(user_id)
                logger.warn(f"Failed to send report to {user_id}: {e}")
            
            # Small delay between users
            await asyncio.sleep(0.5)
    
    # ─────────────────────────────────────────────────────────────────────────
    # Scheduler
    # ─────────────────────────────────────────────────────────────────────────
    
    async def send_intraday_reports(self):
        """Send intraday watchlist performance reports."""
        from app.bots.registry import get_bot
        from app.core.stock_links import get_chart_url
        
        if not db.pool:
            return
            
        # Get all users with watchlist
        users = await db.pool.fetch("SELECT DISTINCT user_id FROM user_watchlist")
        
        for row in users:
            user_id = row['user_id']
            if user_id in self._unreachable_users:
                continue
            try:
                stocks = await self.get_watchlist_performance(user_id)
                if not stocks:
                    continue
                    
                # Format report
                lines = [
                    f"⏱️ <b>自选盯盘</b> ({china_now().strftime('%H:%M')})",
                    "━━━━━━━━━━━━━━━━━━━━━"
                ]
                
                # Sort by change descending (Best to Worst)
                stocks.sort(key=lambda x: x.get('today_change', 0), reverse=True)
                
                for s in stocks:
                    name = s.get('name', s['code'])
                    code = s['code']
                    change = s.get('today_change', 0)
                    
                    if change > 0:
                        icon = "🔴" 
                    elif change < 0:
                        icon = "🟢" 
                    else:
                        icon = "⚪"
                    
                    url = get_chart_url(code, name, context="watchlist_alert")
                    lines.append(f"{icon} <a href=\"{url}\">{name}</a>: {change:+.2f}%")

                report = "\n".join(lines)
                
                bot = get_bot("crawler")
                if bot:
                    await self._send_chunked_message(
                        bot,
                        user_id,
                        report,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                    
            except Exception as e:
                if self._is_unreachable_error(e):
                    self._unreachable_users.add(user_id)
                logger.warn(f"Failed to send intraday report to {user_id}: {e}")
            
            await asyncio.sleep(0.5)

    async def send_closing_reports(self):
        """Send daily closing performance report."""
        from app.bots.registry import get_bot
        from app.core.stock_links import get_chart_url
        
        if not db.pool:
            return
            
        users = await db.pool.fetch("SELECT DISTINCT user_id FROM user_watchlist")
        
        for row in users:
            user_id = row['user_id']
            if user_id in self._unreachable_users:
                continue
            try:
                stocks = await self.get_watchlist_performance(user_id)
                if not stocks:
                    continue
                    
                lines = [
                    "🏁 <b>自选收盘日报</b>",
                    "━━━━━━━━━━━━━━━━━━━━━"
                ]
                
                # Sort by change descending
                stocks.sort(key=lambda x: x.get('today_change', 0), reverse=True)
                
                for s in stocks:
                    name = s.get('name', s['code'])
                    code = s['code']
                    change = s.get('today_change', 0)
                    price = s.get('current_price', 0)
                    
                    if change > 0:
                        icon = "🔴" 
                    elif change < 0:
                        icon = "🟢" 
                    else:
                        icon = "⚪"
                        
                    url = get_chart_url(code, name, context="watchlist_daily")
                    lines.append(f"{icon} <a href=\"{url}\">{name}</a>: {price} ({change:+.2f}%)")
                    
                report = "\n".join(lines)
                
                bot = get_bot("crawler")
                if bot:
                    await self._send_chunked_message(
                        bot,
                        user_id,
                        report,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                    
            except Exception as e:
                if self._is_unreachable_error(e):
                    self._unreachable_users.add(user_id)
                logger.warn(f"Failed to send closing report to {user_id}: {e}")
            
            await asyncio.sleep(0.5)

    # ─────────────────────────────────────────────────────────────────────────
    # Scheduler
    # ─────────────────────────────────────────────────────────────────────────
    
    async def _scheduler_loop(self):
        """Background scheduler for watchlist reports."""
        closing_time = "15:05"
        
        triggered_today = set()
        last_intraday_min = -1
        
        while self.is_running:
            try:
                now = china_now()
                time_str = now.strftime("%H:%M")
                date_str = now.strftime("%Y-%m-%d")
                
                if time_str == "00:00":
                    triggered_today.clear()
                
                # 1. Closing Report (15:05)
                closing_key = f"{date_str}_closing"
                if now.weekday() < 5 and time_str == closing_time and closing_key not in triggered_today:
                    triggered_today.add(closing_key)
                    asyncio.create_task(self.send_closing_reports())
                
                # 2. Intraday Report (Every 10 mins during trading)
                # Trading hours: 09:30-11:30, 13:00-15:00
                is_trading = (
                    (now.hour == 9 and now.minute >= 30) or
                    (now.hour == 10) or
                    (now.hour == 11 and now.minute <= 30) or
                    (now.hour >= 13 and now.hour < 15)
                )
                
                if now.weekday() < 5 and is_trading:
                    if now.minute % 10 == 0 and now.minute != last_intraday_min:
                        last_intraday_min = now.minute
                        asyncio.create_task(self.send_intraday_reports())
                    
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
            
            await asyncio.sleep(30)


# Singleton
watchlist_service = WatchlistService()
