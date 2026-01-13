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

from app.core.logger import Logger
from app.core.database import db
from app.core.config import settings
from app.core.stock_links import get_chart_url
from app.core.timezone import CHINA_TZ, china_now

logger = Logger("StockScanner")


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
                now = china_now()
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
        
        now = china_now()
        text = f"🔍 <b>启动信号扫描</b> {now.strftime('%Y-%m-%d %H:%M')}\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for signal_type, stocks in signals.items():
            if not stocks:
                continue
            
            icon = {"breakout": "🔺", "volume": "📊", "ma_bullish": "📈"}.get(signal_type, "•")
            name = {"breakout": "突破信号", "volume": "放量信号", "ma_bullish": "多头排列"}.get(signal_type, signal_type)
            
            text += f"{icon} <b>{name}</b> ({len(stocks)})\n"
            for s in stocks[:8]:
                url = get_chart_url(s["code"], s.get("name"))
                text += f"  • <a href=\"{url}\">{s['name']}</a> ({s['code']})\n"
            if len(stocks) > 8:
                text += f"  ...及其他 {len(stocks) - 8} 只\n"
            text += "\n"
        
        await telegram_service.send_message(settings.STOCK_ALERT_CHANNEL, text, parse_mode="html")
        logger.info(f"Sent scan report with {sum(len(v) for v in signals.values())} signals")
    
    async def scan_all_stocks(self, limit: int = 500) -> Dict[str, List[Dict]]:
        """Scan stocks for all signal types.
        
        Uses local stock_history database ONLY for maximum speed.
        """
        _, pd = self._get_libs()
        if not pd:
            return {}
        
        signals = {
            "breakout": [],
            "volume": [],
            "ma_bullish": [],
            "small_bullish_5": [],  # 底部连续5个小阳线
            "volume_price": [],  # 量价启动信号
            "multi_signal": [],  # 多信号共振(满足≥3个信号)
        }
        
        if not db.pool:
            logger.warn("Database not connected, cannot scan")
            return signals
        
        try:
            # Get stock codes and names from local database
            # Join with user_watchlist or limit_up_stock for names if available
            rows = await db.pool.fetch("""
                WITH recent_stocks AS (
                    SELECT DISTINCT code 
                    FROM stock_history 
                    WHERE date >= CURRENT_DATE - INTERVAL '7 days'
                ),
                stock_names AS (
                    SELECT code, name FROM user_watchlist GROUP BY code, name
                    UNION
                    SELECT code, name FROM limit_up_stock GROUP BY code, name
                )
                SELECT rs.code, sn.name
                FROM recent_stocks rs
                LEFT JOIN stock_names sn ON rs.code = sn.code
                WHERE rs.code ~ '^[036]'
                LIMIT $1
            """, limit)
            
            if not rows:
                logger.warn("No stocks found in local database")
                return signals
            
            codes = [r['code'] for r in rows]
            code_name_map = {r['code']: r['name'] or r['code'] for r in rows}
            
            logger.info(f"Found {len(codes)} stocks in local DB, starting scan...")
            
            # Fetch history from local database
            local_data = await self._get_local_history_batch(codes)
            
            if not local_data:
                logger.warn("No history data available")
                return signals
            
            checked = 0
            for code in codes:
                name = code_name_map.get(code, code)
                
                try:
                    # Use local data only
                    if code not in local_data or len(local_data[code]) < 21:
                        continue
                    
                    hist = local_data[code]
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
                    
                    if self._check_volume_price_startup(hist, pd):
                        signals["volume_price"].append(stock_info)
                    
                    # Count how many signals this stock has
                    signal_count = sum([
                        stock_info in signals["breakout"],
                        stock_info in signals["volume"],
                        stock_info in signals["ma_bullish"],
                        stock_info in signals["small_bullish_5"],
                        stock_info in signals["volume_price"],
                    ])
                    
                    # Add to multi-signal list if 3+ signals
                    if signal_count >= 3:
                        signals["multi_signal"].append({
                            **stock_info,
                            "signal_count": signal_count
                        })
                    
                    checked += 1
                        
                except Exception as e:
                    continue
            
            total_signals = sum(len(v) for v in signals.values())
            logger.info(f"Scan complete: {checked} stocks, found {total_signals} signals")
            return signals
            
        except Exception as e:
            logger.error(f"Scan failed: {e}")
            return signals

    
    async def _get_local_history_batch(self, codes: List[str]) -> Dict[str, any]:
        """Fetch recent history for multiple stocks from local database.
        
        Returns a dict mapping code -> DataFrame-like object with columns:
        收盘, 开盘, 最高, 最低, 成交量
        """
        if not db.pool:
            return {}
        
        _, pd = self._get_libs()
        if not pd:
            return {}
        
        result = {}
        
        try:
            # Fetch last 25 days of data for all codes
            rows = await db.pool.fetch("""
                SELECT code, date, open, high, low, close, volume
                FROM stock_history
                WHERE code = ANY($1)
                  AND date >= CURRENT_DATE - INTERVAL '30 days'
                ORDER BY code, date DESC
            """, codes)
            
            if not rows:
                return {}
            
            # Group by code and convert to DataFrame-like structure
            from collections import defaultdict
            by_code = defaultdict(list)
            for row in rows:
                by_code[row['code']].append(row)
            
            for code, code_rows in by_code.items():
                if len(code_rows) >= 21:
                    # Convert to DataFrame with Chinese column names (for compatibility)
                    df = pd.DataFrame([{
                        '日期': r['date'],
                        '开盘': float(r['open']),
                        '收盘': float(r['close']),
                        '最高': float(r['high']),
                        '最低': float(r['low']),
                        '成交量': float(r['volume']),
                    } for r in code_rows])
                    # Sort by date ascending
                    df = df.sort_values('日期').reset_index(drop=True)
                    result[code] = df.tail(21)
            
            logger.info(f"Loaded {len(result)} stocks from local DB")
            return result
            
        except Exception as e:
            logger.warn(f"Failed to load local history: {e}")
            return {}
    
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

    def _check_volume_price_startup(self, hist, pd) -> bool:
        """专业量价分析启动信号.
        
        使用多维度量价关系分析，判断股票是否即将启动：
        
        1. 量比分析 - 当前量比 > 1.5 (活跃度提升)
        2. OBV趋势 - 能量潮上升且创新高 (资金持续流入)
        3. 量价配合 - 价升量增的健康形态
        4. 位置确认 - 站上关键均线且处于合理位置
        5. 缩量整理后放量 - 典型启动形态
        """
        try:
            if len(hist) < 20:
                return False
            
            closes = hist['收盘'].values
            volumes = hist['成交量'].values
            highs = hist['最高'].values
            lows = hist['最低'].values
            opens = hist['开盘'].values
            
            # ═══════════════════════════════════════════════════════════
            # 1. 量比分析 (Volume Ratio)
            # ═══════════════════════════════════════════════════════════
            vol_today = volumes[-1]
            vol_avg5 = volumes[-6:-1].mean()
            vol_avg10 = volumes[-11:-1].mean()
            
            volume_ratio = vol_today / vol_avg5 if vol_avg5 > 0 else 0
            
            # 量比需要 > 1.5 表示活跃度提升
            if volume_ratio < 1.5:
                return False
            
            # ═══════════════════════════════════════════════════════════
            # 2. OBV (能量潮) 趋势分析
            # ═══════════════════════════════════════════════════════════
            obv = self._calculate_obv(closes, volumes)
            obv_ma5 = pd.Series(obv).rolling(5).mean().iloc[-1]
            obv_ma10 = pd.Series(obv).rolling(10).mean().iloc[-1]
            
            # OBV需要上升趋势 (OBV > OBV_MA5 > OBV_MA10)
            obv_bullish = obv[-1] > obv_ma5 > obv_ma10
            
            # OBV创5日新高 (资金持续流入)
            obv_new_high = obv[-1] >= max(obv[-5:])
            
            if not (obv_bullish or obv_new_high):
                return False
            
            # ═══════════════════════════════════════════════════════════
            # 3. 价格趋势确认
            # ═══════════════════════════════════════════════════════════
            close_today = closes[-1]
            ma5 = pd.Series(closes).rolling(5).mean().iloc[-1]
            ma10 = pd.Series(closes).rolling(10).mean().iloc[-1]
            ma20 = pd.Series(closes).rolling(20).mean().iloc[-1]
            
            # 价格需站上MA10
            if close_today < ma10:
                return False
            
            # ═══════════════════════════════════════════════════════════
            # 4. 量价配合检测 (近5日)
            # ═══════════════════════════════════════════════════════════
            # 统计量价同向的天数
            vol_price_sync = 0
            for i in range(-5, 0):
                price_up = closes[i] > closes[i-1]
                vol_up = volumes[i] > volumes[i-1]
                # 价涨量增 或 价跌量缩 都是健康形态
                if (price_up and vol_up) or (not price_up and not vol_up):
                    vol_price_sync += 1
            
            # 至少3天量价配合良好
            if vol_price_sync < 3:
                return False
            
            # ═══════════════════════════════════════════════════════════
            # 5. 缩量整理后放量启动 (经典形态)
            # ═══════════════════════════════════════════════════════════
            # 检查前5-10日是否有缩量整理
            vol_prev_5_10 = volumes[-10:-5].mean()
            vol_recent = volumes[-3:].mean()
            
            # 近期量能放大 (相比前期整理期)
            volume_expansion = vol_recent > vol_prev_5_10 * 1.3
            
            # ═══════════════════════════════════════════════════════════
            # 6. K线形态确认
            # ═══════════════════════════════════════════════════════════
            # 今日实体在日内上半部分
            body_top = max(opens[-1], close_today)
            body_bottom = min(opens[-1], close_today)
            day_range = highs[-1] - lows[-1]
            if day_range > 0:
                body_position = (body_bottom - lows[-1]) / day_range
                # 实体应在中上部位置
                if body_position < 0.3:
                    return False
            
            # 今日应为阳线或十字星
            is_bullish = close_today >= opens[-1]
            
            # ═══════════════════════════════════════════════════════════
            # 综合判断: 满足以上条件
            # ═══════════════════════════════════════════════════════════
            return is_bullish and (volume_expansion or volume_ratio > 2)
            
        except:
            return False
    
    def _calculate_obv(self, closes, volumes) -> list:
        """计算OBV (On-Balance Volume 能量潮)."""
        obv = [0]
        for i in range(1, len(closes)):
            if closes[i] > closes[i-1]:
                obv.append(obv[-1] + volumes[i])
            elif closes[i] < closes[i-1]:
                obv.append(obv[-1] - volumes[i])
            else:
                obv.append(obv[-1])
        return obv


# Singleton
stock_scanner = StockScanner()
