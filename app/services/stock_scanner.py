"""
AI Stock Scanner (启动信号扫描器)

Scans all A-share stocks using the modular signal detection system.
Signal implementations are in app/services/scanner/signals/.
"""

import asyncio
import base64
import concurrent.futures
import atexit
from typing import List, Dict
from collections import defaultdict

from app.core.logger import Logger
from app.core.database import db
from app.core.config import settings
from app.core.stock_links import get_chart_url
from app.core.timezone import china_now, china_today

logger = Logger("StockScanner")

# Stream scan when the stock universe is large to avoid OOM on low-memory hosts.
STREAMING_SCAN_THRESHOLD = 1200
STREAMING_BATCH_SIZE = 300

# Module-level persistent executor to avoid spawn overhead and blocking issues
_scan_executor = None

def _get_scan_executor() -> concurrent.futures.ThreadPoolExecutor:
    """Get or create a persistent ThreadPoolExecutor for scanning.
    
    Using ThreadPoolExecutor instead of ProcessPoolExecutor because:
    1. No pickle/serialization needed - threads share memory
    2. Avoids doubling memory usage (critical on low-RAM systems like 1GB)
    3. Still allows concurrent batch processing
    
    Trade-off: GIL limits true parallelism, but signal detection is mostly
    pandas/numpy operations which release the GIL anyway.
    """
    global _scan_executor
    if _scan_executor is None:
        logger.info("🔧 Creating persistent ThreadPoolExecutor for scanning...")
        _scan_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="scanner")
        # Register cleanup on process exit
        atexit.register(_shutdown_scan_executor)
    return _scan_executor

def _shutdown_scan_executor():
    """Shutdown the scan executor on process exit."""
    global _scan_executor
    if _scan_executor is not None:
        logger.info("🔧 Shutting down scan executor...")
        _scan_executor.shutdown(wait=False, cancel_futures=True)
        _scan_executor = None

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
    
    async def scan_all_stocks(self, force: bool = False, progress_callback=None, enabled_signals: List[str] = None, limit: int = None) -> Dict[str, List[Dict]]:
        """Scan all stocks for signals.
        
        Args:
            force: Force rescan even if cache is valid
            progress_callback: Async callback for progress updates  
            enabled_signals: List of signal IDs to scan (None = all signals)
            limit: (Deprecated) argument for backward compatibility, ignored in new logic
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
        """Internal scan implementation with batch scanning to reduce memory usage."""
        from app.services.scanner import SignalRegistry
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
            
            # 2. Load stock universe and decide streaming strategy
            data_signature = (max_date, max_date_count, total_vol, bucketed_limit) if max_date else None
            codes, stock_names = await self._get_scan_codes(today)
            if not codes:
                logger.warn("⚠️ No stock codes available for scanning")
                return {}

            total_stocks = len(codes)
            use_streaming = total_stocks >= STREAMING_SCAN_THRESHOLD

            sig_count = len(enabled_signals) if enabled_signals else SignalRegistry.count()
            logger.info(f"📊 Running scanner on {total_stocks} stocks with {sig_count} signal(s)")

            # Get the running event loop
            loop = asyncio.get_running_loop()
            executor = _get_scan_executor()

            if use_streaming:
                logger.info("🧠 Streaming scan enabled to reduce memory usage")
                if self._cached_stocks_data:
                    self._cached_stocks_data = None
                    self._cached_data_signature = None

                final_results = defaultdict(list)
                failed_batches = 0
                loaded_count = 0
                scanned_count = 0
                temp_5d = []
                temp_10d = []
                temp_20d = []

                if progress_callback:
                    await progress_callback(0, total_stocks, phase="loading")

                for i in range(0, total_stocks, STREAMING_BATCH_SIZE):
                    batch_codes = codes[i : i + STREAMING_BATCH_SIZE]
                    batch_names = {code: stock_names.get(code, code) for code in batch_codes}

                    batch_data = await self._get_local_history_batch(
                        batch_codes,
                        progress_callback=None,
                        limit=bucketed_limit
                    )

                    loaded_count += len(batch_codes)
                    if progress_callback:
                        await progress_callback(loaded_count, total_stocks, phase="loading")

                    for code, hist in batch_data.items():
                        name = batch_names.get(code, code)
                        self._append_top_gainers(hist, code, name, temp_5d, temp_10d, temp_20d)

                    if batch_data:
                        task = functools.partial(
                            run_scan_sync_wrapper,
                            batch_data,
                            batch_names,
                            enabled_signals
                        )

                        try:
                            batch_results = await asyncio.wait_for(
                                loop.run_in_executor(executor, task),
                                timeout=300.0
                            )
                            for sig, items in batch_results.items():
                                final_results[sig].extend(items)
                        except asyncio.TimeoutError:
                            logger.warn(f"⚠️ Batch {i//STREAMING_BATCH_SIZE + 1} timed out after 5 min, skipping...")
                            failed_batches += 1
                        except Exception as e:
                            logger.error(f"❌ Batch {i//STREAMING_BATCH_SIZE + 1} error: {e}")
                            failed_batches += 1

                    scanned_count += len(batch_codes)
                    if progress_callback:
                        await progress_callback(scanned_count, total_stocks, phase="scanning")

                    await asyncio.sleep(0)

                if failed_batches > 0:
                    logger.warn(f"⚠️ {failed_batches} batches failed during scan")

                logger.info("✅ Signal scan complete, calculating top gainers...")
                final_results.update(self._build_top_gainers(temp_5d, temp_10d, temp_20d))
            else:
                stocks_data = None

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
                        stocks_data = await self._get_local_history_batch(codes, progress_callback, limit=bucketed_limit)
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

                total_stocks = len(stocks_data)
                final_results = defaultdict(list)
                stock_codes = list(stocks_data.keys())
                batch_size = 300
                processed_count = 0
                failed_batches = 0

                if progress_callback:
                    await progress_callback(0, total_stocks, phase="scanning")

                for i in range(0, total_stocks, batch_size):
                    batch_codes = stock_codes[i : i + batch_size]
                    batch_data = {code: stocks_data[code] for code in batch_codes}
                    batch_names = {code: stock_names.get(code, code) for code in batch_codes}

                    task = functools.partial(
                        run_scan_sync_wrapper,
                        batch_data,
                        batch_names,
                        enabled_signals
                    )

                    try:
                        batch_results = await asyncio.wait_for(
                            loop.run_in_executor(executor, task),
                            timeout=300.0
                        )
                        for sig, items in batch_results.items():
                            final_results[sig].extend(items)
                    except asyncio.TimeoutError:
                        logger.warn(f"⚠️ Batch {i//batch_size + 1} timed out after 5 min, skipping...")
                        failed_batches += 1
                    except Exception as e:
                        logger.error(f"❌ Batch {i//batch_size + 1} error: {e}")
                        failed_batches += 1

                    processed_count += len(batch_codes)
                    if progress_callback:
                        await progress_callback(processed_count, total_stocks, phase="scanning")

                    await asyncio.sleep(0)

                if failed_batches > 0:
                    logger.warn(f"⚠️ {failed_batches} batches failed during scan")

                logger.info("✅ Signal scan complete, calculating top gainers...")
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




    async def _get_scan_codes(self, today) -> tuple:
        """Fetch stock codes and names for scanning."""
        rows = await db.pool.fetch("""
            SELECT DISTINCT code
            FROM stock_history 
            WHERE date >= $1::date - INTERVAL '7 days'
              AND code ~ '^[036]'
        """, today)

        if not rows:
            return [], {}

        codes = [r['code'] for r in rows]

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

        return codes, stock_names

    async def _load_stocks_data_for_scan(self, today, progress_callback=None, limit: int = 150) -> tuple:
        """Load stock data for scanning.
        
        Returns:
            (stocks_data, stock_names) tuple
        """
        codes, stock_names = await self._get_scan_codes(today)
        if not codes:
            return {}, {}

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

    def _append_top_gainers(self, hist, code: str, name: str, temp_5d: list, temp_10d: list, temp_20d: list) -> None:
        """Append gainers info for a single stock into temp lists."""
        try:
            closes = hist['收盘'].values

            if len(closes) >= 6:
                gain_5d = (closes[-1] - closes[-6]) / closes[-6] * 100
                has_lu = any(
                    (closes[i] - closes[i-1]) / closes[i-1] > 0.095
                    for i in range(-5, 0) if i > -len(closes)
                )
                temp_5d.append({"code": code, "name": name, "gain": gain_5d, "has_lu": has_lu})

            if len(closes) >= 11:
                gain_10d = (closes[-1] - closes[-11]) / closes[-11] * 100
                has_lu = any(
                    (closes[i] - closes[i-1]) / closes[i-1] > 0.095
                    for i in range(-10, 0) if i > -len(closes)
                )
                temp_10d.append({"code": code, "name": name, "gain": gain_10d, "has_lu": has_lu})

            if len(closes) >= 21:
                gain_20d = (closes[-1] - closes[-21]) / closes[-21] * 100
                has_lu = any(
                    (closes[i] - closes[i-1]) / closes[i-1] > 0.095
                    for i in range(-20, 0) if i > -len(closes)
                )
                temp_20d.append({"code": code, "name": name, "gain": gain_20d, "has_lu": has_lu})
        except Exception:
            return

    def _build_top_gainers(self, temp_5d: list, temp_10d: list, temp_20d: list) -> dict:
        """Build top gainers result dict from temp lists."""
        signals = {
            "top_gainers_weekly": [],
            "top_gainers_half_month": [],
            "top_gainers_monthly": [],
            "top_gainers_weekly_no_lu": [],
            "top_gainers_half_month_no_lu": [],
            "top_gainers_monthly_no_lu": [],
        }

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

    async def _calculate_top_gainers(self, stocks_data: dict, stock_names: dict) -> dict:
        """Calculate top gainers for various time periods.
        
        Returns dict with top_gainers_* keys.
        """
        temp_5d = []
        temp_10d = []
        temp_20d = []

        for code, hist in stocks_data.items():
            name = stock_names.get(code, code)
            self._append_top_gainers(hist, code, name, temp_5d, temp_10d, temp_20d)

        return self._build_top_gainers(temp_5d, temp_10d, temp_20d)


# Singleton
stock_scanner = StockScanner()

def run_scan_sync_wrapper(stocks_data, stock_names, enabled_signals):
    """Sync wrapper to run scanner in a thread.
    
    Creates a new event loop for the thread since run_scan is async.
    With ThreadPoolExecutor, data is shared (not pickled), saving memory.
    """
    import asyncio
    from app.services.scanner import run_scan
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        results = loop.run_until_complete(
            run_scan(stocks_data, stock_names, progress_callback=None, enabled_signals=enabled_signals)
        )
        loop.close()
        return results
    except Exception as e:
        logger.error(f"Thread scan error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {}
