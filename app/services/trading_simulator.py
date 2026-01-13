"""
Trading Simulator Service (模拟交易服务)

Automated trading simulation with:
- Daily stock scanning for buy signals after market close
- Intraday T+0 trading using existing positions
- Trailing stop (移动止盈) strategy
- Operation notifications to user
- 1,000,000 RMB initial capital, max 5 positions
"""

import asyncio
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Optional, Tuple

from app.core.logger import Logger
from app.core.database import db
from app.core.config import settings
from app.core.timezone import CHINA_TZ, china_now, china_today

logger = Logger("TradingSimulator")


# Trading rules
MAX_POSITIONS = 5           # Maximum number of stocks to hold (reduced from 10)
TRAILING_STOP_TRIGGER = 8.0 # Start trailing stop after 8% profit
TRAILING_STOP_PCT = 3.0     # Trailing stop: sell if drops 3% from peak
STOP_LOSS_PCT = 5.0         # Fixed stop loss: sell when loss >= 5%
MAX_HOLDING_DAYS = 20       # Sell if no profit after 20 days
INITIAL_CAPITAL = 1000000   # 100万初始资金
T_TRADE_THRESHOLD = 2.0     # Do T when intraday swing >= 2%


class TradingSimulator:
    """Service for automated trading simulation."""
    
    def __init__(self):
        self.is_running = False
        self._scheduler_task = None
        self._ak = None
        self._pd = None
        self._notify_callback = None  # Callback for user notifications
    
    def set_notify_callback(self, callback):
        """Set callback function for sending notifications to user."""
        self._notify_callback = callback
    
    async def _notify(self, message: str):
        """Send notification to user."""
        logger.info(f"[NOTIFY] {message}")
        if self._notify_callback:
            try:
                await self._notify_callback(message)
            except Exception as e:
                logger.error(f"Notification failed: {e}")
    
    def _get_libs(self):
        """Lazy load akshare and pandas."""
        if self._ak is None:
            import akshare as ak
            import pandas as pd
            self._ak = ak
            self._pd = pd
        return self._ak, self._pd
    
    async def start(self):
        """Start the trading simulator scheduler."""
        if self.is_running:
            return
        self.is_running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("✅ Trading Simulator started")
    
    async def stop(self):
        """Stop the service."""
        self.is_running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        logger.info("Trading Simulator stopped")
    
    async def _scheduler_loop(self):
        """Run at 10:00 (intraday check), 14:30 (T trade check), and 15:35 (daily close)."""
        while self.is_running:
            try:
                now = china_now()
                
                # Define schedule times
                schedules = [
                    (10, 0, 'intraday'),   # Morning check
                    (14, 30, 't_trade'),   # Afternoon T trade
                    (15, 35, 'daily'),     # After close
                ]
                
                # Find next schedule
                next_time = None
                next_task = None
                
                for hour, minute, task in schedules:
                    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    if now >= target:
                        continue
                    if next_time is None or target < next_time:
                        next_time = target
                        next_task = task
                
                if next_time is None:
                    # All done for today, schedule for tomorrow
                    next_time = (now + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
                    next_task = 'intraday'
                
                # Skip weekends
                while next_time.weekday() >= 5:
                    next_time += timedelta(days=1)
                
                wait_seconds = (next_time - now).total_seconds()
                if wait_seconds > 0:
                    logger.info(f"Next {next_task} at {next_time.strftime('%Y-%m-%d %H:%M')}")
                    await asyncio.sleep(wait_seconds)
                
                # Execute task
                if next_task == 'intraday':
                    await self.intraday_check()
                elif next_task == 't_trade':
                    await self.check_t_trade_opportunity()
                elif next_task == 'daily':
                    await self.daily_routine()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                await asyncio.sleep(60)
    
    async def daily_routine(self):
        """Daily trading routine: check positions, scan for new buys."""
        try:
            await self._notify("🔔 开始每日收盘分析...")
            
            # 1. Check existing positions for sell signals (trailing stop, etc)
            sold_count = await self.check_positions_for_sell()
            
            # 2. Scan for new buy signals if we have room
            positions = await self.get_current_positions()
            if len(positions) < MAX_POSITIONS:
                bought_count = await self.scan_and_buy()
            else:
                bought_count = 0
                await self._notify(f"📦 仓位已满 ({len(positions)}/{MAX_POSITIONS})")
            
            # 3. Update account value
            await self.update_account_value()
            
            # 4. Send summary
            stats = await self.get_statistics()
            await self._notify(
                f"📊 收盘总结\n"
                f"持仓: {stats.get('current_positions', 0)}/{MAX_POSITIONS}\n"
                f"今日买入: {bought_count}只 | 卖出: {sold_count}只\n"
                f"总收益: {stats.get('total_return_pct', 0):+.2f}%"
            )
            
        except Exception as e:
            logger.error(f"Daily routine failed: {e}")
            await self._notify(f"❌ 每日分析失败: {e}")
    
    async def intraday_check(self):
        """Morning intraday check - update trailing stops."""
        try:
            positions = await self.get_current_positions()
            if not positions:
                return
            
            for pos in positions:
                pos = await self.get_position_with_current_price(pos)
                if 'current_price' not in pos:
                    continue
                
                # Update peak price for trailing stop
                await self._update_peak_price(pos['id'], pos['current_price'])
                
        except Exception as e:
            logger.error(f"Intraday check failed: {e}")
    
    async def check_t_trade_opportunity(self):
        """Check for T+0 trading opportunities using existing positions.
        
        A-share T+0 strategy:
        - If holding stock and it dipped in morning, buy more
        - Then sell original shares at higher price in afternoon
        - Net effect: lower cost basis while maintaining position
        """
        try:
            positions = await self.get_current_positions()
            if not positions:
                return
            
            ak, pd = self._get_libs()
            
            for pos in positions:
                # Skip if bought today (can't sell T+0)
                if pos['buy_date'] == china_today():
                    continue
                
                code = pos['code']
                name = pos.get('name', code)
                
                try:
                    # Get intraday data
                    df = await asyncio.to_thread(
                        ak.stock_zh_a_spot_em
                    )
                    
                    if df is None or df.empty:
                        continue
                    
                    row = df[df['代码'] == code]
                    if row.empty:
                        continue
                    
                    current_price = float(row.iloc[0]['最新价'])
                    high_price = float(row.iloc[0]['最高'])
                    low_price = float(row.iloc[0]['最低'])
                    open_price = float(row.iloc[0]['今开'])
                    
                    # Calculate intraday swing
                    if low_price <= 0:
                        continue
                    
                    swing_pct = (high_price - low_price) / low_price * 100
                    
                    # Check if there's T opportunity
                    if swing_pct >= T_TRADE_THRESHOLD:
                        buy_price = float(pos['buy_price'])
                        
                        # If current price is higher than buy price and near high
                        # This is a good time to do reverse T (sell high, buy back low later)
                        if current_price > buy_price and current_price >= high_price * 0.98:
                            # Sell half position at high
                            half_shares = pos['shares'] // 2
                            if half_shares >= 100:
                                await self._notify(
                                    f"📈 做T机会 {name}({code})\n"
                                    f"当前: ¥{current_price:.2f} (近最高)\n"
                                    f"日内振幅: {swing_pct:.1f}%\n"
                                    f"建议: 卖出{half_shares}股，待回调买回"
                                )
                        
                        # If current price dipped below buy price
                        elif current_price < buy_price * 0.98 and current_price <= low_price * 1.02:
                            await self._notify(
                                f"📉 做T机会 {name}({code})\n"
                                f"当前: ¥{current_price:.2f} (近最低)\n"
                                f"日内振幅: {swing_pct:.1f}%\n"
                                f"成本: ¥{buy_price:.2f}\n"
                                f"建议: 加仓降低成本"
                            )
                    
                except Exception as e:
                    logger.error(f"T trade check failed for {code}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"T trade opportunity check failed: {e}")
    
    async def _update_peak_price(self, position_id: int, current_price: float):
        """Update peak price for trailing stop calculation."""
        if not db.pool:
            return
        
        async with db.pool.acquire() as conn:
            # Get current peak (stored in a new column or use highest seen)
            pos = await conn.fetchrow("""
                SELECT peak_price FROM trading_portfolio WHERE id = $1
            """, position_id)
            
            if pos:
                peak = float(pos['peak_price']) if pos['peak_price'] else 0
                if current_price > peak:
                    await conn.execute("""
                        UPDATE trading_portfolio SET peak_price = $1 WHERE id = $2
                    """, current_price, position_id)
    
    # ─────────────────────────────────────────────────────────────────────────
    # Position Management
    # ─────────────────────────────────────────────────────────────────────────
    
    async def get_current_positions(self) -> List[Dict]:
        """Get all current holding positions."""
        if not db.pool:
            return []
        
        async with db.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, code, name, buy_date, buy_price, buy_amount, shares, 
                       signal_type, peak_price, created_at
                FROM trading_portfolio
                WHERE status = 'holding'
                ORDER BY buy_date DESC
            """)
            return [dict(r) for r in rows]
    
    async def get_position_with_current_price(self, position: Dict) -> Dict:
        """Enrich position with current price and P&L."""
        try:
            ak, pd = self._get_libs()
            
            # Get current price
            df = await asyncio.to_thread(
                ak.stock_zh_a_spot_em
            )
            
            if df is not None and not df.empty:
                row = df[df['代码'] == position['code']]
                if not row.empty:
                    current_price = float(row.iloc[0]['最新价'])
                    buy_price = float(position['buy_price'])
                    profit_pct = (current_price - buy_price) / buy_price * 100
                    profit_loss = (current_price - buy_price) * position['shares']
                    holding_days = (china_today() - position['buy_date']).days
                    
                    position.update({
                        'current_price': current_price,
                        'profit_pct': round(profit_pct, 2),
                        'profit_loss': round(profit_loss, 2),
                        'holding_days': holding_days,
                        'market_value': current_price * position['shares']
                    })
        except Exception as e:
            logger.error(f"Failed to get price for {position['code']}: {e}")
        
        return position
    
    async def check_positions_for_sell(self) -> int:
        """Check all positions and sell if conditions met (with trailing stop)."""
        positions = await self.get_current_positions()
        sold_count = 0
        
        for pos in positions:
            pos = await self.get_position_with_current_price(pos)
            
            if 'current_price' not in pos:
                continue
            
            sell_reason = None
            current_price = pos['current_price']
            buy_price = float(pos['buy_price'])
            peak_price = float(pos.get('peak_price') or current_price)
            profit_pct = pos['profit_pct']
            
            # 1. Trailing Stop: if profit was > 8% and now dropped 3% from peak
            if peak_price > buy_price * (1 + TRAILING_STOP_TRIGGER / 100):
                trailing_trigger = peak_price * (1 - TRAILING_STOP_PCT / 100)
                if current_price <= trailing_trigger:
                    sell_reason = 'trailing_stop'
                    await self._notify(
                        f"📉 移动止盈触发 {pos['name']}({pos['code']})\n"
                        f"最高: ¥{peak_price:.2f} → 当前: ¥{current_price:.2f}\n"
                        f"回撤: {(peak_price - current_price) / peak_price * 100:.1f}%"
                    )
            
            # 2. Fixed Stop Loss
            if profit_pct <= -STOP_LOSS_PCT:
                sell_reason = 'stop_loss'
                await self._notify(
                    f"🛑 止损 {pos['name']}({pos['code']})\n"
                    f"亏损: {profit_pct:.2f}%"
                )
            
            # 3. Holding timeout (no profit after MAX_HOLDING_DAYS)
            elif pos['holding_days'] >= MAX_HOLDING_DAYS and profit_pct <= 0:
                sell_reason = 'timeout'
                await self._notify(
                    f"⏰ 超时清仓 {pos['name']}({pos['code']})\n"
                    f"持仓{pos['holding_days']}天，收益: {profit_pct:.2f}%"
                )
            
            # 4. Death cross signal
            elif await self._check_death_cross(pos['code']):
                sell_reason = 'death_cross'
                await self._notify(
                    f"📊 死叉信号 {pos['name']}({pos['code']})\n"
                    f"MA5下穿MA10，建议卖出"
                )
            
            if sell_reason:
                await self.sell_position(pos['id'], current_price, sell_reason)
                sold_count += 1
        
        return sold_count
    
    async def _check_death_cross(self, code: str) -> bool:
        """Check if MA5 crossed below MA10 (death cross)."""
        try:
            if not db.pool:
                return False
            
            async with db.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT date, close
                    FROM stock_history
                    WHERE code = $1
                    ORDER BY date DESC
                    LIMIT 15
                """, code)
            
            if len(rows) < 12:
                return False
            
            closes = [float(r['close']) for r in reversed(rows)]
            
            # Calculate MA5 and MA10 for last 2 days
            ma5_today = sum(closes[-5:]) / 5
            ma10_today = sum(closes[-10:]) / 10
            ma5_yesterday = sum(closes[-6:-1]) / 5
            ma10_yesterday = sum(closes[-11:-1]) / 10
            
            # Death cross: MA5 was above MA10 yesterday, now below
            return ma5_yesterday >= ma10_yesterday and ma5_today < ma10_today
            
        except Exception as e:
            logger.error(f"Death cross check failed for {code}: {e}")
            return False
    
    async def sell_position(self, position_id: int, sell_price: float, reason: str):
        """Sell a position and update records."""
        if not db.pool:
            return
        
        async with db.pool.acquire() as conn:
            # Get position details
            pos = await conn.fetchrow("""
                SELECT * FROM trading_portfolio WHERE id = $1
            """, position_id)
            
            if not pos:
                return
            
            buy_price = float(pos['buy_price'])
            shares = pos['shares']
            profit_loss = (sell_price - buy_price) * shares
            profit_pct = (sell_price - buy_price) / buy_price * 100
            holding_days = (china_today() - pos['buy_date']).days
            sell_amount = sell_price * shares
            
            # Update position
            await conn.execute("""
                UPDATE trading_portfolio
                SET status = 'sold',
                    sell_date = $1,
                    sell_price = $2,
                    sell_reason = $3,
                    profit_loss = $4,
                    profit_pct = $5,
                    holding_days = $6
                WHERE id = $7
            """, china_today(), sell_price, reason, profit_loss, profit_pct, holding_days, position_id)
            
            # Update account
            await conn.execute("""
                UPDATE trading_account
                SET current_cash = current_cash + $1,
                    total_profit = total_profit + $2,
                    total_trades = total_trades + 1,
                    win_count = win_count + $3,
                    loss_count = loss_count + $4,
                    updated_at = NOW()
                WHERE id = 1
            """, sell_amount, profit_loss, 1 if profit_loss > 0 else 0, 1 if profit_loss <= 0 else 0)
            
            # Notify user
            reason_cn = {
                'trailing_stop': '移动止盈',
                'stop_loss': '止损',
                'timeout': '超时',
                'death_cross': '死叉',
                'manual': '手动'
            }.get(reason, reason)
            
            emoji = '🟢' if profit_loss >= 0 else '🔴'
            await self._notify(
                f"{emoji} 卖出 {pos['name']}({pos['code']})\n"
                f"价格: ¥{sell_price:.2f} | {shares}股\n"
                f"盈亏: ¥{profit_loss:+,.0f} ({profit_pct:+.2f}%)\n"
                f"原因: {reason_cn} | 持仓{holding_days}天"
            )
            
            logger.info(f"Sold {pos['name']}({pos['code']}) at {sell_price:.2f}, "
                       f"P&L: {profit_loss:+.2f} ({profit_pct:+.2f}%), reason: {reason}")
    
    # ─────────────────────────────────────────────────────────────────────────
    # Buy Signals and Execution
    # ─────────────────────────────────────────────────────────────────────────
    
    async def scan_and_buy(self) -> int:
        """Scan for buy signals and execute buys."""
        # Get stocks with buy signals from stock_scanner
        from app.services.stock_scanner import stock_scanner
        
        try:
            signals = await stock_scanner.scan_all_stocks(limit=200)
        except Exception as e:
            logger.error(f"Scan failed: {e}")
            return 0
        
        if not signals:
            return 0
        
        # Filter: require multiple signal types for higher confidence
        high_confidence = []
        
        for s in signals:
            signal_types = s.get('signals', [])
            if 'volume_price_startup' in signal_types or len(signal_types) >= 2:
                high_confidence.append(s)
        
        if not high_confidence:
            await self._notify("📭 未发现高置信度买入信号")
            return 0
        
        # Get current positions and account
        positions = await self.get_current_positions()
        held_codes = {p['code'] for p in positions}
        account = await self.get_account()
        
        if not account:
            return 0
        
        available_cash = float(account['current_cash'])
        slots_available = MAX_POSITIONS - len(positions)
        
        if slots_available <= 0 or available_cash < 10000:
            return 0
        
        # Calculate position size
        position_size = available_cash / slots_available
        
        bought_count = 0
        for signal in high_confidence[:slots_available]:
            code = signal['code']
            
            # Skip if already holding
            if code in held_codes:
                continue
            
            # Get current price
            try:
                price = await self._get_current_price(code)
                if not price or price <= 0:
                    continue
                
                # Calculate shares (round to 100 - lot size)
                shares = int(position_size / price / 100) * 100
                if shares < 100:
                    continue
                
                buy_amount = shares * price
                
                # Execute buy
                success = await self.buy_stock(
                    code=code,
                    name=signal.get('name', code),
                    price=price,
                    shares=shares,
                    amount=buy_amount,
                    signal_type=','.join(signal.get('signals', ['unknown']))
                )
                
                if success:
                    bought_count += 1
                    held_codes.add(code)
                    available_cash -= buy_amount
                    
            except Exception as e:
                logger.error(f"Failed to buy {code}: {e}")
                continue
        
        return bought_count
    
    async def _get_current_price(self, code: str) -> Optional[float]:
        """Get current stock price."""
        try:
            ak, _ = self._get_libs()
            df = await asyncio.to_thread(ak.stock_zh_a_spot_em)
            
            if df is not None and not df.empty:
                row = df[df['代码'] == code]
                if not row.empty:
                    return float(row.iloc[0]['最新价'])
        except Exception as e:
            logger.error(f"Failed to get price for {code}: {e}")
        return None
    
    async def buy_stock(self, code: str, name: str, price: float, shares: int, 
                       amount: float, signal_type: str) -> bool:
        """Execute a buy order."""
        if not db.pool:
            return False
        
        try:
            async with db.pool.acquire() as conn:
                # Deduct cash
                result = await conn.execute("""
                    UPDATE trading_account
                    SET current_cash = current_cash - $1,
                        updated_at = NOW()
                    WHERE id = 1 AND current_cash >= $1
                """, amount)
                
                if 'UPDATE 0' in result:
                    logger.warning(f"Insufficient cash to buy {code}")
                    return False
                
                # Add position
                await conn.execute("""
                    INSERT INTO trading_portfolio 
                    (code, name, status, buy_date, buy_price, buy_amount, shares, signal_type, peak_price)
                    VALUES ($1, $2, 'holding', $3, $4, $5, $6, $7, $4)
                """, code, name, china_today(), price, amount, shares, signal_type)
            
            # Notify user
            await self._notify(
                f"🟢 买入 {name}({code})\n"
                f"价格: ¥{price:.2f} | {shares}股\n"
                f"金额: ¥{amount:,.0f}\n"
                f"信号: {signal_type}"
            )
            
            logger.info(f"Bought {name}({code}) {shares}股 at {price:.2f}, total: {amount:.2f}")
            return True
            
        except Exception as e:
            logger.error(f"Buy execution failed for {code}: {e}")
            return False
    
    # ─────────────────────────────────────────────────────────────────────────
    # Account and Reporting
    # ─────────────────────────────────────────────────────────────────────────
    
    async def get_account(self) -> Optional[Dict]:
        """Get trading account details."""
        if not db.pool:
            return None
        
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM trading_account WHERE id = 1
            """)
            return dict(row) if row else None
    
    async def update_account_value(self):
        """Update total account value based on current positions."""
        if not db.pool:
            return
        
        account = await self.get_account()
        if not account:
            return
        
        positions = await self.get_current_positions()
        total_market_value = 0
        
        for pos in positions:
            pos = await self.get_position_with_current_price(pos)
            if 'market_value' in pos:
                total_market_value += pos['market_value']
            else:
                total_market_value += float(pos['buy_amount'])
        
        total_value = float(account['current_cash']) + total_market_value
        
        async with db.pool.acquire() as conn:
            await conn.execute("""
                UPDATE trading_account
                SET total_value = $1, updated_at = NOW()
                WHERE id = 1
            """, total_value)
    
    async def get_trade_history(self, limit: int = 20) -> List[Dict]:
        """Get recent trade history (sold positions)."""
        if not db.pool:
            return []
        
        async with db.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT code, name, buy_date, buy_price, sell_date, sell_price,
                       profit_loss, profit_pct, holding_days, sell_reason, signal_type
                FROM trading_portfolio
                WHERE status = 'sold'
                ORDER BY sell_date DESC
                LIMIT $1
            """, limit)
            return [dict(r) for r in rows]
    
    async def get_statistics(self) -> Dict:
        """Get trading statistics."""
        account = await self.get_account()
        if not account:
            return {}
        
        positions = await self.get_current_positions()
        
        # Calculate unrealized P&L
        unrealized_pnl = 0
        for pos in positions:
            pos = await self.get_position_with_current_price(pos)
            if 'profit_loss' in pos:
                unrealized_pnl += pos['profit_loss']
        
        total_profit = float(account['total_profit']) + unrealized_pnl
        total_trades = account['total_trades']
        win_rate = account['win_count'] / total_trades * 100 if total_trades > 0 else 0
        
        return {
            'initial_capital': float(account['initial_capital']),
            'current_cash': float(account['current_cash']),
            'total_value': float(account['total_value']),
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
            return "📊 <b>模拟持仓</b>\n\n当前无持仓"
        
        lines = ["📊 <b>模拟持仓</b>\n"]
        total_value = 0
        total_pnl = 0
        
        for i, pos in enumerate(positions, 1):
            pos = await self.get_position_with_current_price(pos)
            
            name = pos.get('name', pos['code'])
            code = pos['code']
            
            if 'current_price' in pos:
                price = pos['current_price']
                pnl_pct = pos['profit_pct']
                pnl = pos['profit_loss']
                days = pos['holding_days']
                market_val = pos['market_value']
                peak = float(pos.get('peak_price') or price)
                
                emoji = '🔴' if pnl >= 0 else '🟢'
                peak_info = f" 📈{peak:.2f}" if peak > price else ""
                lines.append(
                    f"{i}. <b>{name}</b> ({code})\n"
                    f"   {emoji} {pnl_pct:+.2f}% | ¥{pnl:+,.0f} | {days}天{peak_info}"
                )
                total_value += market_val
                total_pnl += pnl
            else:
                lines.append(f"{i}. <b>{name}</b> ({code}) - 无法获取价格")
                total_value += float(pos['buy_amount'])
        
        lines.append(f"\n💰 持仓市值: ¥{total_value:,.0f}")
        lines.append(f"📈 持仓盈亏: ¥{total_pnl:+,.0f}")
        
        return "\n".join(lines)
    
    async def generate_pnl_report(self) -> str:
        """Generate P&L statistics report."""
        stats = await self.get_statistics()
        
        if not stats:
            return "📉 <b>盈亏统计</b>\n\n无数据"
        
        return (
            f"📉 <b>盈亏统计</b>\n\n"
            f"💰 初始资金: ¥{stats['initial_capital']:,.0f}\n"
            f"💵 当前现金: ¥{stats['current_cash']:,.0f}\n"
            f"📊 账户总值: ¥{stats['total_value']:,.0f}\n\n"
            f"📈 总收益: ¥{stats['total_profit']:+,.0f} ({stats['total_return_pct']:+.2f}%)\n"
            f"   - 已实现: ¥{stats['realized_profit']:+,.0f}\n"
            f"   - 未实现: ¥{stats['unrealized_profit']:+,.0f}\n\n"
            f"🎯 交易统计:\n"
            f"   - 总交易: {stats['total_trades']}笔\n"
            f"   - 盈利: {stats['win_count']}笔 / 亏损: {stats['loss_count']}笔\n"
            f"   - 胜率: {stats['win_rate']:.1f}%\n\n"
            f"📦 当前持仓: {stats['current_positions']}/{MAX_POSITIONS}"
        )
    
    async def generate_trades_report(self, limit: int = 10) -> str:
        """Generate recent trades report."""
        trades = await self.get_trade_history(limit)
        
        if not trades:
            return "📜 <b>交易历史</b>\n\n暂无交易记录"
        
        lines = ["📜 <b>交易历史</b>\n"]
        
        for t in trades:
            name = t.get('name', t['code'])
            pnl = float(t['profit_loss']) if t['profit_loss'] else 0
            pnl_pct = float(t['profit_pct']) if t['profit_pct'] else 0
            days = t['holding_days'] or 0
            reason = {
                'trailing_stop': '移动止盈',
                'stop_loss': '止损',
                'timeout': '超时',
                'death_cross': '死叉',
                'manual': '手动'
            }.get(t['sell_reason'], t['sell_reason'])
            
            emoji = '🟢' if pnl >= 0 else '🔴'
            sell_date = t['sell_date'].strftime('%m/%d') if t['sell_date'] else '--'
            
            lines.append(
                f"{emoji} <b>{name}</b> {sell_date}\n"
                f"   {pnl_pct:+.2f}% | ¥{pnl:+,.0f} | {days}天 | {reason}"
            )
        
        return "\n".join(lines)


# Singleton
trading_simulator = TradingSimulator()
