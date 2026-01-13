"""
打板 (Limit-Up Board) Trading Simulator

Simulates 打板 trading with:
- 100K initial capital
- Max 2 positions (concentrated bets)
- Buy at limit-up, aim for next-day continuation
- Sell rules: 连板 continuation, 炸板 cut loss, -5% stop loss
"""

import asyncio
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional

from app.core.logger import Logger
from app.core.database import db
from app.core.config import settings
from app.core.timezone import CHINA_TZ, china_now, china_today

logger = Logger("DabanSimulator")


# Trading rules - 打板 specific
INITIAL_CAPITAL = 100000     # 10万初始资金
MAX_POSITIONS = 2            # Max 2 stocks (concentrated bets)
STOP_LOSS_OPEN = -5.0        # Stop loss if opens below -5%
TRAILING_PROFIT = 5.0        # If up but not limit, trail from +5%
TRAILING_DROP = 3.0          # Trailing sell if drops this much from intraday high
LIMIT_PERCENT_MAIN = 10.0    # Main board limit = 10%
LIMIT_PERCENT_STAR = 20.0    # 科创板/创业板 limit = 20%
MIN_SCORE = 65               # Minimum score to consider buying
LIMIT_UP_TOLERANCE = 0.5     # Tolerance for limit-up checks


class DabanSimulator:
    """Simulator for 打板 trading strategy."""
    
    def __init__(self):
        self.is_running = False
        self._scheduler_task = None
        self._ak = None
        self._notify_callback = None
        self._last_date = None  # For date change detection
        self._triggered_today = set()
    
    def set_notify_callback(self, callback):
        """Set callback function for sending notifications."""
        self._notify_callback = callback
    
    async def _notify(self, message: str):
        """Send notification."""
        logger.info(f"[NOTIFY] {message}")
        if self._notify_callback:
            try:
                await self._notify_callback(message)
            except Exception as e:
                logger.error(f"Notification failed: {e}")
    
    def _get_akshare(self):
        """Lazy load akshare module."""
        if self._ak is None:
            try:
                import akshare as ak
                self._ak = ak
            except ImportError:
                logger.error("AkShare not installed")
                return None
        return self._ak
    
    async def start(self):
        """Start the 打板 simulator."""
        if self.is_running:
            return
        await self._ensure_tables()
        await self._ensure_account()
        self.is_running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("✅ 打板 Simulator started")
    
    async def stop(self):
        """Stop the simulator."""
        self.is_running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        logger.info("打板 Simulator stopped")
    
    async def _ensure_tables(self):
        """Create database tables if not exists."""
        if not db.pool:
            return
        
        try:
            await db.pool.execute("""
                CREATE TABLE IF NOT EXISTS daban_account (
                    id SERIAL PRIMARY KEY,
                    initial_capital DECIMAL(12,2) DEFAULT 100000,
                    current_cash DECIMAL(12,2) DEFAULT 100000,
                    total_value DECIMAL(12,2) DEFAULT 100000,
                    total_profit DECIMAL(12,2) DEFAULT 0,
                    total_trades INT DEFAULT 0,
                    win_count INT DEFAULT 0,
                    loss_count INT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            await db.pool.execute("""
                CREATE TABLE IF NOT EXISTS daban_portfolio (
                    id SERIAL PRIMARY KEY,
                    code VARCHAR(10),
                    name VARCHAR(50),
                    status VARCHAR(20) DEFAULT 'holding',
                    buy_date DATE,
                    buy_price DECIMAL(10,2),
                    buy_amount DECIMAL(12,2),
                    shares INT,
                    board_type VARCHAR(20),
                    daban_score DECIMAL(5,2),
                    limit_pct DECIMAL(4,2),
                    sell_date DATE,
                    sell_price DECIMAL(10,2),
                    sell_reason VARCHAR(50),
                    profit_loss DECIMAL(12,2),
                    profit_pct DECIMAL(6,2),
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            logger.info("✅ 打板 database tables initialized")
        except Exception as e:
            logger.error(f"Failed to create tables: {e}")
    
    async def _ensure_account(self):
        """Ensure account exists."""
        if not db.pool:
            return
        
        row = await db.pool.fetchrow("SELECT id FROM daban_account WHERE id = 1")
        if not row:
            await db.pool.execute("""
                INSERT INTO daban_account (id, initial_capital, current_cash, total_value)
                VALUES (1, $1, $1, $1)
            """, INITIAL_CAPITAL)
            logger.info(f"Created 打板 account with {INITIAL_CAPITAL} initial capital")

    async def _get_spot_quotes(self, codes: List[str]) -> Dict[str, Dict]:
        """Fetch spot quotes for given codes."""
        if not codes:
            return {}
        ak = self._get_akshare()
        if not ak:
            return {}

        try:
            df = await asyncio.to_thread(ak.stock_zh_a_spot_em)
            if df is None or df.empty:
                return {}

            df = df[df['代码'].isin(codes)]
            quotes = {}
            for _, row in df.iterrows():
                code = str(row.get('代码', ''))
                quotes[code] = {
                    'price': float(row.get('最新价', 0) or 0),
                    'open': float(row.get('今开', 0) or 0),
                    'high': float(row.get('最高', 0) or 0),
                    'low': float(row.get('最低', 0) or 0),
                    'change_pct': float(row.get('涨跌幅', 0) or 0),
                }
            return quotes
        except Exception as e:
            logger.error(f"Failed to fetch spot quotes: {e}")
            return {}

    async def _get_limit_up_codes(self) -> set:
        """Fetch current limit-up codes."""
        ak = self._get_akshare()
        if not ak:
            return set()

        try:
            date_str = china_today().strftime("%Y%m%d")
            df = await asyncio.to_thread(ak.stock_zt_pool_em, date=date_str)
            if df is None or df.empty:
                return set()
            return {str(code) for code in df['代码'].tolist() if code}
        except Exception as e:
            logger.warn(f"Failed to fetch limit-up pool: {e}")
            return set()
    
    async def get_account(self) -> Optional[Dict]:
        """Get account details."""
        if not db.pool:
            return None
        
        row = await db.pool.fetchrow("SELECT * FROM daban_account WHERE id = 1")
        return dict(row) if row else None
    
    async def get_current_positions(self) -> List[Dict]:
        """Get all current holding positions."""
        if not db.pool:
            return []
        
        rows = await db.pool.fetch("""
            SELECT * FROM daban_portfolio
            WHERE status = 'holding'
            ORDER BY buy_date DESC
        """)
        return [dict(r) for r in rows]
    
    async def get_trade_history(self, limit: int = 20) -> List[Dict]:
        """Get recent trade history."""
        if not db.pool:
            return []
        
        rows = await db.pool.fetch("""
            SELECT * FROM daban_portfolio
            WHERE status = 'sold'
            ORDER BY sell_date DESC
            LIMIT $1
        """, limit)
        return [dict(r) for r in rows]
    
    async def buy_stock(self, code: str, name: str, price: float, 
                       board_type: str, score: float, limit_pct: float) -> bool:
        """Execute a buy order for 打板."""
        if not db.pool:
            return False
        
        account = await self.get_account()
        if not account:
            return False
        
        available_cash = float(account['current_cash'])
        positions = await self.get_current_positions()
        
        if len(positions) >= MAX_POSITIONS:
            logger.info(f"Cannot buy {code}: max positions reached")
            return False
        
        # Calculate position size (split evenly among max positions)
        position_size = min(available_cash, INITIAL_CAPITAL / MAX_POSITIONS)
        
        if position_size < 1000:
            logger.info(f"Cannot buy {code}: insufficient cash")
            return False
        
        # Calculate shares (round to 100 - lot size)
        shares = int(position_size / price / 100) * 100
        if shares < 100:
            return False
        
        buy_amount = shares * price
        
        try:
            async with db.pool.acquire() as conn:
                # Deduct cash
                result = await conn.execute("""
                    UPDATE daban_account
                    SET current_cash = current_cash - $1, updated_at = NOW()
                    WHERE id = 1 AND current_cash >= $1
                """, buy_amount)
                
                if 'UPDATE 0' in result:
                    return False
                
                # Add position
                await conn.execute("""
                    INSERT INTO daban_portfolio 
                    (code, name, status, buy_date, buy_price, buy_amount, shares, 
                     board_type, daban_score, limit_pct)
                    VALUES ($1, $2, 'holding', $3, $4, $5, $6, $7, $8, $9)
                """, code, name, china_today(), price, buy_amount, shares, 
                    board_type, score, limit_pct)
            
            await self._notify(
                f"🎯 打板买入 {name}({code})\n"
                f"价格: ¥{price:.2f} | {shares}股\n"
                f"金额: ¥{buy_amount:,.0f}\n"
                f"{board_type} | 评分: {score:.1f}"
            )
            
            logger.info(f"打板 bought {name}({code}) {shares}股 at {price:.2f}")
            return True
            
        except Exception as e:
            logger.error(f"打板 buy failed for {code}: {e}")
            return False
    
    async def sell_stock(self, position_id: int, sell_price: float, reason: str) -> bool:
        """Sell a position."""
        if not db.pool:
            return False
        
        try:
            async with db.pool.acquire() as conn:
                pos = await conn.fetchrow("""
                    SELECT * FROM daban_portfolio WHERE id = $1
                """, position_id)
                
                if not pos:
                    return False
                
                buy_price = float(pos['buy_price'])
                shares = pos['shares']
                profit_loss = (sell_price - buy_price) * shares
                profit_pct = (sell_price - buy_price) / buy_price * 100
                sell_amount = sell_price * shares
                
                # Update position
                await conn.execute("""
                    UPDATE daban_portfolio
                    SET status = 'sold',
                        sell_date = $1,
                        sell_price = $2,
                        sell_reason = $3,
                        profit_loss = $4,
                        profit_pct = $5
                    WHERE id = $6
                """, china_today(), sell_price, reason, profit_loss, profit_pct, position_id)
                
                # Update account
                await conn.execute("""
                    UPDATE daban_account
                    SET current_cash = current_cash + $1,
                        total_profit = total_profit + $2,
                        total_trades = total_trades + 1,
                        win_count = win_count + $3,
                        loss_count = loss_count + $4,
                        updated_at = NOW()
                    WHERE id = 1
                """, sell_amount, profit_loss, 
                    1 if profit_loss > 0 else 0, 
                    1 if profit_loss <= 0 else 0)
                
                # Translate reason
                reason_cn = {
                    'limit_continue': '连板成功后卖出',
                    'limit_fail': '连板失败',
                    'burst': '炸板止损',
                    'stop_loss': '开盘止损',
                    'trailing': '回落止盈',
                    'manual': '手动'
                }.get(reason, reason)
                
                emoji = '🟢' if profit_loss >= 0 else '🔴'
                await self._notify(
                    f"{emoji} 打板卖出 {pos['name']}({pos['code']})\n"
                    f"价格: ¥{sell_price:.2f} | {shares}股\n"
                    f"盈亏: ¥{profit_loss:+,.0f} ({profit_pct:+.2f}%)\n"
                    f"原因: {reason_cn}"
                )
                
                logger.info(f"打板 sold {pos['name']} at {sell_price:.2f}, P&L: {profit_loss:+.2f}")
                return True
                
        except Exception as e:
            logger.error(f"打板 sell failed: {e}")
            return False
    
    async def afternoon_scan_buy(self):
        """Scan and buy at end of day (14:45-15:00)."""
        from app.services.daban_service import daban_service
        
        positions = await self.get_current_positions()
        if len(positions) >= MAX_POSITIONS:
            logger.info("打板 positions full, skipping scan")
            return
        
        held_codes = {p['code'] for p in positions}
        
        # Get top recommendations
        candidates = await daban_service.get_buy_recommendations(top_n=5)
        
        if not candidates:
            await self._notify("📭 今日无高评分打板候选")
            return
        
        slots_available = MAX_POSITIONS - len(positions)
        bought = 0
        
        for c in candidates:
            if c['code'] in held_codes:
                continue
            if c['score'] < MIN_SCORE:
                continue
            
            success = await self.buy_stock(
                code=c['code'],
                name=c['name'],
                price=c['price'],
                board_type=c['board_type'],
                score=c['score'],
                limit_pct=c['limit_pct']
            )
            
            if success:
                bought += 1
                held_codes.add(c['code'])
                if bought >= slots_available:
                    break
        
        if bought == 0:
            await self._notify("📭 今日未买入打板标的")
    
    async def morning_check_positions(self):
        """Check positions at morning open (9:35)."""
        positions = await self.get_current_positions()
        if not positions:
            return
        
        await self._notify("🔔 打板持仓早盘检查...")

        try:
            codes = [p['code'] for p in positions]
            quotes = await self._get_spot_quotes(codes)
            if not quotes:
                return

            limit_up_codes = await self._get_limit_up_codes()

            for pos in positions:
                code = pos['code']
                current = quotes.get(code)
                if not current:
                    continue

                buy_price = float(pos['buy_price'])
                limit_pct = float(pos['limit_pct'])
                open_price = current['open'] or current['price']
                current_price = current['price']
                open_pct = (open_price - buy_price) / buy_price * 100
                current_pct = (current_price - buy_price) / buy_price * 100

                is_limit = code in limit_up_codes or current['change_pct'] >= limit_pct - LIMIT_UP_TOLERANCE

                # Check if hit limit again (连板成功 - hold)
                if is_limit:
                    await self._notify(
                        f"🚀 {pos['name']} 继续涨停! 持仓继续"
                    )
                    continue

                # Check stop loss at open
                if open_pct <= STOP_LOSS_OPEN:
                    await self.sell_stock(pos['id'], current_price, 'stop_loss')
                    continue

                # Check if failed to continue and has profit
                if current_pct >= TRAILING_PROFIT:
                    await self._notify(
                        f"📈 {pos['name']} 盈利 {current_pct:.1f}% 但未封板，观察中..."
                    )

        except Exception as e:
            logger.error(f"Morning check failed: {e}")

    async def afternoon_check_positions(self):
        """Check positions near close for limit continuation or burst."""
        positions = await self.get_current_positions()
        if not positions:
            return

        await self._notify("🔔 打板持仓尾盘检查...")

        try:
            codes = [p['code'] for p in positions]
            quotes = await self._get_spot_quotes(codes)
            if not quotes:
                return

            limit_up_codes = await self._get_limit_up_codes()

            for pos in positions:
                if pos['buy_date'] == china_today():
                    # Avoid selling same-day buys
                    continue

                code = pos['code']
                current = quotes.get(code)
                if not current:
                    continue

                buy_price = float(pos['buy_price'])
                limit_pct = float(pos['limit_pct'])
                current_price = current['price']
                current_pct = (current_price - buy_price) / buy_price * 100
                high_price = current['high'] or current_price
                high_pct = (high_price - buy_price) / buy_price * 100

                is_limit = code in limit_up_codes or current['change_pct'] >= limit_pct - LIMIT_UP_TOLERANCE
                if is_limit:
                    continue

                hit_limit = high_pct >= limit_pct - LIMIT_UP_TOLERANCE
                if hit_limit:
                    await self.sell_stock(pos['id'], current_price, 'burst')
                    continue

                if high_pct >= TRAILING_PROFIT and (high_pct - current_pct) >= TRAILING_DROP:
                    await self.sell_stock(pos['id'], current_price, 'trailing')
                    continue

                await self.sell_stock(pos['id'], current_price, 'limit_fail')

        except Exception as e:
            logger.error(f"Afternoon check failed: {e}")
    
    async def get_statistics(self) -> Dict:
        """Get simulator statistics."""
        account = await self.get_account()
        if not account:
            return {}
        
        positions = await self.get_current_positions()
        
        # Calculate unrealized P&L
        unrealized_pnl = 0
        total_market_value = 0
        quotes = {}
        if positions:
            quotes = await self._get_spot_quotes([p['code'] for p in positions])

        for pos in positions:
            quote = quotes.get(pos['code'])
            if quote:
                current_price = quote['price']
                buy_price = float(pos['buy_price'])
                unrealized_pnl += (current_price - buy_price) * pos['shares']
                total_market_value += current_price * pos['shares']
            else:
                total_market_value += float(pos['buy_amount'])
        
        total_profit = float(account['total_profit']) + unrealized_pnl
        total_trades = account['total_trades']
        win_rate = account['win_count'] / total_trades * 100 if total_trades > 0 else 0
        total_value = float(account['current_cash']) + total_market_value

        if db.pool:
            try:
                await db.pool.execute("""
                    UPDATE daban_account
                    SET total_value = $1, updated_at = NOW()
                    WHERE id = 1
                """, total_value)
            except Exception as e:
                logger.warn(f"Failed to update account value: {e}")
        
        return {
            'initial_capital': float(account['initial_capital']),
            'current_cash': float(account['current_cash']),
            'total_value': float(total_value),
            'total_profit': round(total_profit, 2),
            'total_return_pct': round(total_profit / float(account['initial_capital']) * 100, 2),
            'realized_profit': float(account['total_profit']),
            'unrealized_profit': round(unrealized_pnl, 2),
            'total_trades': total_trades,
            'win_count': account['win_count'],
            'loss_count': account['loss_count'],
            'win_rate': round(win_rate, 2),
            'current_positions': len(positions),
        }
    
    async def generate_portfolio_report(self) -> str:
        """Generate portfolio report for bot."""
        positions = await self.get_current_positions()
        
        if not positions:
            return "🎯 <b>打板持仓</b>\n\n当前无持仓"
        
        lines = ["🎯 <b>打板持仓</b>\n"]
        
        quotes = await self._get_spot_quotes([p['code'] for p in positions])
        total_pnl = 0
        
        for i, pos in enumerate(positions, 1):
            current_price = float(pos['buy_price'])  # Default
            pnl_pct = 0
            
            quote = quotes.get(pos['code'])
            if quote:
                current_price = quote['price']
                buy_price = float(pos['buy_price'])
                pnl_pct = (current_price - buy_price) / buy_price * 100
                total_pnl += (current_price - buy_price) * pos['shares']

            emoji = '🟢' if pnl_pct >= 0 else '🔴'
            lines.append(
                f"{i}. <b>{pos['name']}</b> ({pos['code']})\n"
                f"   {pos['board_type']} | 评分: {pos['daban_score']:.1f}\n"
                f"   {emoji} {pnl_pct:+.2f}% | 现价: ¥{current_price:.2f}"
            )
        
        lines.append(f"\n💰 持仓盈亏: ¥{total_pnl:+,.0f}")
        return "\n".join(lines)
    
    async def generate_stats_report(self) -> str:
        """Generate statistics report for bot."""
        stats = await self.get_statistics()
        
        if not stats:
            return "📊 <b>打板统计</b>\n\n无数据"
        
        return (
            f"📊 <b>打板统计</b>\n\n"
            f"💰 初始资金: ¥{stats['initial_capital']:,.0f}\n"
            f"💵 当前现金: ¥{stats['current_cash']:,.0f}\n\n"
            f"📈 总收益: ¥{stats['total_profit']:+,.0f} ({stats['total_return_pct']:+.2f}%)\n"
            f"   - 已实现: ¥{stats['realized_profit']:+,.0f}\n"
            f"   - 未实现: ¥{stats['unrealized_profit']:+,.0f}\n\n"
            f"🎯 交易统计:\n"
            f"   - 总交易: {stats['total_trades']}笔\n"
            f"   - 盈利: {stats['win_count']}笔\n"
            f"   - 亏损: {stats['loss_count']}笔\n"
            f"   - 胜率: {stats['win_rate']:.1f}%\n\n"
            f"📦 当前持仓: {stats['current_positions']}/{MAX_POSITIONS}"
        )
    
    async def _scheduler_loop(self):
        """
        Background scheduler for 打板 operations.
        
        Uses time window and date change for reliable triggering.
        """
        schedules = [
            (9, 35, 'morning_check'),   # Morning check at 09:35
            (14, 45, 'afternoon_check'),  # Close check at 14:45
            (14, 50, 'afternoon_scan'),  # Afternoon scan at 14:50
        ]
        
        while self.is_running:
            try:
                now = china_now()
                current_date = now.strftime("%Y-%m-%d")
                
                # Date change detection - clear triggered set
                if self._last_date and self._last_date != current_date:
                    self._triggered_today.clear()
                    logger.debug("Cleared triggered set for new day")
                self._last_date = current_date
                
                # Skip weekends
                if now.weekday() >= 5:
                    await asyncio.sleep(60)
                    continue
                
                for sched_hour, sched_min, task in schedules:
                    key = f"{current_date}_{task}"
                    
                    if key not in self._triggered_today:
                        # Check if within 1 minute window of target time
                        target_time = now.replace(hour=sched_hour, minute=sched_min, second=0, microsecond=0)
                        time_diff = abs((now - target_time).total_seconds())
                        
                        if time_diff < 60:  # Within 1 minute window
                            self._triggered_today.add(key)
                            logger.info(f"Triggering 打板 task: {task}")
                            
                            if task == 'morning_check':
                                await self.morning_check_positions()
                            elif task == 'afternoon_scan':
                                await self.afternoon_scan_buy()
                            elif task == 'afternoon_check':
                                await self.afternoon_check_positions()
                
            except Exception as e:
                logger.error(f"打板 scheduler error: {e}")
            
            await asyncio.sleep(30)


# Singleton
daban_simulator = DabanSimulator()
