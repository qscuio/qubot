"""
AI Stock Scanner (启动信号扫描器)

Scans all A-share stocks for startup signals:
- Breakout: Close > 20-day high
- Volume surge: Volume > 5-day avg × 2  
- MA bullish: MA5 > MA10 > MA20 with golden cross
- Small bullish 5: 5 consecutive small bullish candles at bottom (底部连续5个小阳线)
"""

import asyncio
from datetime import datetime, date
from typing import List, Dict, Optional
import pytz

from app.core.logger import Logger
from app.core.database import db
from app.core.config import settings
from app.core.stock_links import get_chart_url

logger = Logger("StockScanner")

CHINA_TZ = pytz.timezone("Asia/Shanghai")


class StockScanner:
    """Service for scanning stocks with startup signals."""
    
    def __init__(self):
        self.is_running = False
        self._scheduler_task = None
        self._ak = None
        self._pd = None
    
    def _get_libs(self):
        """Lazy load akshare and pandas."""
        if self._ak is None:
            try:
                import akshare as ak
                import pandas as pd
                self._ak = ak
                self._pd = pd
            except ImportError:
                logger.error("Missing libs. Run: pip install akshare pandas")
                return None, None
        return self._ak, self._pd
    
    async def start(self):
        """Start the scanner scheduler."""
        if self.is_running:
            return
        
        self.is_running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("✅ Stock Scanner started")
    
    async def stop(self):
        """Stop the scanner."""
        self.is_running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        logger.info("Stock Scanner stopped")
    
    async def _scheduler_loop(self):
        """Run scanner at 15:30 daily."""
        triggered_today = set()
        
        while self.is_running:
            try:
                now = datetime.now(CHINA_TZ)
                time_str = now.strftime("%H:%M")
                date_str = now.strftime("%Y-%m-%d")
                
                if time_str == "00:00":
                    triggered_today.clear()
                
                key = f"{date_str}_scan"
                
                # Scan at 15:30 on weekdays
                if now.weekday() < 5 and time_str == "15:30" and key not in triggered_today:
                    triggered_today.add(key)
                    asyncio.create_task(self.scan_and_report())
                    
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
            
            await asyncio.sleep(30)
    
    async def scan_and_report(self):
        """Scan all stocks and send report."""
        from app.core.bot import telegram_service
        
        if not settings.STOCK_ALERT_CHANNEL:
            return
        
        logger.info("Starting full market scan...")
        signals = await self.scan_all_stocks()
        
        if not signals:
            logger.info("No signals found")
            return
        
        now = datetime.now(CHINA_TZ)
        text = f"🔍 <b>启动信号扫描</b> {now.strftime('%Y-%m-%d %H:%M')}\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for signal_type, stocks in signals.items():
            if not stocks:
                continue
            
            icon = {"breakout": "🔺", "volume": "📊", "ma_bullish": "📈"}.get(signal_type, "•")
            name = {"breakout": "突破信号", "volume": "放量信号", "ma_bullish": "多头排列"}.get(signal_type, signal_type)
            
            text += f"{icon} <b>{name}</b> ({len(stocks)})\n"
            for s in stocks[:8]:
                url = await get_chart_url(s["code"], s.get("name"))
                text += f"  • <a href=\"{url}\">{s['name']}</a> ({s['code']})\n"
            if len(stocks) > 8:
                text += f"  ...及其他 {len(stocks) - 8} 只\n"
            text += "\n"
        
        await telegram_service.send_message(settings.STOCK_ALERT_CHANNEL, text, parse_mode="html")
        logger.info(f"Sent scan report with {sum(len(v) for v in signals.values())} signals")
    
    async def scan_all_stocks(self, limit: int = 500) -> Dict[str, List[Dict]]:
        """Scan stocks for all signal types."""
        ak, pd = self._get_libs()
        if not ak or not pd:
            return {}
        
        signals = {
            "breakout": [],
            "volume": [],
            "ma_bullish": [],
            "small_bullish_5": [],  # 底部连续5个小阳线
        }
        
        try:
            # Get stock list
            stock_list = await asyncio.to_thread(ak.stock_zh_a_spot_em)
            if stock_list is None or stock_list.empty:
                return signals
            
            # Filter main board stocks (exclude ST, new stocks)
            stocks = stock_list[
                ~stock_list['名称'].str.contains('ST|退', na=False) &
                (stock_list['代码'].str.match(r'^[036]'))
            ].head(limit)
            
            checked = 0
            for _, row in stocks.iterrows():
                code = str(row['代码'])
                name = str(row['名称'])
                
                try:
                    # Get 30-day history
                    hist = await asyncio.to_thread(
                        ak.stock_zh_a_hist, 
                        symbol=code, 
                        period="daily",
                        adjust="qfq"
                    )
                    
                    if hist is None or len(hist) < 21:
                        continue
                    
                    hist = hist.tail(21)  # Last 21 days
                    
                    stock_info = {"code": code, "name": name}
                    
                    # Check signals
                    if self._check_breakout(hist, pd):
                        signals["breakout"].append(stock_info)
                    
                    if self._check_volume_surge(hist, pd):
                        signals["volume"].append(stock_info)
                    
                    if self._check_ma_bullish(hist, pd):
                        signals["ma_bullish"].append(stock_info)
                    
                    if self._check_small_bullish_5(hist, pd):
                        signals["small_bullish_5"].append(stock_info)
                    
                    checked += 1
                    
                    # Rate limit
                    if checked % 50 == 0:
                        logger.info(f"Scanned {checked} stocks...")
                        await asyncio.sleep(1)
                        
                except Exception as e:
                    continue
            
            logger.info(f"Scan complete: {checked} stocks, found {sum(len(v) for v in signals.values())} signals")
            return signals
            
        except Exception as e:
            logger.error(f"Scan failed: {e}")
            return signals
    
    def _check_breakout(self, hist, pd) -> bool:
        """Check if close > 20-day high (breakout)."""
        try:
            close = hist['收盘'].iloc[-1]
            high_20 = hist['最高'].iloc[:-1].max()  # Exclude today
            return close > high_20
        except:
            return False
    
    def _check_volume_surge(self, hist, pd) -> bool:
        """Check if volume > 5-day avg × 2."""
        try:
            vol_today = hist['成交量'].iloc[-1]
            vol_avg5 = hist['成交量'].iloc[-6:-1].mean()
            return vol_today > vol_avg5 * 2
        except:
            return False
    
    def _check_ma_bullish(self, hist, pd) -> bool:
        """Check if MA5 > MA10 > MA20 with golden cross."""
        try:
            close = hist['收盘']
            ma5 = close.rolling(5).mean().iloc[-1]
            ma10 = close.rolling(10).mean().iloc[-1]
            ma20 = close.rolling(20).mean().iloc[-1]
            
            # MA5 crossed above MA10 today
            ma5_prev = close.rolling(5).mean().iloc[-2]
            ma10_prev = close.rolling(10).mean().iloc[-2]
            
            bullish = ma5 > ma10 > ma20
            golden_cross = ma5 > ma10 and ma5_prev <= ma10_prev
            
            return bullish and golden_cross
        except:
            return False
    
    def _check_small_bullish_5(self, hist, pd) -> bool:
        """检查底部连续5个小阳线信号.
        
        条件:
        1. 最近5日都是阳线 (收盘 > 开盘)
        2. 每日涨幅在0.5%-3%之间 (小阳线)
        3. 股价在近20日低位 (底部)
        """
        try:
            # Get last 5 days
            last_5 = hist.tail(5)
            
            if len(last_5) < 5:
                return False
            
            # Check all 5 days are bullish (close > open) and small body
            for i in range(5):
                row = last_5.iloc[i]
                open_price = row['开盘']
                close = row['收盘']
                
                # Must be bullish
                if close <= open_price:
                    return False
                
                # Calculate body percentage
                body_pct = (close - open_price) / open_price * 100
                
                # Small bullish: 0.5% - 3%
                if body_pct < 0.5 or body_pct > 3.0:
                    return False
            
            # Check if at bottom (current price < 20-day MA or in lower 30% of 20-day range)
            close_current = hist['收盘'].iloc[-1]
            high_20 = hist['最高'].max()
            low_20 = hist['最低'].min()
            range_20 = high_20 - low_20
            
            if range_20 > 0:
                position = (close_current - low_20) / range_20
                # At bottom means in lower 40% of range
                return position < 0.4
            
            return False
        except:
            return False


# Singleton
stock_scanner = StockScanner()
