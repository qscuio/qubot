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
        self._last_scan_signature = None
        self._last_signals = None
        self._last_scan_used_cache = False

    @property
    def last_scan_used_cache(self) -> bool:
        return self._last_scan_used_cache
    
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
    
    async def scan_all_stocks(self, force: bool = False) -> Dict[str, List[Dict]]:
        """Scan ALL stocks for all signal types.
        
        Uses local stock_history database ONLY for maximum speed.
        """
        logger.info("🔍 Starting scan_all_stocks (full scan)")
        self._last_scan_used_cache = False
        
        _, pd = self._get_libs()
        if not pd:
            logger.error("❌ Failed to load pandas/akshare libraries")
            return {}
        
        signals = {
            "breakout": [],
            "volume": [],
            "ma_bullish": [],
            "small_bullish_5": [],  # 底部连续5个小阳线
            "volume_price": [],  # 量价启动信号
            "small_bullish_4": [],  # 底部四连阳
            "small_bullish_4_1_bearish": [],  # 四阳一阴
            "small_bullish_5_1_bearish": [],  # 五阳一阴
            "pullback_ma5": [],  # 5日线回踩
            "pullback_ma20": [],  # 20日线回踩
            "pullback_ma30": [],  # 30日线回踩
            "pullback_ma5_weekly": [],  # 5周线回踩
            "multi_signal": [],  # 多信号共振(满足≥3个信号)
        }
        
        if not db.pool:
            logger.error("❌ Database not connected, cannot scan")
            return signals
        
        try:
            # Use China timezone for date calculation
            from app.core.timezone import china_today
            today = china_today()
            logger.info(f"📅 Using China date: {today}")
            
            # First, check if stock_history table has any data
            count_row = await db.pool.fetchrow("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(DISTINCT code) as stock_count,
                    MAX(date) as max_date,
                    MIN(date) as min_date
                FROM stock_history
            """)
            
            if count_row:
                logger.info(f"📊 stock_history stats: total={count_row['total']}, stocks={count_row['stock_count']}, "
                           f"date_range={count_row['min_date']} ~ {count_row['max_date']}")
            else:
                logger.warn("⚠️ stock_history table appears to be empty")

            max_date = count_row['max_date'] if count_row else None
            max_date_count = 0
            if max_date:
                max_date_count = await db.pool.fetchval("""
                    SELECT COUNT(DISTINCT code)
                    FROM stock_history
                    WHERE date = $1
                """, max_date) or 0

            signature = (max_date, max_date_count) if max_date else None
            if not force and signature and self._last_signals is not None and signature == self._last_scan_signature:
                logger.info("♻️ Using cached scan results (DB data unchanged)")
                self._last_scan_used_cache = True
                return self._last_signals
            
            # Check recent data specifically
            recent_count = await db.pool.fetchval("""
                SELECT COUNT(DISTINCT code) 
                FROM stock_history 
                WHERE date >= $1::date - INTERVAL '7 days'
            """, today)
            logger.info(f"📈 Stocks with data in last 7 days: {recent_count}")
            
            if recent_count == 0:
                logger.warn(f"⚠️ No stocks have data in the last 7 days (since {today - __import__('datetime').timedelta(days=7)})")
                logger.warn("💡 Suggestion: Run /dbsync to sync stock history data")
                return signals
            
            # Get ALL stock codes from stock_history (no limit)
            rows = await db.pool.fetch("""
                SELECT DISTINCT code
                FROM stock_history 
                WHERE date >= $1::date - INTERVAL '7 days'
                  AND code ~ '^[036]'
            """, today)
            
            if not rows:
                logger.warn(f"⚠️ No stocks found matching pattern '^[036]' in local database. Today (China): {today}")
                # Try to debug: get some sample codes
                sample = await db.pool.fetch("SELECT DISTINCT code FROM stock_history LIMIT 5")
                if sample:
                    logger.info(f"📋 Sample codes in DB: {[r['code'] for r in sample]}")
                return signals
            
            codes = [r['code'] for r in rows]
            code_name_map = {code: code for code in codes}

            # Enrich with stock names if available
            try:
                name_rows = await db.pool.fetch("""
                    SELECT code, name
                    FROM stock_info
                    WHERE code = ANY($1)
                """, codes)
                for row in name_rows:
                    if row.get('name'):
                        code_name_map[row['code']] = row['name']
            except Exception:
                pass
            
            logger.info(f"✅ Found {len(codes)} stocks in local DB, starting scan...")
            
            # Fetch history from local database
            local_data = await self._get_local_history_batch(codes)
            
            if not local_data:
                logger.warn("⚠️ No history data available after fetching from DB")
                return signals
            
            logger.info(f"📊 Loaded history for {len(local_data)} stocks")
            
            checked = 0
            skipped_insufficient = 0
            for code in codes:
                name = code_name_map.get(code, code)
                
                try:
                    # Use local data only
                    if code not in local_data or len(local_data[code]) < 21:
                        skipped_insufficient += 1
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

                    if self._check_small_bullish_4(hist, pd):
                        signals["small_bullish_4"].append(stock_info)

                    if self._check_small_bullish_4_1_bearish(hist, pd):
                        signals["small_bullish_4_1_bearish"].append(stock_info)

                    if self._check_small_bullish_5_1_bearish(hist, pd):
                        signals["small_bullish_5_1_bearish"].append(stock_info)

                    if self._check_ma_pullback(hist, pd, 5):
                        signals["pullback_ma5"].append(stock_info)

                    if self._check_ma_pullback(hist, pd, 20):
                        signals["pullback_ma20"].append(stock_info)

                    if self._check_ma_pullback(hist, pd, 30):
                        signals["pullback_ma30"].append(stock_info)

                    if self._check_ma_pullback_weekly(hist, pd, 5):
                        signals["pullback_ma5_weekly"].append(stock_info)
                    
                    # Count how many signals this stock has
                    signal_count = sum([
                        stock_info in signals["breakout"],
                        stock_info in signals["volume"],
                        stock_info in signals["ma_bullish"],
                        stock_info in signals["small_bullish_5"],
                        stock_info in signals["volume_price"],
                        stock_info in signals["small_bullish_4"],
                        stock_info in signals["small_bullish_4_1_bearish"],
                        stock_info in signals["small_bullish_5_1_bearish"],
                        stock_info in signals["pullback_ma5"],
                        stock_info in signals["pullback_ma20"],
                        stock_info in signals["pullback_ma30"],
                        stock_info in signals["pullback_ma5_weekly"],
                    ])
                    
                    # Add to multi-signal list if 3+ signals
                    if signal_count >= 3:
                        signals["multi_signal"].append({
                            **stock_info,
                            "signal_count": signal_count
                        })
                    
                    checked += 1
                        
                except Exception as e:
                    logger.debug(f"Error checking {code}: {e}")
                    continue
            
            if skipped_insufficient > 0:
                logger.info(f"⏭️ Skipped {skipped_insufficient} stocks with insufficient history (<21 days)")
            
            total_signals = sum(len(v) for v in signals.values())
            logger.info(f"✅ Scan complete: checked {checked} stocks, found {total_signals} signals")
            for sig_type, stocks in signals.items():
                if stocks:
                    logger.info(f"   {sig_type}: {len(stocks)} signals")
            if signature:
                self._last_scan_signature = signature
                self._last_signals = signals
            return signals
            
        except Exception as e:
            logger.error(f"❌ Scan failed with error: {e}")
            import traceback
            logger.error(traceback.format_exc())
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
        
        try:
            min_rows = 21
            max_rows = 60

            rows = await db.pool.fetch("""
                SELECT code, date, open, high, low, close, volume
                FROM (
                    SELECT code, date, open, high, low, close, volume,
                           ROW_NUMBER() OVER (PARTITION BY code ORDER BY date DESC) AS rn
                    FROM stock_history
                    WHERE code = ANY($1)
                ) t
                WHERE rn <= $2
                ORDER BY code, date DESC
            """, codes, max_rows)

            if not rows:
                logger.warn(f"No history rows found for {len(codes)} codes (last {max_rows} rows)")
                return {}

            from collections import defaultdict
            by_code = defaultdict(list)
            for row in rows:
                by_code[row['code']].append(row)

            result = {}
            for code, code_rows in by_code.items():
                if len(code_rows) >= min_rows:
                    df = pd.DataFrame([{
                        '日期': r['date'],
                        '开盘': float(r['open']),
                        '收盘': float(r['close']),
                        '最高': float(r['high']),
                        '最低': float(r['low']),
                        '成交量': float(r['volume']),
                    } for r in code_rows])
                    df = df.sort_values('日期').reset_index(drop=True)
                    result[code] = df.tail(min_rows)

            logger.info(f"Loaded {len(result)} stocks from local DB (last {max_rows} rows)")
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

    def _check_small_bullish_4(self, hist, pd) -> bool:
        """检查底部四连阳信号.
        
        条件:
        1. 最近4日都是小阳线 (收盘 > 开盘, 实体0.5%-3%)
        2. 股价在近60日低位 (底部)
        """
        try:
            # Get last 4 days
            last_4 = hist.tail(4)
            
            if len(last_4) < 4:
                return False
            
            # Check all 4 days are small bullish
            for i in range(4):
                row = last_4.iloc[i]
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
            
            # Check if at bottom (current price in lower 40% of 60-day range)
            # Note: hist might be shorter than 60 days, use what we have
            close_current = hist['收盘'].iloc[-1]
            high_60 = hist['最高'].max()
            low_60 = hist['最低'].min()
            range_60 = high_60 - low_60
            
            if range_60 > 0:
                position = (close_current - low_60) / range_60
                return position < 0.4
            
            return False
        except:
            return False

    def _check_small_bullish_4_1_bearish(self, hist, pd) -> bool:
        """检查四阳一阴信号.
        
        条件:
        1. 前4日(T-4到T-1)都是小阳线 (实体0.5%-3%)
        2. 今日(T)是阴线
        3. 股价在近60日低位
        """
        try:
            # Get last 5 days
            last_5 = hist.tail(5)
            
            if len(last_5) < 5:
                return False
            
            # Check first 4 days are small bullish
            for i in range(4):
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
            
            # Check today is bearish
            today = last_5.iloc[-1]
            if today['收盘'] >= today['开盘']:
                return False
            
            # Check if at bottom
            close_current = hist['收盘'].iloc[-1]
            high_60 = hist['最高'].max()
            low_60 = hist['最低'].min()
            range_60 = high_60 - low_60
            
            if range_60 > 0:
                position = (close_current - low_60) / range_60
                return position < 0.4
            
            return False
            return False
        except:
            return False

    def _check_small_bullish_5_1_bearish(self, hist, pd) -> bool:
        """检查五阳一阴信号.
        
        条件:
        1. 前5日(T-5到T-1)都是小阳线 (实体0.5%-3%)
        2. 今日(T)是阴线
        3. 股价在近60日低位
        """
        try:
            # Get last 6 days
            last_6 = hist.tail(6)
            
            if len(last_6) < 6:
                return False
            
            # Check first 5 days are small bullish
            for i in range(5):
                row = last_6.iloc[i]
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
            
            # Check today is bearish
            today = last_6.iloc[-1]
            if today['收盘'] >= today['开盘']:
                return False
            
            # Check if at bottom
            close_current = hist['收盘'].iloc[-1]
            high_60 = hist['最高'].max()
            low_60 = hist['最低'].min()
            range_60 = high_60 - low_60
            
            if range_60 > 0:
                position = (close_current - low_60) / range_60
                return position < 0.4
            
            return False
        except:
            return False

    def _check_ma_pullback(self, hist, pd, window: int) -> bool:
        """检查均线回踩确认信号.
        
        条件:
        1. 均线趋势向上 (当前MA > 5日前MA)
        2. 昨日(T-1): 阴线回踩 (收盘 < 开盘, 最低 <= MA*1.01, 收盘 > MA)
        3. 今日(T): 阳线确认 (收盘 > 开盘)
        """
        try:
            if len(hist) < window + 5:
                return False
                
            close = hist['收盘']
            ma = close.rolling(window).mean()
            
            ma_curr = ma.iloc[-1]
            ma_prev_5 = ma.iloc[-6]
            
            # 1. Trend is rising
            if ma_curr <= ma_prev_5:
                return False
                
            # Get Yesterday (T-1) and Today (T)
            today = hist.iloc[-1]
            yesterday = hist.iloc[-2]
            ma_yesterday = ma.iloc[-2]
            
            # 2. Yesterday: Bearish Pullback
            # Bearish
            if yesterday['收盘'] >= yesterday['开盘']:
                return False
            # Pullback (Low touches MA or within 1%)
            if yesterday['最低'] > ma_yesterday * 1.01:
                return False
            # Support (Close above MA)
            if yesterday['收盘'] <= ma_yesterday:
                return False
                
            # 3. Today: Bullish Confirmation
            if today['收盘'] <= today['开盘']:
                return False
                
            return True
        except:
            return False

    def _resample_weekly(self, hist, pd):
        """Resample daily data to weekly."""
        try:
            # Ensure index is datetime
            if not isinstance(hist.index, pd.DatetimeIndex):
                hist = hist.copy()
                hist.index = pd.to_datetime(hist['日期'])
            
            # Resample logic
            weekly = hist.resample('W').agg({
                '开盘': 'first',
                '最高': 'max',
                '最低': 'min',
                '收盘': 'last',
                '成交量': 'sum',
                '成交额': 'sum'
            })
            # Drop incomplete weeks if needed, or keep current week
            return weekly.dropna()
        except:
            return None

    def _check_ma_pullback_weekly(self, hist, pd, window: int) -> bool:
        """检查周线均线回踩确认信号.
        
        逻辑同日线回踩，但基于周线数据.
        """
        try:
            weekly = self._resample_weekly(hist, pd)
            if weekly is None or len(weekly) < window + 5:
                return False
                
            return self._check_ma_pullback(weekly, pd, window)
        except:
            return False


# Singleton
stock_scanner = StockScanner()
