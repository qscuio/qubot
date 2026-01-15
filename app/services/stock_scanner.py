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
from app.services.scanner_utils import calculate_kuangbiao_score

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
            
            icon = {"breakout": "🔺", "volume": "📊", "ma_bullish": "📈", "startup_candidate": "🚀", "kuangbiao": "🏎️", "triple_bullish_shrink_breakout": "🔥"}.get(signal_type, "•")
            name = {"breakout": "突破信号", "volume": "放量信号", "ma_bullish": "多头排列", "startup_candidate": "启动关注", "kuangbiao": "狂飙启动", "triple_bullish_shrink_breakout": "蓄势爆发"}.get(signal_type, signal_type)
            
            text += f"{icon} <b>{name}</b> ({len(stocks)})\n"
            for s in stocks[:8]:
                url = get_chart_url(s["code"], s.get("name"))
                text += f"  • <a href=\"{url}\">{s['name']}</a> ({s['code']})\n"
            if len(stocks) > 8:
                text += f"  ...及其他 {len(stocks) - 8} 只\n"
            text += "\n"
        
        await telegram_service.send_message(settings.STOCK_ALERT_CHANNEL, text, parse_mode="html")
        logger.info(f"Sent scan report with {sum(len(v) for v in signals.values())} signals")
    
        self._last_scan_used_cache = False
        self.is_scanning = False  # Scanning state lock
    
    async def scan_all_stocks(self, force: bool = False, progress_callback = None) -> Dict[str, List[Dict]]:
        """
        Scan all stocks for signals. Wrapper for locking/error handling.
        """
        if self.is_scanning:
            logger.warn("⚠️ Scan already in progress, rejecting duplicate request")
            return self._last_signals or {}

        try:
            self.is_scanning = True
            logger.info("🔍 Starting scan_all_stocks (full scan)")
            self._last_scan_used_cache = False
            
            return await self._scan_impl(force=force, progress_callback=progress_callback)
            
        except Exception as e:
            logger.error(f"❌ Scan failed with error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self._last_signals or {}
        finally:
            self.is_scanning = False

    async def _scan_impl(self, force: bool = False, progress_callback = None) -> Dict[str, List[Dict]]:
        """Internal scan implementation."""
        # Note: lock and try/finally are handled in the wrapper
        _, pd = self._get_libs()
        if not pd:
            logger.error("❌ Failed to load pandas/akshare libraries")
            return {}
        
        signals = {
            "breakout": [],
            "kuangbiao": [], # 狂飙信号 (ScoreA + ScoreB)
            "triple_bullish_shrink_breakout": [], # 三阳一缩一放
            "volume": [],
            "ma_bullish": [],
            "small_bullish_5": [],  # 底部连续5个小阳线
            "volume_price": [],  # 量价启动信号
            "startup_candidate": [], # 启动阶段信号 (Startup Candidate)
            "small_bullish_4": [],  # 底部四连阳
            "small_bullish_4_1_bearish": [],  # 四阳一阴
            "small_bullish_5_1_bearish": [],  # 五阳一阴
            "small_bullish_3_1_bearish_1_bullish": [],  # 三阳一阴一阳
            "small_bullish_5_in_7": [],  # 地位七天五阳
            "strong_first_negative": [],  # 强势股首阴
            "broken_limit_up_streak": [],  # 连板断板
            "pullback_ma5": [],  # 5日线回踩
            "pullback_ma20": [],  # 20日线回踩
            "pullback_ma30": [],  # 30日线回踩
            "pullback_ma5_weekly": [],  # 5周线回踩
            "multi_signal": [],  # 多信号共振(满足≥3个信号)
            # New Trend Signals (Linear Regression Channel)
            "support_linreg_5": [],   # 5日趋势支撑
            "support_linreg_10": [],  # 10日趋势支撑
            "support_linreg_20": [],  # 20日趋势支撑
            "breakout_linreg_5": [],   # 突破5日趋势
            "breakout_linreg_10": [],  # 突破10日趋势
            "breakout_linreg_20": [],  # 突破20日趋势
            
            "top_gainers_weekly": [], # 每周涨幅前40
            "top_gainers_half_month": [], # 每半月涨幅前40
            "top_gainers_monthly": [], # 每月涨幅前40
            "top_gainers_weekly_no_lu": [], # 每周涨幅前40 (未涨停)
            "top_gainers_half_month_no_lu": [], # 每半月涨幅前40 (未涨停)
            "top_gainers_monthly_no_lu": [], # 每月涨幅前40 (未涨停)
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
            
            # Batch processing settings
            BATCH_SIZE = 200
            total_codes = len(codes)
            
            logger.info(f"✅ Found {total_codes} stocks in local DB, starting scan in batches of {BATCH_SIZE}...")
            
            checked = 0
            skipped_insufficient = 0
            
            for i in range(0, total_codes, BATCH_SIZE):
                batch_codes = codes[i : i + BATCH_SIZE]
                
                # Fetch history for this batch only
                local_data = await self._get_local_history_batch(batch_codes)
                
                if not local_data:
                    # Just skip if no data for this batch
                    continue
                
                for code in batch_codes:
                    name = code_name_map.get(code, code)
                    
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

                    # Kuangbiao Signal Check
                    if self._check_kuangbiao(hist, pd, stock_info):
                        signals["kuangbiao"].append(stock_info)

                    if self._check_triple_bullish_shrink_breakout(hist, pd):
                        signals["triple_bullish_shrink_breakout"].append(stock_info)

                    if self._check_startup_candidate(hist, pd):
                        signals["startup_candidate"].append(stock_info)

                    if self._check_small_bullish_4(hist, pd):
                        signals["small_bullish_4"].append(stock_info)

                    if self._check_small_bullish_4_1_bearish(hist, pd):
                        signals["small_bullish_4_1_bearish"].append(stock_info)

                    if self._check_small_bullish_5_1_bearish(hist, pd):
                        signals["small_bullish_5_1_bearish"].append(stock_info)

                    if self._check_small_bullish_3_1_bearish_1_bullish(hist, pd):
                        signals["small_bullish_3_1_bearish_1_bullish"].append(stock_info)

                    if self._check_small_bullish_5_in_7(hist, pd):
                        signals["small_bullish_5_in_7"].append(stock_info)

                    if self._check_strong_first_negative(hist, pd):
                        signals["strong_first_negative"].append(stock_info)

                    if self._check_broken_limit_up_streak(hist, pd, code):
                        signals["broken_limit_up_streak"].append(stock_info)

                    if self._check_ma_pullback(hist, pd, 5):
                        signals["pullback_ma5"].append(stock_info)

                    if self._check_ma_pullback(hist, pd, 20):
                        signals["pullback_ma20"].append(stock_info)

                    if self._check_ma_pullback(hist, pd, 30):
                        signals["pullback_ma30"].append(stock_info)

                    if self._check_ma_pullback_weekly(hist, pd, 5):
                        signals["pullback_ma5_weekly"].append(stock_info)
                    
                    # Trend Support Signals (LinReg)
                    if self._check_linreg_support(hist, pd, 5):
                        signals["support_linreg_5"].append(stock_info)
                    if self._check_linreg_support(hist, pd, 10):
                        signals["support_linreg_10"].append(stock_info)
                    if self._check_linreg_support(hist, pd, 20):
                        signals["support_linreg_20"].append(stock_info)

                    # Trend Breakout Signals (LinReg)
                    if self._check_linreg_breakout(hist, pd, 5):
                        signals["breakout_linreg_5"].append(stock_info)
                    if self._check_linreg_breakout(hist, pd, 10):
                        signals["breakout_linreg_10"].append(stock_info)
                    if self._check_linreg_breakout(hist, pd, 20):
                        signals["breakout_linreg_20"].append(stock_info)
                    
                    # Count how many signals this stock has
                    signal_count = sum([
                        stock_info in signals["breakout"],
                        stock_info in signals["volume"],
                        stock_info in signals["ma_bullish"],
                        stock_info in signals["small_bullish_5"],
                        stock_info in signals["volume_price"],
                        stock_info in signals["startup_candidate"],
                        stock_info in signals["kuangbiao"],
                        stock_info in signals["triple_bullish_shrink_breakout"],
                        stock_info in signals["small_bullish_4"],
                        stock_info in signals["small_bullish_4_1_bearish"],
                        stock_info in signals["small_bullish_5_1_bearish"],
                        stock_info in signals["small_bullish_3_1_bearish_1_bullish"],
                        stock_info in signals["small_bullish_5_in_7"],
                        stock_info in signals["strong_first_negative"],
                        stock_info in signals["broken_limit_up_streak"],
                        stock_info in signals["pullback_ma5"],
                        stock_info in signals["pullback_ma20"],
                        stock_info in signals["pullback_ma30"],
                        stock_info in signals["pullback_ma5_weekly"],
                        stock_info in signals["pullback_ma5_weekly"],
                    ])
                    
                    # ═══════════════════════════════════════════════════════════
                    # Top Gainers Calculation
                    # ═══════════════════════════════════════════════════════════
                    # Calculate gains for 5, 10, 20 days
                    try:
                        closes = hist['收盘'].values
                        highs = hist['最高'].values
                        
                        # 5 Days (Weekly)
                        if len(closes) >= 6:
                            gain_5d = (closes[-1] - closes[-6]) / closes[-6] * 100
                            # Check limit up in last 5 days (approx > 9.5%)
                            # We check daily returns
                            has_lu_5d = False
                            for i in range(-5, 0):
                                if i == -len(closes): break # Safety
                                prev_c = closes[i-1]
                                curr_c = closes[i]
                                if prev_c > 0 and (curr_c - prev_c) / prev_c > 0.095:
                                    has_lu_5d = True
                                    break
                            
                            signals.setdefault("_temp_gainers_5d", []).append({
                                **stock_info, "gain": gain_5d, "has_lu": has_lu_5d
                            })
                        
                        # 10 Days (Half-Month)
                        if len(closes) >= 11:
                            gain_10d = (closes[-1] - closes[-11]) / closes[-11] * 100
                            has_lu_10d = False
                            for i in range(-10, 0):
                                if i == -len(closes): break
                                prev_c = closes[i-1]
                                curr_c = closes[i]
                                if prev_c > 0 and (curr_c - prev_c) / prev_c > 0.095:
                                    has_lu_10d = True
                                    break
                                    
                            signals.setdefault("_temp_gainers_10d", []).append({
                                **stock_info, "gain": gain_10d, "has_lu": has_lu_10d
                            })

                        # 20 Days (Monthly)
                        if len(closes) >= 21:
                            gain_20d = (closes[-1] - closes[-21]) / closes[-21] * 100
                            has_lu_20d = False
                            for i in range(-20, 0):
                                if i == -len(closes): break
                                prev_c = closes[i-1]
                                curr_c = closes[i]
                                if prev_c > 0 and (curr_c - prev_c) / prev_c > 0.095:
                                    has_lu_20d = True
                                    break
                                    
                            signals.setdefault("_temp_gainers_20d", []).append({
                                **stock_info, "gain": gain_20d, "has_lu": has_lu_20d
                            })

                    except Exception as e:
                        pass # Ignore calculation errors for gainers
                    
                    # Add to multi-signal list if 3+ signals
                    if signal_count >= 3:
                        signals["multi_signal"].append({
                            **stock_info,
                            "signal_count": signal_count
                        })
                    
                    checked += 1
                
                # Report progress after each batch
                logger.info(f"Scanning progress: {checked}/{total_codes} stocks checked ({((checked) / total_codes * 100):.1f}%)")
                if progress_callback:
                    try:
                        await progress_callback(checked, total_codes)
                    except Exception:
                        pass
                
                # Yield control to event loop to prevent blocking
                await asyncio.sleep(0.01)

            if skipped_insufficient > 0:
                logger.info(f"⏭️ Skipped {skipped_insufficient} stocks with insufficient history (<21 days)")
            
            # Process Top Gainers
            # Weekly
            temp_5d = signals.pop("_temp_gainers_5d", [])
            temp_5d.sort(key=lambda x: x["gain"], reverse=True)
            signals["top_gainers_weekly"] = temp_5d[:40]
            signals["top_gainers_weekly_no_lu"] = [s for s in temp_5d if not s["has_lu"]][:40]
            
            # Half-Month
            temp_10d = signals.pop("_temp_gainers_10d", [])
            temp_10d.sort(key=lambda x: x["gain"], reverse=True)
            signals["top_gainers_half_month"] = temp_10d[:40]
            signals["top_gainers_half_month_no_lu"] = [s for s in temp_10d if not s["has_lu"]][:40]
            
            # Monthly
            temp_20d = signals.pop("_temp_gainers_20d", [])
            temp_20d.sort(key=lambda x: x["gain"], reverse=True)
            signals["top_gainers_monthly"] = temp_20d[:40]
            signals["top_gainers_monthly_no_lu"] = [s for s in temp_20d if not s["has_lu"]][:40]

            
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
            logger.error(f"❌ Scan implementation error: {e}")
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
            max_rows = 150

            rows = await db.pool.fetch("""
                SELECT code, date, open, high, low, close, volume, turnover_rate
                FROM (
                    SELECT code, date, open, high, low, close, volume, turnover_rate,
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
                        '最低': float(r['low']),
                        '成交量': float(r['volume']),
                        '换手率': float(r['turnover_rate']) if r['turnover_rate'] is not None else 0.0,
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

    def _check_small_bullish_3_1_bearish_1_bullish(self, hist, pd) -> bool:
        """检查三阳一阴一阳信号.
        
        条件:
        1. T-4到T-2 (3日): 小阳线 (实体0.5%-3%)
        2. T-1 (昨日): 阴线
        3. T (今日): 阳线
        4. 股价在近60日低位
        """
        try:
            # Get last 5 days
            last_5 = hist.tail(5)
            
            if len(last_5) < 5:
                return False
            
            # 1. Check first 3 days are small bullish
            for i in range(3):
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
            
            # 2. Check yesterday (T-1) is bearish
            yesterday = last_5.iloc[-2]
            if yesterday['收盘'] >= yesterday['开盘']:
                return False
                
            # 3. Check today (T) is bullish
            today = last_5.iloc[-1]
            if today['收盘'] <= today['开盘']:
                return False
            
            # 4. Check if at bottom
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

    def _check_small_bullish_5_in_7(self, hist, pd) -> bool:
        """检查地位七天五阳信号.
        
        条件:
        1. 最近7日中至少有5日是小阳线
           小阳线定义: 收盘 > 开盘 且 实体涨幅在 0.5% - 3.0% 之间
        2. 股价在近60日低位 (区间下部40%)
        """
        try:
            # Get last 7 days
            last_7 = hist.tail(7)
            
            if len(last_7) < 7:
                return False
            
            small_bullish_count = 0
            
            # Check for small bullish candles
            for i in range(len(last_7)):
                row = last_7.iloc[i]
                open_price = row['开盘']
                close = row['收盘']
                
                # Must be bullish
                if close <= open_price:
                    continue
                    
                # Calculate body percentage
                if open_price > 0:
                    body_pct = (close - open_price) / open_price * 100
                    
                    # Small bullish: 0.5% - 3%
                    if 0.5 <= body_pct <= 3.0:
                        small_bullish_count += 1
            
            # Condition 1: At least 5 small bullish candles
            if small_bullish_count < 5:
                return False
            
            # Condition 2: Check if at bottom (current price in lower 40% of 60-day range)
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

    def _check_strong_first_negative(self, hist, pd) -> bool:
        """检查强势股首阴信号.
        
        条件:
        1. 强势: 近20日涨幅 > 30%
        2. 首阴: 昨日(T-1)是阳线, 今日(T)是阴线
        """
        try:
            if len(hist) < 21:
                return False
                
            # Use T-1 close vs T-21 close to avoid today's drop affecting calculation
            close = hist['收盘']
            close_yesterday = close.iloc[-2]
            close_20_ago = close.iloc[-21]
            
            if close_20_ago == 0:
                return False
                
            gain_pct = (close_yesterday - close_20_ago) / close_20_ago
            if gain_pct <= 0.3:
                return False
                
            # 2. Check First Negative
            # Yesterday (T-1) must be Bullish
            yesterday = hist.iloc[-2]
            if yesterday['收盘'] <= yesterday['开盘']:
                return False
                
            # Today (T) must be Bearish
            today = hist.iloc[-1]
            if today['收盘'] >= today['开盘']:
                return False
                
            return True
        except:
            return False

    def _check_broken_limit_up_streak(self, hist, pd, code: str) -> bool:
        """检查连板断板信号.
        
        条件:
        1. 连板: T-2 和 T-1 都是涨停
        2. 断板: T (今日) 不是涨停
        """
        try:
            if len(hist) < 3:
                return False
                
            # Determine limit up threshold
            limit_pct = 9.5
            if code.startswith('688') or code.startswith('300'):
                limit_pct = 19.5
                
            # Check T-2 and T-1 (Must be Limit Up)
            for i in [-2, -3]:
                row = hist.iloc[i]
                prev_close = hist.iloc[i-1]['收盘']
                if prev_close == 0:
                    return False
                
                gain = (row['收盘'] - prev_close) / prev_close * 100
                if gain < limit_pct:
                    return False
            
            # Check T (Today) - Must NOT be Limit Up
            today = hist.iloc[-1]
            yesterday_close = hist.iloc[-2]['收盘']
            if yesterday_close == 0:
                return False
                
            today_gain = (today['收盘'] - yesterday_close) / yesterday_close * 100
            if today_gain >= limit_pct:
                return False
                
            return True
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

    # --- Trend Channel (Linear Regression) Helpers ---
    def _calculate_linreg_channel(self, series: pd.Series, window: int) -> Tuple[float, float, float, float]:
        """Calculate Linear Regression Channel for the window.
        
        Returns:
            (slope, current_mid, current_upper, current_lower)
            slope: Slope of the regression line
            current_mid: Regression value at the last point (predict)
            current_upper: Mid + 2 * StdDev
            current_lower: Mid - 2 * StdDev
        """
        try:
            if len(series) < window:
                return 0.0, 0.0, 0.0, 0.0
                
            y = series.iloc[-window:].values
            x = np.arange(window)
            
            # Linear Regression: y = mx + b
            # Simple 1D-polyfit
            slope, intercept = np.polyfit(x, y, 1)
            
            # Predicted values
            y_pred = slope * x + intercept
            
            # Std Dev of residuals
            residuals = y - y_pred
            std_dev = np.std(residuals)
            
            current_mid = slope * (window - 1) + intercept
            current_upper = current_mid + 2 * std_dev
            current_lower = current_mid - 2 * std_dev
            
            return slope, current_mid, current_upper, current_lower
        except:
            return 0.0, 0.0, 0.0, 0.0

    def _check_linreg_support(self, hist, pd, window: int) -> bool:
        """Check for Support at Lower Rail of Linear Regression Channel.
        
        Conditions:
        1. Trend is UP (Slope > 0).
        2. Price Drops to Support: Low <= Lower Rail (or close to it).
        3. Support Holds: Close > Lower Rail.
        """
        try:
            if len(hist) < window + 2:
                return False
                
            close_series = hist['收盘']
            slope, mid, upper, lower = self._calculate_linreg_channel(close_series, window)
            
            # 1. Trend Rising
            # Slope tells us units of price change per day. 
            # Needs to be significantly positive? Or just > 0. Let's say > 0.
            if slope <= 0:
                return False
            
            # 2. Touched Support
            # Low <= Lower * 1.01 (within 1% above lower rail, or below it)
            low_curr = hist['最低'].iloc[-1]
            if low_curr > lower * 1.01:
                return False
                
            # 3. Held Support (Close > Lower)
            # Actually if it breaks lower rail significantly it might be bad.
            # But "Support" usually means it tested it.
            close_curr = hist['收盘'].iloc[-1]
            if close_curr < lower * 0.99: # Allow small breakdown but must be mostly above?
                # If closed deep below, support broken
                return False
                
            return True
        except:
            return False

    def _check_linreg_breakout(self, hist, pd, window: int) -> bool:
        """Check for Breakout of Upper Rail of Linear Regression Channel.
        
        Conditions:
        1. Trend is UP.
        2. Breakout Pressure: Close > Upper Rail.
        """
        try:
            if len(hist) < window + 2:
                return False
                
            close_series = hist['收盘']
            slope, mid, upper, lower = self._calculate_linreg_channel(close_series, window)
            
            # 1. Trend Rising
            if slope <= 0:
                return False
            
            # 2. Breakout
            close_curr = hist['收盘'].iloc[-1]
            if close_curr > upper:
                return True
                
            return False
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

    def _check_kuangbiao(self, hist, pd, stock_info) -> bool:
        """检查狂飙信号 (两阶段评分)."""
        try:
            score_a, score_b, state = calculate_kuangbiao_score(hist)
            if state == "B": # Launch Trigger
                # Enrich info with scores for debugging/display if needed
                stock_info["score_a"] = score_a
                stock_info["score_b"] = score_b
                return True
            return False
        except:
            return False

    def _check_triple_bullish_shrink_breakout(self, hist, pd) -> bool:
        """检查“三阳一缩一放”信号.
        
        模式:
        1. T-4 到 T-2 (3天): 连续小阳线 (0.5% < 实体 < 4%)
        2. T-1 (1天): 缩量小阴或十字星 (Vol < T-2 Vol)
        3. T (今日): 放量实体突破 (Vol > T-1 Vol * 1.5, 收盘 > T-1最高, 实体饱满)
        """
        try:
            if len(hist) < 6:
                return False
                
            # Data slices
            last_5 = hist.tail(5)
            # Days: [-5, -4, -3, -2, -1] -> [T-4, T-3, T-2, T-1, T] in array indices 0..4
            
            # 1. Check T-4, T-3, T-2 (Indices 0, 1, 2) - Small Bullish
            for i in range(3):
                row = last_5.iloc[i]
                op = row['开盘']
                cl = row['收盘']
                
                # Must be Bullish
                if cl <= op: return False
                
                # Body Check (0.5% - 4%)
                body_pct = (cl - op) / op * 100
                if not (0.5 <= body_pct <= 4.0):
                    return False
            
            # 2. Check T-1 (Index 3) - Shrink + Small Bearish/Doji
            t_minus_1 = last_5.iloc[3]
            t_minus_2 = last_5.iloc[2]
            
            # Shrink Volume: Vol(T-1) < Vol(T-2)
            if t_minus_1['成交量'] >= t_minus_2['成交量']:
                return False
                
            # Candle Shape: Small Bearish OR Doji
            op_1 = t_minus_1['开盘']
            cl_1 = t_minus_1['收盘']
            body_pct_1 = abs(cl_1 - op_1) / op_1 * 100
            
            is_bearish = cl_1 < op_1
            is_doji = body_pct_1 < 0.5
            
            # Condition: Must be (Small Bearish) OR (Doji)
            # If Bearish, body should not be massive (e.g. < 3%)
            if is_bearish and body_pct_1 > 3.0:
                return False
            # If Bullish, MUST be Doji
            if not is_bearish and not is_doji:
                return False

            # 3. Check T (Index 4) - Volume Surge + Breakout
            t_now = last_5.iloc[4]
            op_0 = t_now['开盘']
            cl_0 = t_now['收盘']
            vol_0 = t_now['成交量']
            vol_1 = t_minus_1['成交量']
            
            # Bullish
            if cl_0 <= op_0: return False
            
            # Volume Surge (vs T-1)
            if vol_0 <= vol_1 * 1.5:
                # Relax slightly if it's huge breakout? No, strict for now.
                return False
                
            # Breakout T-1 High (to ensure we recover the wash)
            if cl_0 <= t_minus_1['最高']:
                return False
                
            # Solid Body? (Body > 1.5% or Body/Range > 0.5)
            # Let's say Body > 1.5% to show strength
            body_pct_0 = (cl_0 - op_0) / op_0 * 100
            if body_pct_0 < 1.5:
                return False
                
            return True

        except:
            return False

    def _check_startup_candidate(self, hist, pd) -> bool:
        """检查“启动阶段”信号.
        
        核心思想: 主力开始试盘 / 建仓 → 情绪尚未扩散 → 波动率和成交量刚抬头
        
        指标体系:
        1. 趋势过滤: Close < MA200, MA20 > MA60, MA60走平或向上
        2. 结构压缩: ATR(14)/Close < 3%, BB Width < 120日低点 * 1.2
        3. 量能异动: 1.8x < Volume < 3.5x MA20(Vol)
        4. 形态突破: Close > 20日最高, 实体/振幅 > 0.6
        5. 资金行为: 3% < 换手率 < 10%
        """
        try:
            # Need at least 120 days for Bollinger Band Width historical comparison
            if len(hist) < 120:
                return False
            
            closes = hist['收盘']
            highs = hist['最高']
            lows = hist['最低']
            opens = hist['开盘']
            volumes = hist['成交量']
            turnover_rates = hist['换手率']
            
            # Latest values
            close = closes.iloc[-1]
            open_p = opens.iloc[-1]
            high = highs.iloc[-1]
            low = lows.iloc[-1]
            vol = volumes.iloc[-1]
            turnover = turnover_rates.iloc[-1]

            # 1. 趋势过滤
            ma20 = closes.rolling(20).mean()
            ma60 = closes.rolling(60).mean()
            ma200 = closes.rolling(200).mean()
            
            # Close < MA200 (if we have 200 days data, otherwise skip this check or use max available)
            if len(closes) >= 200:
                if close >= ma200.iloc[-1]:
                    return False
            
            # MA20 > MA60
            if ma20.iloc[-1] <= ma60.iloc[-1]:
                return False
                
            # MA60 走平或向上 (Slope >= 0)
            # Check slope over last 3-5 days
            ma60_slope = ma60.iloc[-1] - ma60.iloc[-5]
            if ma60_slope < 0:
                return False

            # 2. 结构压缩
            # ATR(14)
            tr = pd.concat([
                highs - lows,
                (highs - closes.shift(1)).abs(),
                (lows - closes.shift(1)).abs()
            ], axis=1).max(axis=1)
            atr14 = tr.rolling(14).mean().iloc[-1]
            
            if (atr14 / close) >= 0.03:
                return False
                
            # Bollinger Band Width
            std20 = closes.rolling(20).std()
            bb_width = (4 * std20) / ma20 
            
            current_bb_width = bb_width.iloc[-1]
            
            # Compare with lowest width in last 120 days
            min_bb_width_120 = bb_width.rolling(120).min().iloc[-1]
            
            if current_bb_width >= min_bb_width_120 * 1.2:
                return False

            # 3. 量能异动
            ma20_vol = volumes.rolling(20).mean().iloc[-1]
            if ma20_vol == 0: return False
            
            vol_ratio = vol / ma20_vol
            if not (1.8 < vol_ratio < 3.5):
                return False

            # 4. 形态突破
            # Close > Highest(High, 20) (excluding today)
            high_20_prev = highs.iloc[-21:-1].max()
            if close <= high_20_prev:
                return False
                
            # (Close - Open) / (High - Low) > 0.6
            range_len = high - low
            if range_len == 0: return False
            body_len = close - open_p
            if (body_len / range_len) <= 0.6:
                return False

            # 5. 资金行为 (换手率)
            if not (3.0 <= turnover <= 10.0):
                return False

            return True

        except Exception as e:
            return False


# Singleton
stock_scanner = StockScanner()
