
import asyncio
from typing import List, Dict, Optional
from datetime import datetime

from app.core.logger import Logger
from app.core.database import db
from app.core.timezone import china_now, china_today

logger = Logger("PortfolioService")

class PortfolioService:
    """Service for managing user's real stock portfolio."""
    
    def __init__(self):
        self.is_running = False
        self._scheduler_task = None
        self._ak = None
        # Cache for alert notifications to avoid spamming
        # Key: f"{user_id}_{code}_{type}_{date}"
        self._alert_cache = set()
    
    def _get_akshare(self):
        if self._ak is None:
            try:
                import akshare as ak
                self._ak = ak
            except ImportError:
                logger.error("AkShare not installed")
                return None
        return self._ak

    async def start(self):
        """Start the portfolio monitor."""
        if self.is_running:
            return
        self.is_running = True
        self._scheduler_task = asyncio.create_task(self._monitor_loop())
        logger.info("✅ Portfolio Service started")

    async def stop(self):
        """Stop the service."""
        self.is_running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        logger.info("Portfolio Service stopped")

    # ─────────────────────────────────────────────────────────────────────────
    # Management
    # ─────────────────────────────────────────────────────────────────────────

    async def add_position(self, user_id: int, code: str, cost_price: float, shares: int) -> bool:
        """Add or update a position."""
        if not db.pool:
            return False
        
        try:
            await db.pool.execute("""
                INSERT INTO user_portfolio (user_id, code, cost_price, shares)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id, code) DO UPDATE SET
                    cost_price = EXCLUDED.cost_price,
                    shares = EXCLUDED.shares
            """, user_id, code, cost_price, shares)
            return True
        except Exception as e:
            logger.error(f"Failed to add position: {e}")
            return False

    async def remove_position(self, user_id: int, code: str) -> bool:
        """Remove a position."""
        if not db.pool:
            return False
        
        try:
            result = await db.pool.execute("""
                DELETE FROM user_portfolio WHERE user_id = $1 AND code = $2
            """, user_id, code)
            return "DELETE" in result
        except Exception as e:
            logger.error(f"Failed to remove position: {e}")
            return False

    async def get_portfolio(self, user_id: int) -> List[Dict]:
        """Get user's portfolio with real-time data."""
        if not db.pool:
            return []
            
        # Get holdings
        rows = await db.pool.fetch("""
            SELECT code, cost_price, shares 
            FROM user_portfolio 
            WHERE user_id = $1
        """, user_id)
        
        if not rows:
            return []
            
        holdings = [dict(r) for r in rows]
        
        # Fetch real-time prices
        ak = self._get_akshare()
        if not ak:
            return holdings
            
        try:
            # Batch fetch all A-shares
            df = await asyncio.to_thread(ak.stock_zh_a_spot_em)
            if df is None or df.empty:
                return holdings
                
            price_map = {}
            for _, row in df.iterrows():
                code = str(row.get('代码', ''))
                price_map[code] = {
                    'current_price': float(row.get('最新价', 0) or 0),
                    'change_pct': float(row.get('涨跌幅', 0) or 0),
                    'name': str(row.get('名称', '')),
                }
            
            result = []
            for h in holdings:
                code = h['code']
                info = price_map.get(code, {})
                
                current = info.get('current_price', 0)
                cost = float(h['cost_price'])
                shares = h['shares']
                
                # Calculate P&L
                market_value = current * shares
                profit = (current - cost) * shares
                profit_pct = (current - cost) / cost * 100 if cost > 0 else 0
                
                h.update({
                    'name': info.get('name', code),
                    'current_price': current,
                    'today_change': info.get('change_pct', 0),
                    'market_value': market_value,
                    'profit': profit,
                    'profit_pct': profit_pct
                })
                result.append(h)
                
            return result
            
        except Exception as e:
            logger.error(f"Failed to fetch portfolio prices: {e}")
            return holdings

    # ─────────────────────────────────────────────────────────────────────────
    # Monitoring
    # ─────────────────────────────────────────────────────────────────────────

    async def _monitor_loop(self):
        """Monitor portfolio for alerts."""
        while self.is_running:
            try:
                now = china_now()
                
                # Clear cache at midnight
                if now.hour == 0 and now.minute == 0:
                    self._alert_cache.clear()
                
                # Check alerts during trading hours
                is_trading = (
                    (now.hour == 9 and now.minute >= 30) or
                    (now.hour == 10) or
                    (now.hour == 11 and now.minute <= 30) or
                    (now.hour >= 13 and now.hour < 15)
                )
                
                if now.weekday() < 5 and is_trading:
                    await self._check_alerts()
                    
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
            
            await asyncio.sleep(60) # Check every minute

    async def _check_alerts(self):
        """Check all portfolios for alert conditions."""
        if not db.pool:
            return

        # Get all users
        users = await db.pool.fetch("SELECT DISTINCT user_id FROM user_portfolio")
        
        for row in users:
            user_id = row['user_id']
            portfolio = await self.get_portfolio(user_id)
            
            for stock in portfolio:
                if 'today_change' not in stock:
                    continue
                    
                change = stock['today_change']
                code = stock['code']
                name = stock['name']
                today_str = china_today().strftime("%Y-%m-%d")
                
                # Alert Rules: > 5% or < -2%
                alert_type = None
                if change > 5:
                    alert_type = "surge"
                elif change < -2:
                    alert_type = "drop"
                
                if alert_type:
                    key = f"{user_id}_{code}_{alert_type}_{today_str}"
                    if key not in self._alert_cache:
                        self._alert_cache.add(key)
                        await self._send_alert(user_id, stock, alert_type)

    async def _send_alert(self, user_id: int, stock: Dict, alert_type: str):
        """Send alert message to user."""
        from app.bots.registry import get_bot
        bot = get_bot("crawler")
        if not bot:
            return
            
        emoji = "🚀" if alert_type == "surge" else "📉"
        action = "大涨" if alert_type == "surge" else "下跌"
        
        msg = (
            f"{emoji} <b>持仓预警: {stock['name']}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"当前涨跌: <b>{stock['today_change']:+.2f}%</b>\n"
            f"现价: {stock['current_price']:.2f}\n"
            f"成本: {stock['cost_price']:.2f}\n"
            f"持仓盈亏: {stock['profit_pct']:+.2f}%"
        )
        
        try:
            await bot.send_message(user_id, msg, parse_mode="HTML")
        except Exception as e:
            logger.warn(f"Failed to send alert to {user_id}: {e}")

portfolio_service = PortfolioService()
