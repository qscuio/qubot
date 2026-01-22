"""
AI Stock Scanner (启动信号扫描器)

Scans all A-share stocks using the modular signal detection system.
Signal implementations are in app/services/scanner/signals/.
"""

import asyncio
import base64
from typing import List, Dict
from collections import defaultdict

from app.core.logger import Logger
from app.core.database import db
from app.core.config import settings
from app.core.stock_links import get_chart_url
from app.core.timezone import china_now, china_today

logger = Logger("StockScanner")


class StockScanner:
    """Service for scanning stocks with modular signal detection."""
    
    def __init__(self):
        self.is_running = False
        self._scheduler_task = None
        self._ak = None
        self._pd = None
        self._last_scan_signature = None
        self._last_signals = None
        self._last_scan_used_cache = False
        self.is_scanning = False
        
        # Data cache (independent of signals)
        self._cached_stocks_data = None
        self._cached_data_signature = None

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
        from app.services.scanner import SignalRegistry
        
        if not settings.STOCK_ALERT_CHANNEL:
            return
        
        logger.info("Starting full market scan...")
        signals = await self.scan_all_stocks()
        
        if not signals:
            logger.info("No signals found")
            return
        
        # Get icons and names from registry
        icons = SignalRegistry.get_icons()
        names = SignalRegistry.get_names()
        
        now = china_now()
        text = f"🔍 <b>启动信号扫描</b> {now.strftime('%Y-%m-%d %H:%M')}\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for signal_type, stocks in signals.items():
            if not stocks:
                continue
            
            icon = icons.get(signal_type, "•")
            name = names.get(signal_type, signal_type)
            
            text += f"{icon} <b>{name}</b> ({len(stocks)})\n"
            for s in stocks[:8]:
                url = get_chart_url(s["code"], s.get("name"))
                text += f"  • <a href=\"{url}\">{s.get('name', s['code'])}</a> ({s['code']})\n"
            if len(stocks) > 8:
                text += f"  ...及其他 {len(stocks) - 8} 只\n"
            text += "\n"
        
        await telegram_service.send_message(settings.STOCK_ALERT_CHANNEL, text, parse_mode="html")
        logger.info(f"Sent scan report with {sum(len(v) for v in signals.values())} signals")
    
        self._last_scan_used_cache = False
        self.is_scanning = False
    
    async def scan_all_stocks(self, force: bool = False, progress_callback=None, enabled_signals: List[str] = None) -> Dict[str, List[Dict]]:
        """Scan all stocks for signals.
        
        Args:
            force: Force rescan even if cache is valid
            progress_callback: Async callback for progress updates  
            enabled_signals: List of signal IDs to scan (None = all signals)
        """
        if self.is_scanning:
            logger.warn("⚠️ Scan already in progress, rejecting duplicate request")
            return self._last_signals or {}

        try:
            self.is_scanning = True
            sig_desc = f"signals: {enabled_signals}" if enabled_signals else "all signals"
            logger.info(f"🔍 Starting scan_all_stocks ({sig_desc})")
            self._last_scan_used_cache = False
            
            return await self._scan_impl(force=force, progress_callback=progress_callback, enabled_signals=enabled_signals)
            
        except Exception as e:
            logger.error(f"❌ Scan failed with error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self._last_signals or {}
        finally:
            self.is_scanning = False

    async def _scan_impl(self, force: bool = False, progress_callback=None, enabled_signals: List[str] = None) -> Dict[str, List[Dict]]:
        """Internal scan implementation using modular scanner with ProcessPoolExecutor."""
        from app.services.scanner import run_scan, SignalRegistry
        import concurrent.futures
        import functools
        
        _, pd = self._get_libs()
        if not pd:
            logger.error("❌ Failed to load pandas/akshare libraries")
            return {}
        
        if not db.pool:
            logger.error("❌ Database not connected, cannot scan")
            return {}

        # Determine history limit based on active signals
        active_signals = []
        if enabled_signals:
            for sig_id in enabled_signals:
                s = SignalRegistry.get_by_id(sig_id)
                if s: active_signals.append(s)
        else:
            active_signals = SignalRegistry.get_all(enabled_only=True)
        
        limit = 150
        if active_signals:
            limit = max((s.min_bars for s in active_signals), default=150)
        
        limit = max(limit, 150) + 20
        bucket_size = 300
        bucketed_limit = ((limit + bucket_size - 1) // bucket_size) * bucket_size
        
        try:
            today = china_today()
            logger.info(f"📅 Scan date: {today}")
            
            # Check cache signature
            logger.info("📋 Checking cache signature...")
            count_row = await db.pool.fetchrow("""
                SELECT MAX(date) as max_date, 
                       COUNT(DISTINCT code) as stock_count,
                       SUM(volume) as total_vol
                FROM stock_history
                WHERE date >= $1::date - INTERVAL '7 days'
            """, today)
            
            max_date = count_row['max_date'] if count_row else None
            max_date_count = count_row['stock_count'] if count_row else 0
            total_vol = count_row['total_vol'] or 0
            
            # 1. Check Result Cache
            signature = (max_date, max_date_count, total_vol, str(enabled_signals)) if max_date else None
            if not force and signature and self._last_signals is not None and signature == self._last_scan_signature:
                logger.info("♻️ Using cached scan results")
                self._last_scan_used_cache = True
                return self._last_signals
            
            # 2. Check/Load Data
            data_signature = (max_date, max_date_count, total_vol, bucketed_limit) if max_date else None
            stocks_data = None
            stock_names = None
            
            if not force and data_signature and self._cached_stocks_data and data_signature == self._cached_data_signature:
                logger.info(f"♻️ Using cached stock data (limit={bucketed_limit})")
                stocks_data, stock_names = self._cached_stocks_data
            else:
                # Try Redis
                redis_key = f"scanner:data:v3:{max_date}:{max_date_count}:{total_vol}:{bucketed_limit}"
                loaded_from_redis = False
                if db.redis and not force:
                    try:
                        cached_blob = await db.redis.get(redis_key)
                        if cached_blob:
                            logger.info("♻️ Using Redis cached stock data")
                            import pickle
                            cached_bytes = base64.b64decode(cached_blob)
                            stocks_data, stock_names = pickle.loads(cached_bytes)
                            loaded_from_redis = True
                    except Exception as e:
                        logger.error(f"Redis cache error: {e}")

                if not loaded_from_redis:
                    logger.info(f"📥 Loading stock data from DB (requested={limit})...")
                    stocks_data, stock_names = await self._load_stocks_data_for_scan(today, progress_callback, limit=bucketed_limit)
                    if db.redis and stocks_data:
                        try:
                            import pickle
                            blob_bytes = pickle.dumps((stocks_data, stock_names))
                            blob_str = base64.b64encode(blob_bytes).decode('utf-8')
                            await db.redis.setex(redis_key, 86400, blob_str)
                        except Exception as e:
                            logger.error(f"Failed to save to Redis: {e}")
                
                if stocks_data and data_signature:
                    self._cached_stocks_data = (stocks_data, stock_names)
                    self._cached_data_signature = data_signature
            
            if not stocks_data:
                logger.warn("⚠️ No stock data available for scanning")
                return {}
            
            sig_count = len(enabled_signals) if enabled_signals else SignalRegistry.count()
            total_stocks = len(stocks_data)
            logger.info(f"📊 Running scanner on {total_stocks} stocks with {sig_count} signal(s)")
            
            # --- START MULTIPROCESSING SCAN ---
            # Run scan in a separate process to avoid blocking the asyncio loop
            # We process in batches to provide progress updates and avoid huge IPC payloads
            
            final_results = defaultdict(list)
            stock_codes = list(stocks_data.keys())
            batch_size = 300
            
            # Use ProcessPoolExecutor
            loop = asyncio.get_event_loop()
            with concurrent.futures.ProcessPoolExecutor(max_workers=2) as executor:
                processed_count = 0
                
                # Report initial progress
                if progress_callback:
                    await progress_callback(0, total_stocks, phase="scanning")
                
                for i in range(0, total_stocks, batch_size):
                    batch_codes = stock_codes[i : i + batch_size]
                    batch_data = {code: stocks_data[code] for code in batch_codes}
                    batch_names = {code: stock_names.get(code, code) for code in batch_codes}
                    
                    # Submit task to executor
                    # Note: We must NOT pass callbacks to the subprocess
                    task = functools.partial(
                        run_scan_sync_wrapper,
                        batch_data,
                        batch_names,
                        enabled_signals
                    )
                    
                    # Run in executor
                    batch_results = await loop.run_in_executor(executor, task)
                    
                    # Merge results
                    for sig, items in batch_results.items():
                        final_results[sig].extend(items)
                    
                    processed_count += len(batch_codes)
                    
                    # Update progress
                    if progress_callback:
                        await progress_callback(processed_count, total_stocks, phase="scanning")
            
            # --- END MULTIPROCESSING SCAN ---
            
            logger.info(f"✅ Signal scan complete, calculating top gainers...")
            
            # Top gainers are light enough to run here or could be moved too
            top_gainers = await self._calculate_top_gainers(stocks_data, stock_names)
            final_results.update(top_gainers)
            
            if signature:
                self._last_scan_signature = signature
                self._last_signals = final_results
            
            total_signals = sum(len(v) for v in final_results.values())
            logger.info(f"✅ Scan complete: {total_signals} signals found")
            
            return final_results
            
        except Exception as e:
            logger.error(f"❌ Scan error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {}




    async def _load_stocks_data_for_scan(self, today, progress_callback=None, limit: int = 150) -> tuple:
        """Load stock data for scanning.
        
        Returns:
            (stocks_data, stock_names) tuple
        """
        # Get stock codes with recent data
        rows = await db.pool.fetch("""
            SELECT DISTINCT code
            FROM stock_history 
            WHERE date >= $1::date - INTERVAL '7 days'
              AND code ~ '^[036]'
        """, today)
        
        if not rows:
            return {}, {}
        
        codes = [r['code'] for r in rows]
        
        # Get stock names
        stock_names = {code: code for code in codes}
        try:
            name_rows = await db.pool.fetch("""
                SELECT code, name FROM stock_info WHERE code = ANY($1)
            """, codes)
            for row in name_rows:
                if row.get('name'):
                    stock_names[row['code']] = row['name']
        except Exception:
            pass
        
        # Load history data with progress
        stocks_data = await self._get_local_history_batch(codes, progress_callback, limit=limit)
        
        return stocks_data, stock_names

    async def _get_local_history_batch(self, codes: List[str], progress_callback=None, limit: int = 150) -> Dict[str, any]:
        """Fetch recent history for multiple stocks from local database.
        
        Processes in batches of 300 codes to avoid blocking.
        Returns a dict mapping code -> DataFrame.
        """
        if not db.pool:
            return {}
        
        _, pd = self._get_libs()
        if not pd:
            return {}
        
        try:
            min_rows = 21
            max_rows = limit
            batch_size = 300
            
            result = {}
            total_codes = len(codes)
            total_batches = (total_codes + batch_size - 1) // batch_size
            
            # Process in batches
            for batch_start in range(0, total_codes, batch_size):
                batch_end = min(batch_start + batch_size, total_codes)
                batch_codes = codes[batch_start:batch_end]
                batch_num = batch_start // batch_size + 1
                
                logger.info(f"📥 Fetching batch {batch_num}/{total_batches}: {len(batch_codes)} codes...")
                
                # Report progress to user
                if progress_callback:
                    try:
                        await progress_callback(batch_num, total_batches, phase="loading")
                    except Exception:
                        pass
                
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
                """, batch_codes, max_rows)
                
                if not rows:
                    continue
                
                # Process rows
                by_code = defaultdict(list)
                for row in rows:
                    by_code[row['code']].append(row)
                
                for code, code_rows in by_code.items():
                    if len(code_rows) >= min_rows:
                        df = pd.DataFrame([{
                            '日期': r['date'],
                            '开盘': float(r['open']),
                            '收盘': float(r['close']),
                            '最高': float(r['high']),
                            '最低': float(r['low']),
                            '成交量': float(r['volume']),
                            '换手率': float(r['turnover_rate']) if r['turnover_rate'] is not None else 0.0,
                        } for r in code_rows])
                        df = df.sort_values('日期').reset_index(drop=True)
                        result[code] = df
                
                # Yield to event loop between batches
                await asyncio.sleep(0)
            
            logger.info(f"✅ Loaded {len(result)} stocks from local DB")
            return result

        except Exception as e:
            logger.warn(f"Failed to load local history: {e}")
            import traceback
            logger.warn(traceback.format_exc())
            return {}

    async def _calculate_top_gainers(self, stocks_data: dict, stock_names: dict) -> dict:
        """Calculate top gainers for various time periods.
        
        Returns dict with top_gainers_* keys.
        """
        signals = {
            "top_gainers_weekly": [],
            "top_gainers_half_month": [],
            "top_gainers_monthly": [],
            "top_gainers_weekly_no_lu": [],
            "top_gainers_half_month_no_lu": [],
            "top_gainers_monthly_no_lu": [],
        }
        
        temp_5d = []
        temp_10d = []
        temp_20d = []
        
        for code, hist in stocks_data.items():
            try:
                closes = hist['收盘'].values
                name = stock_names.get(code, code)
                
                # 5 Days (Weekly)
                if len(closes) >= 6:
                    gain_5d = (closes[-1] - closes[-6]) / closes[-6] * 100
                    has_lu = any(
                        (closes[i] - closes[i-1]) / closes[i-1] > 0.095
                        for i in range(-5, 0) if i > -len(closes)
                    )
                    temp_5d.append({"code": code, "name": name, "gain": gain_5d, "has_lu": has_lu})
                
                # 10 Days (Half-Month)
                if len(closes) >= 11:
                    gain_10d = (closes[-1] - closes[-11]) / closes[-11] * 100
                    has_lu = any(
                        (closes[i] - closes[i-1]) / closes[i-1] > 0.095
                        for i in range(-10, 0) if i > -len(closes)
                    )
                    temp_10d.append({"code": code, "name": name, "gain": gain_10d, "has_lu": has_lu})
                
                # 20 Days (Monthly)
                if len(closes) >= 21:
                    gain_20d = (closes[-1] - closes[-21]) / closes[-21] * 100
                    has_lu = any(
                        (closes[i] - closes[i-1]) / closes[i-1] > 0.095
                        for i in range(-20, 0) if i > -len(closes)
                    )
                    temp_20d.append({"code": code, "name": name, "gain": gain_20d, "has_lu": has_lu})
                    
            except Exception:
                continue
        
        # Sort and take top 40
        temp_5d.sort(key=lambda x: x["gain"], reverse=True)
        signals["top_gainers_weekly"] = temp_5d[:40]
        signals["top_gainers_weekly_no_lu"] = [s for s in temp_5d if not s["has_lu"]][:40]
        
        temp_10d.sort(key=lambda x: x["gain"], reverse=True)
        signals["top_gainers_half_month"] = temp_10d[:40]
        signals["top_gainers_half_month_no_lu"] = [s for s in temp_10d if not s["has_lu"]][:40]
        
        temp_20d.sort(key=lambda x: x["gain"], reverse=True)
        signals["top_gainers_monthly"] = temp_20d[:40]
        signals["top_gainers_monthly_no_lu"] = [s for s in temp_20d if not s["has_lu"]][:40]
        
        return signals


# Singleton
stock_scanner = StockScanner()

def run_scan_sync_wrapper(stocks_data, stock_names, enabled_signals):
    """Sync wrapper to run scanner in a separate process.
    
    This function must be top-level to be picklable.
    """
    import asyncio
    from app.services.scanner import run_scan
    
    # Create a new event loop for the subprocess if needed, 
    # but run_scan is async, so we need to run it synchronously here.
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        results = loop.run_until_complete(
            run_scan(stocks_data, stock_names, progress_callback=None, enabled_signals=enabled_signals)
        )
        loop.close()
        return results
    except Exception as e:
        print(f"Subprocess scan error: {e}")
        return {}
