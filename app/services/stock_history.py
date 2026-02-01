"""
A-Share Stock History Service (A股历史数据服务)

Background service that builds and maintains a local PostgreSQL copy of
5-year A-share stock history data for signal detection and trend analysis.

Features:
- Fetches all A-share stock codes (~5000 stocks)
- Backfills 10 years of OHLCV history on first run
- Daily updates after 3PM (15:15) to capture latest trading data
- Rate limiting to avoid API throttling
"""

import asyncio
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Callable
import time
import random

from app.core.logger import Logger
from app.core.database import db
from app.core.config import settings
from app.core.timezone import CHINA_TZ, china_now, china_today

logger = Logger("StockHistoryService")


class StockHistoryService:
    """Service for building and maintaining A-share history database."""
    
    def __init__(self):
        self.is_running = False
        self._scheduler_task = None
        self._scheduler_task = None
    # Executor no longer needed as we use async DataProvider logic

    def _get_libs(self):
        """Lazy load dependencies."""
        try:
            import akshare as ak
            import pandas as pd
            return ak, pd
        except ImportError:
            logger.error("Missing libs. Run: pip install akshare pandas")
            return None, None
    

    
    async def start(self):
        """Start the stock history service scheduler."""
        if self.is_running:
            return
        
        self.is_running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("✅ Stock History Service started")
    
    async def stop(self):
        """Stop the service."""
        self.is_running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        logger.info("Stock History Service stopped")
    
    async def initialize(self):
        """Initialize service - backfill 5 years of history if needed.
        
        Smart resume: If backfill was interrupted, resumes from where it left off
        by checking which stocks are missing from the database.
        """
        if not db.pool:
            logger.warn("Database not connected, skipping initialization")
            return
        
        # Get current stock count in DB
        result = await db.pool.fetchrow("""
            SELECT COUNT(*) as total_records,
                   COUNT(DISTINCT code) as stock_count,
                   MIN(date) as min_date, 
                   MAX(date) as max_date
            FROM stock_history
        """)
        
        db_stock_count = result['stock_count'] or 0
        
        if db_stock_count > 0:
            logger.info(
                f"Found {result['total_records']:,} records: {db_stock_count} stocks, "
                f"from {result['min_date']} to {result['max_date']}"
            )
            
        # Optimization: Check if stock_info is already updated today to avoid slow AkShare call
        # NOTE: This only skips the external API fetch, NOT the history staleness checks!
        use_cached_stock_list = False
        try:
            info_stats = await db.pool.fetchrow("""
                SELECT COUNT(*) as count, MAX(updated_at) as last_update 
                FROM stock_info
            """)
            if info_stats and info_stats['count'] > 4000:
                last_update = info_stats['last_update']
                today = china_today()
                if last_update and last_update.date() == today:
                    logger.info(f"Stock list cache is fresh (Updated: {last_update}), will use cached list")
                    use_cached_stock_list = True
        except Exception as e:
            logger.warn(f"Failed to check stock_info stats: {e}")
        
        # Get all current A-share stock codes (use cache if fresh, else fetch from API)
        all_codes = await self.get_all_stock_codes(force_refresh=not use_cached_stock_list)
        if not all_codes:
            logger.warn("Could not fetch stock list, skipping backfill check")
            return
        
        # Check coverage - if we have less than 90% of stocks, resume backfill
        coverage = db_stock_count / len(all_codes) if all_codes else 1.0
        
        # Find missing stocks
        existing_codes = set()
        if db_stock_count > 0:
            rows = await db.pool.fetch("SELECT DISTINCT code FROM stock_history")
            existing_codes = {row['code'] for row in rows}
        
        missing_codes = [c for c in all_codes if c not in existing_codes]
        
        # Check data freshness for existing stocks
        stale_stocks = []
        if coverage >= 0.9 and db_stock_count > 0:
            # Get latest date for each stock
            today = china_today()
            rows = await db.pool.fetch("""
                SELECT code, MAX(date) as latest_date
                FROM stock_history
                GROUP BY code
            """)
            
            for row in rows:
                days_old = (today - row['latest_date']).days
                # If data is more than 7 days old (accounting for weekends), needs update
                if days_old > 7:
                    stale_stocks.append(row['code'])
            
            if stale_stocks:
                logger.info(f"Found {len(stale_stocks)} stocks with stale data (>7 days old)")
                # Run in background task
                asyncio.create_task(self._update_stale_background_task(stale_stocks))
        
        # Handle missing stocks
        if coverage < 0.9:
            if missing_codes:
                logger.info(
                    f"Stock coverage: {coverage:.1%} ({db_stock_count}/{len(all_codes)}), "
                    f"resuming backfill for {len(missing_codes)} missing stocks..."
                )
                # Run in background task
                asyncio.create_task(self._backfill_background_task(missing_codes))
            else:
                logger.info("All stocks have history data")
        else:
            logger.info(f"Stock coverage: {coverage:.1%} ({db_stock_count}/{len(all_codes)}) - sufficient")
        
        # Cleanup abnormal data (future dates or duplicate syncs)
        await self.cleanup_abnormal_data()
        
        # [NEW] Check history depth coverage (Deep Backfill)
        # Identify stocks that exist but have history starting too recently (e.g., > 4 years ago)
        # We want at least 5 years of data.
        await self._check_and_backfill_shallow_stocks(db_stock_count)

    async def _check_and_backfill_shallow_stocks(self, total_stocks: int):
        """Check if existing stocks have enough history depth."""
        if total_stocks < 100:
            return

        try:
            target_years = 10
            cutoff_date = china_today() - timedelta(days=target_years * 365 - 100) # Allow some buffer
            
            # Find stocks with start_date > cutoff_date (i.e., too new)
            # This query finds stocks where the earliest record is MORE RECENT than 4.x years ago
            logger.info(f"Checking for stocks with history starting after {cutoff_date}...")
            
            rows = await db.pool.fetch("""
                SELECT code, MIN(date) as min_date
                FROM stock_history 
                GROUP BY code 
                HAVING MIN(date) > $1::date
            """, cutoff_date)
            
            shallow_stocks = [r['code'] for r in rows]
            
            if shallow_stocks:
                # If too many stocks need backfill (e.g. initial run with shallow db), it might take a while
                logger.info(
                    f"Found {len(shallow_stocks)} stocks with insufficient history (start > {cutoff_date}). "
                    f"Starting deep backfill in background..."
                )
                
                # Run in background task
                asyncio.create_task(self._deep_backfill_background_task(shallow_stocks, cutoff_date))
            else:
                logger.info("✅ All stocks have sufficient history depth")
                
        except Exception as e:
            logger.warn(f"Failed to check history depth: {e}")

    
    async def _backfill_all_stocks(self):
        """Backfill 10 years of history for all A-share stocks."""
        codes = await self.get_all_stock_codes()
        if not codes:
            logger.error("Failed to get stock codes")
            return
        await self._backfill_stocks(codes)
    
    async def _update_stale_stocks(self, codes: List[str]):
        """Update stocks that have stale data by fetching missing recent days."""
        ak, pd = self._get_libs()
        if not ak or not pd:
            return
        
        today = china_today()
        
        logger.info(f"Updating {len(codes)} stocks with stale data...")
        
        success_count = 0
        error_count = 0
        
        for i, code in enumerate(codes):
            try:
                # Get the latest date we have for this stock
                latest = await db.pool.fetchval(
                    "SELECT MAX(date) FROM stock_history WHERE code = $1", code
                )
                
                if not latest:
                    continue
                
                # Fetch from day after latest to today
                start_date = latest + timedelta(days=1)
                start_str = start_date.strftime("%Y%m%d")
                end_str = today.strftime("%Y%m%d")
                
                records = await self._fetch_and_save_history(code, start_str, end_str)
                if records > 0:
                    success_count += 1
                
                # Progress logging
                if (i + 1) % 100 == 0:
                    logger.info(
                        f"Update progress: {i + 1}/{len(codes)} stocks "
                        f"({success_count} success, {error_count} errors)"
                    )
                
                # Rate limiting - 0.5s between requests, longer pause every 50 stocks
                await asyncio.sleep(0.5)
                if (i + 1) % 50 == 0:
                    await asyncio.sleep(2)  # Yield more time to other tasks
                
            except Exception as e:
                error_count += 1
                if error_count <= 10:
                    logger.warn(f"Failed to update {code}: {e}")
        
        logger.info(
            f"✅ Update complete: {success_count}/{len(codes)} stocks updated, "
            f"{error_count} errors"
        )
    
    async def _backfill_stocks(self, codes: List[str]):
        """Backfill 10 years of history for specified stock codes."""
        ak, pd = self._get_libs()
        if not ak or not pd:
            return
        
        # Calculate date range (10 years)
        end_date = china_today()
        start_date = end_date - timedelta(days=10 * 365)
        
        start_str = start_date.strftime("%Y%m%d")
        end_str = end_date.strftime("%Y%m%d")
        
        logger.info(f"Backfilling {len(codes)} stocks from {start_date} to {end_date}")
        
        success_count = 0
        error_count = 0
        
        for i, code in enumerate(codes):
            try:
                records = await self._fetch_and_save_history(code, start_str, end_str)
                if records > 0:
                    success_count += 1
                
                # Progress logging
                if (i + 1) % 100 == 0:
                    logger.info(
                        f"Backfill progress: {i + 1}/{len(codes)} stocks "
                        f"({success_count} success, {error_count} errors)"
                    )
                
                # Rate limiting - 0.5s between requests, longer pause every 50 stocks
                await asyncio.sleep(0.5)
                if (i + 1) % 50 == 0:
                    await asyncio.sleep(2)  # Yield more time to other tasks
                
            except Exception as e:
                error_count += 1
                if error_count <= 10:  # Only log first 10 errors
                    logger.warn(f"Failed to backfill {code}: {e}")
        
        logger.info(
            f"✅ Backfill complete: {success_count}/{len(codes)} stocks, "
            f"{error_count} errors"
        )
    
    async def _update_stale_background_task(self, codes: List[str]):
        """Async background task to update stale stocks."""
        today = china_today()
        logger.info(f"[BG Task] Updating {len(codes)} stocks with stale data...")
        
        success_count = 0
        error_count = 0
        
        for i, code in enumerate(codes):
            try:
                latest = await db.pool.fetchval(
                    "SELECT MAX(date) FROM stock_history WHERE code = $1", code
                )
                
                if not latest:
                    continue
                
                start_date = latest + timedelta(days=1)
                start_str = start_date.strftime("%Y%m%d")
                end_str = today.strftime("%Y%m%d")
                
                records = await self._fetch_and_save_history(code, start_str, end_str)
                if records > 0:
                    success_count += 1
                
                if (i + 1) % 100 == 0:
                    logger.info(f"[BG Task] Update: {i+1}/{len(codes)} ({success_count} success)")
                
                # Yield to event loop
                await asyncio.sleep(0.2)
                
            except Exception as e:
                error_count += 1
                if error_count <= 10:
                    logger.warn(f"[BG Task] Failed to update {code}: {e}")
        
        logger.info(f"✅ [BG Task] Update complete: {success_count}/{len(codes)}, {error_count} errors")

    async def _backfill_background_task(self, codes: List[str]):
        """Async background task to backfill stocks."""
        end_date = china_today()
        start_date = end_date - timedelta(days=10 * 365)
        start_str = start_date.strftime("%Y%m%d")
        end_str = end_date.strftime("%Y%m%d")
        
        logger.info(f"[BG Task] Backfilling {len(codes)} stocks from {start_date} to {end_date}")
        
        success_count = 0
        error_count = 0
        
        for i, code in enumerate(codes):
            try:
                records = await self._fetch_and_save_history(code, start_str, end_str)
                if records > 0:
                    success_count += 1
                
                if (i + 1) % 100 == 0:
                    logger.info(f"[BG Task] Backfill: {i+1}/{len(codes)} ({success_count} success)")
                
                await asyncio.sleep(0.5) # Gentler pacing for heavy backfill
                
            except Exception as e:
                error_count += 1
                if error_count <= 10:
                    logger.warn(f"[BG Task] Failed to backfill {code}: {e}")
                    
        logger.info(f"✅ [BG Task] Backfill complete: {success_count}/{len(codes)}, {error_count} errors")

    async def _deep_backfill_background_task(self, codes: List[str], cutoff_date):
        """Async background task for deep backfill."""
        target_start = china_today() - timedelta(days=10 * 365 + 30)
        start_str = target_start.strftime("%Y%m%d")
        
        logger.info(f"[BG Task] Deep backfilling {len(codes)} stocks from {target_start}...")
        
        success_count = 0
        error_count = 0
        
        for i, code in enumerate(codes):
            try:
                # Re-check min date
                current_min = await db.pool.fetchval("SELECT MIN(date) FROM stock_history WHERE code = $1", code)
                
                if not current_min:
                    continue
                    
                end_date = current_min - timedelta(days=1)
                if end_date < target_start:
                    continue
                    
                end_str = end_date.strftime("%Y%m%d")
                
                records = await self._fetch_and_save_history(code, start_str, end_str)
                if records > 0:
                    success_count += 1
                
                if (i + 1) % 50 == 0:
                    logger.info(f"[BG Task] Deep Fill: {i+1}/{len(codes)} ({success_count} success)")
                    
                await asyncio.sleep(0.5)
                
            except Exception as e:
                error_count += 1
                if error_count <= 10:
                    logger.warn(f"[BG Task] Failed deep backfill for {code}: {e}")
                    
        logger.info(f"✅ [BG Task] Deep backfill complete: {success_count}/{len(codes)} stocks enriched")
    

    
    async def get_all_stock_codes(self, force_refresh: bool = False) -> List[str]:
        """Fetch all A-share stock codes using DataProvider."""
        if not db.pool:
            return []
            
        from app.services.data_provider.service import data_provider

        # === Step 1: Try local cache first (unless force_refresh) ===
        if not force_refresh and db.pool:
            try:
                info_stats = await db.pool.fetchrow("""
                    SELECT COUNT(*) as count, MAX(updated_at) as last_update 
                    FROM stock_info
                """)
                
                if info_stats and info_stats['count'] and info_stats['count'] > 4000:
                    last_update = info_stats['last_update']
                    today = china_today()
                    
                    # Cache is valid if updated today or yesterday (for weekend/holiday)
                    if last_update and (today - last_update.date()).days <= 1:
                        rows = await db.pool.fetch("SELECT code FROM stock_info")
                        codes = [r['code'] for r in rows]
                        logger.info(f"✅ Using cached stock list: {len(codes)} stocks (last update: {last_update})")
                        return codes
                    else:
                        logger.info(f"Stock list cache stale (last: {last_update}), will refresh from API")
            except Exception as e:
                logger.warn(f"Failed to check stock_info cache: {e}")

        # === Step 2: Fetch from DataProvider ===
        try:
            logger.info("Fetching stock list from DataProvider...")
            stock_list = await data_provider.get_stock_list()
            
            if not stock_list:
                logger.error("DataProvider returned empty stock list")
                raise Exception("Empty result from DataProvider")
            
            codes = [item['code'] for item in stock_list]
            
            # Update stock_info cache
            if db.pool:
                try:
                    records = []
                    for item in stock_list:
                        codes_val = item['code']
                        name_val = item['name']
                        if codes_val and name_val:
                            records.append((str(codes_val), str(name_val)))
                    if records:
                        await db.pool.executemany("""
                            INSERT INTO stock_info (code, name, updated_at)
                            VALUES ($1, $2, NOW())
                            ON CONFLICT (code) DO UPDATE SET
                                name = EXCLUDED.name,
                                updated_at = NOW()
                        """, records)
                        logger.info(f"📦 Updated stock_info cache with {len(records)} stocks")
                except Exception as e:
                    logger.warn(f"Failed to update stock_info cache: {e}")
            
            return codes
            
        except Exception as e:
            logger.error(f"Failed to get stock codes: {e}")
            
            # === Step 3: Fallback to local database ===
            if db.pool:
                try:
                    logger.info("⚠️ Falling back to local database...")
                    rows = await db.pool.fetch("SELECT code FROM stock_info")
                    if not rows:
                        rows = await db.pool.fetch("SELECT DISTINCT code FROM stock_history")
                    
                    if rows:
                        codes = [r['code'] for r in rows]
                        logger.info(f"✅ Loaded {len(codes)} stocks from local DB fallback")
                        return codes
                except Exception as db_e:
                    logger.error(f"Failed to load from local DB: {db_e}")
            
            return []
    
    async def _fetch_and_save_history(
        self, 
        code: str, 
        start_date: str, 
        end_date: str
    ) -> int:
        """Fetch history for a single stock and save to database using DataProvider."""
        if not db.pool:
            return 0
        
        try:
            from app.services.data_provider.service import data_provider
            from app.core.timezone import china_today, china_now
            
            # DataProvider expects YYYYMMDD
            # start_date and end_date passed in are already YYYYMMDD string format from callers
            
            data_list = await data_provider.get_daily_bars(code, start_date, end_date)
            
            if not data_list:
                return 0
            
            today = china_today()
            now = china_now()
            is_pre_market = now.time() < datetime.strptime("09:30", "%H:%M").time()
            
            records = []
            for item in data_list:
                date_val = item['date']
                
                # Validation: Skip future dates
                if date_val > today:
                    continue
                
                # Validation: Skip today's data if pre-market (09:30)
                if date_val == today and is_pre_market:
                    continue
                
                record = (
                    code,
                    date_val,
                    item['open'],
                    item['high'],
                    item['low'],
                    item['close'],
                    item['volume'],
                    item['turnover'],  # turnover (amount)
                    item.get('amplitude', 0.0),
                    item.get('change_pct', 0.0),
                    item.get('change_amt', 0.0),
                    item.get('turnover_rate', 0.0),
                )
                records.append(record)
            
            # Batch insert with upsert
            if records:
                await db.pool.executemany("""
                    INSERT INTO stock_history 
                    (code, date, open, high, low, close, volume, turnover, 
                     amplitude, change_pct, change_amt, turnover_rate)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                    ON CONFLICT (code, date) DO UPDATE SET
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        volume = EXCLUDED.volume,
                        turnover = EXCLUDED.turnover,
                        amplitude = EXCLUDED.amplitude,
                        change_pct = EXCLUDED.change_pct,
                        change_amt = EXCLUDED.change_amt,
                        turnover_rate = EXCLUDED.turnover_rate
                """, records)
            
            return len(records)
            
        except Exception as e:
            logger.warn(f"History fetch failed for {code}: {e}")
            return 0
    
    async def _update_all_stocks_concurrent(self, progress_callback: Optional[Callable] = None):
        """Fallback: Concurrent update - fetch today's data for all stocks individually.
        
        Args:
            progress_callback: Optional async callback(stage, current, total, message)
        """
        ak, pd = self._get_libs()
        if not ak or not pd or not db.pool:
            return
        
        today = china_today()
        date_str = today.strftime("%Y%m%d")
        
        # Get all stock codes
        codes = await self.get_all_stock_codes()
        if not codes:
            return
        
        # Concurrency control
        sem = asyncio.Semaphore(5)
        
        success_count = 0
        error_count = 0
        processed_count = 0
        last_progress_time = time.time()
        
        
        # Abort flag
        aborted = False
        
        async def update_one(code):
            nonlocal success_count, error_count, processed_count, last_progress_time, aborted
            
            if aborted:
                return

            async with sem:
                if aborted: return
                
                # Random sleep to prevent IP blocking
                await asyncio.sleep(random.uniform(0.5, 1.5))
                try:
                    records = await self._fetch_and_save_history(code, date_str, date_str)
                    if records > 0:
                        success_count += 1
                except Exception as e:
                    error_count += 1
                    if error_count <= 5:
                        logger.warn(f"Failed to update {code}: {e}")
                finally:
                    processed_count += 1
                    
                    if processed_count % 200 == 0:
                        logger.info(f"Daily update progress: {processed_count}/{len(codes)} stocks")
                    
                    # Abort if too many errors (likely blocked)
                    if not aborted and error_count > 50:
                        logger.error(f"❌ Too many errors ({error_count}), aborting daily update to prevent IP ban persistence.")
                        aborted = True
                    
                    # Progress callback (every 2 seconds or 100 items)
                    if progress_callback and (time.time() - last_progress_time >= 2 or processed_count % 100 == 0):
                        last_progress_time = time.time()
                        pct = int(processed_count / len(codes) * 100)
                        try:
                            await progress_callback("数据同步", processed_count, len(codes), f"⏳ 数据同步中 (Fallback): {processed_count}/{len(codes)} ({pct}%)")
                        except:
                            pass

        # Run concurrently
        tasks = [update_one(code) for code in codes]
        await asyncio.gather(*tasks)
        
        # Invalidate cache after update
        await self.invalidate_stock_cache()
        
        # Final progress notification
        if progress_callback:
            await progress_callback("数据同步", len(codes), len(codes), f"✅ 同步完成 (Fallback): {success_count}/{len(codes)} 只股票")
        
        logger.info(
            f"✅ Daily update complete (Fallback): {success_count}/{len(codes)} stocks updated"
        )

    async def update_all_stocks(
        self,
        progress_callback: Optional[Callable] = None,
        ignore_time_checks: bool = False,
    ):
        """Daily update - fetch today's data for all stocks.
        
        Tries batch update first, falls back to concurrent individual update.
        """
        today = china_today()
        # Skip weekends unless manual override
        if not ignore_time_checks and today.weekday() >= 5:
            logger.info("Weekend, skipping daily update")
            return

        # Try batch update first
        success = await self.update_all_stocks_batch(
            progress_callback,
            ignore_time_checks=ignore_time_checks,
        )
        
        if success:
            return
            
        # Fallback to concurrent update
        logger.warn("Batch update failed, falling back to concurrent individual update...")
        if progress_callback:
            await progress_callback("数据同步", 0, 100, "⚠️ 批量更新失败，切换到备用模式...")
            
        await self._update_all_stocks_concurrent(progress_callback)
    
    async def update_all_stocks_batch(
        self,
        progress_callback: Optional[Callable] = None,
        ignore_time_checks: bool = False,
    ) -> bool:
        """Batch update using ak.stock_zh_a_spot_em() - much faster.
        
        Returns:
            bool: True if successful, False if failed (triggering fallback)
        """
        ak, pd = self._get_libs()
        if not ak or not pd or not db.pool:
            return False
        
        today = china_today()
        # Determine the correct date for the data
        # If before 09:30, the data is from the previous trading day
        if ignore_time_checks:
            target_date = today
        else:
            now = china_now()
            if now.time() < datetime.strptime("09:30", "%H:%M").time():
                target_date = today - timedelta(days=1)
                logger.info(f"Time is {now.strftime('%H:%M')} (<09:30), assuming data is from previous day: {target_date}")
            else:
                target_date = today
            
        # Get actual latest trading date
        trade_date = await self.get_latest_trading_date(target_date)
        if not trade_date:
            logger.warn("Could not determine trading date, using target date")
            trade_date = target_date
            
        date_str = trade_date.strftime("%Y-%m-%d")
        logger.info(f"Starting batch daily update for {date_str} (Target: {target_date})")
        
        # Check if already synced
        try:
            count = await db.pool.fetchval("SELECT COUNT(*) FROM stock_history WHERE date = $1", trade_date)
            if count and count > 4000:
                logger.info(f"✅ Data for {date_str} already exists ({count} records). Skipping sync.")
                if progress_callback:
                    await progress_callback("数据同步", 100, 100, f"✅ {date_str} 数据已存在，无需同步")
                return True
        except Exception as e:
            logger.warn(f"Failed to check existing data: {e}")
        
        if progress_callback:
            await progress_callback("数据同步", 0, 100, f"⏳ 正在批量获取实时数据 ({date_str})...")
            
        try:
            # Fetch all spot data using data provider (respects rate limits/circuit breaker)
            from app.services.data_provider.service import data_provider
            
            logger.info("Calling data_provider.get_all_spot_data()...")
            df = await data_provider.get_all_spot_data()
            
            if df is None or df.empty:
                logger.error("Batch update failed: API returned empty data or circuit open")
                return False
                
            # Filter valid A-share stocks
            # A-share codes: 00xxxx (SZ), 30xxxx (创业板), 60xxxx (SH), 68xxxx (科创板)
            df_filtered = df[
                ~df['名称'].str.contains('ST|退', na=False) &
                (df['代码'].str.match(r'^[036]'))
            ].copy()
            
            total_stocks = len(df_filtered)
            logger.info(f"Got {total_stocks} valid stocks from API")

            if progress_callback:
                await progress_callback("数据同步", 10, 100, f"⏳ 获取到 {total_stocks} 只股票，准备入库...")

            # Reject partial market snapshots to avoid poisoning local DB.
            try:
                expected_count = 0
                if db.pool:
                    expected_count = await db.pool.fetchval("SELECT COUNT(*) FROM stock_info") or 0
                min_required = int(expected_count * 0.9) if expected_count else 0
                if total_stocks < min_required:
                    logger.warn(
                        f"Batch snapshot too small ({total_stocks} < {min_required}); "
                        "treating as failure to trigger fallback."
                    )
                    return False
            except Exception as e:
                logger.warn(f"Failed to validate snapshot size: {e}")

            # Prepare records for bulk insert
            records = []
            for _, row in df_filtered.iterrows():
                try:
                    # Map columns
                    # '最新价'->close, '今开'->open, '最高'->high, '最低'->low
                    # '成交量'->volume, '成交额'->turnover
                    # '涨跌幅'->change_pct, '换手率'->turnover_rate, '振幅'->amplitude
                    
                    code = str(row['代码'])
                    close = float(row['最新价'])
                    open_price = float(row['今开'])
                    high = float(row['最高'])
                    low = float(row['最低'])
                    volume = float(row['成交量']) if pd.notna(row['成交量']) else 0.0
                    turnover = float(row['成交额']) if pd.notna(row['成交额']) else 0.0
                    change_pct = float(row['涨跌幅'])
                    turnover_rate = float(row['换手率']) if pd.notna(row['换手率']) else 0.0
                    amplitude = float(row['振幅']) if pd.notna(row['振幅']) else 0.0
                    
                    # Basic validation
                    if close <= 0 or open_price <= 0:
                        continue
                        
                    records.append((
                        code, trade_date, open_price, high, low, close, 
                        volume, turnover, change_pct, turnover_rate, amplitude
                    ))
                except Exception:
                    continue
            
            if not records:
                logger.warn("No valid records to insert")
                return False
                
            # Bulk insert
            logger.info(f"Inserting {len(records)} records...")
            if progress_callback:
                await progress_callback("数据同步", 50, 100, f"⏳ 正在写入 {len(records)} 条数据...")
                
            async with db.pool.acquire() as conn:
                await conn.executemany("""
                    INSERT INTO stock_history (
                        code, date, open, high, low, close, 
                        volume, turnover, change_pct, turnover_rate, amplitude
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    ON CONFLICT (code, date) DO UPDATE SET
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        volume = EXCLUDED.volume,
                        turnover = EXCLUDED.turnover,
                        change_pct = EXCLUDED.change_pct,
                        turnover_rate = EXCLUDED.turnover_rate,
                        amplitude = EXCLUDED.amplitude
                """, records)
                
            logger.info(f"✅ Batch update complete: {len(records)} records inserted")
            
            # Invalidate cache
            await self.invalidate_stock_cache()
            
            if progress_callback:
                await progress_callback("数据同步", 100, 100, f"✅ 批量同步完成: {len(records)} 只股票")
            
            return True
            
        except Exception as e:
            logger.error(f"Batch update failed: {e}")
            if progress_callback:
                await progress_callback("数据同步", 0, 100, f"❌ 同步失败: {e}")
            return False
    
    async def cleanup_abnormal_data(self):
        """Cleanup abnormal data from database.
        
        Removes:
        1. Future dates (date > today)
        2. Today's data if time < 09:30 (likely synced incorrectly at midnight)
        """
        if not db.pool:
            return
            
        try:
            today = china_today()
            now = china_now()
            
            # 1. Remove future dates
            res = await db.pool.execute("DELETE FROM stock_history WHERE date > $1", today)
            count = int(res.split()[-1]) if res else 0
            if count > 0:
                logger.info(f"🧹 Cleaned up {count} future data records")
                
            # 2. Remove today's data if before market open
            if now.time() < datetime.strptime("09:30", "%H:%M").time():
                res = await db.pool.execute("DELETE FROM stock_history WHERE date = $1", today)
                count = int(res.split()[-1]) if res else 0
                if count > 0:
                    logger.info(f"🧹 Cleaned up {count} premature today data records")
                    
        except Exception as e:
            logger.error(f"Failed to cleanup abnormal data: {e}")

    async def get_latest_trading_date(self, target_date: date) -> Optional[date]:
        """Get the latest trading date <= target_date using DataProvider."""
        try:
            from app.services.data_provider.service import data_provider
            
            # Fetch generic range around target date (e.g. last 30 days)
            start_date = (target_date - timedelta(days=30)).strftime("%Y%m%d")
            end_date = target_date.strftime("%Y%m%d")
            
            dates = await data_provider.get_trading_dates(start_date, end_date)
            
            if dates:
                # Latest date is the last one in the sorted list
                return dates[-1]
            return None
            
        except Exception as e:
            logger.error(f"Failed to get trading date: {e}")
            return None

    async def sync_with_integrity_check(
        self,
        progress_callback: Optional[Callable] = None,
        ignore_time_checks: bool = False,
    ):
        """Sync data with integrity check.
        
        This method:
        1. Updates all stocks with latest trading date data (batch preferred)
        2. Checks for stocks missing data in the last 7 trading days
        3. Fills in the gaps for those stocks
        
        Args:
            progress_callback: Optional async callback(stage, current, total, message)
        
        Called by /dbsync command and daily 15:15 scheduled task.
        """
        ak, pd = self._get_libs()
        if not ak or not pd or not db.pool:
            return
        
        today = china_today()

        # Skip weekends unless manual override
        if not ignore_time_checks and today.weekday() >= 5:
            logger.info("Weekend, skipping sync")
            return
        
        logger.info("🔍 Starting sync with data integrity check...")
        
        # Notify start
        if progress_callback:
            await progress_callback("开始同步", 0, 100, "⏳ 正在同步最新数据...")
        
        # Step 1: Regular daily update for latest trading day data
        await self.update_all_stocks(progress_callback, ignore_time_checks=ignore_time_checks)

        # Step 2: Find stocks with missing 7-day data and fix gaps
        try:
            stocks_to_fix = await self._check_recent_data_integrity(
                progress_callback,
                ignore_time_checks=ignore_time_checks,
            )
            
            if stocks_to_fix:
                logger.info(f"📋 Found {len(stocks_to_fix)} stocks with incomplete data, fixing...")
                if progress_callback:
                    await progress_callback("完整性修复", 0, len(stocks_to_fix), f"🛠️ 发现 {len(stocks_to_fix)} 只股票数据不完整，开始修复...")
                await self._fix_incomplete_stocks(stocks_to_fix, progress_callback)
            else:
                logger.info("✅ All stocks have complete recent data")
                if progress_callback:
                    await progress_callback("完整性检查", 100, 100, "✅ 所有股票数据完整")
                
        except Exception as e:
            logger.error(f"Error during integrity check: {e}")
        
        # Step 3: Final cleanup to ensure no future/premature data slipped in
        await self.cleanup_abnormal_data()
    
    async def _check_recent_data_integrity(
        self,
        progress_callback: Optional[Callable] = None,
        limit: Optional[int] = None,
        ignore_time_checks: bool = False,
    ) -> List[Dict]:
        """Check which stocks are missing data in the last 7 trading days.
        
        Returns list of dicts with 'code' and 'missing_from' date.
        """
        if not db.pool:
            return []
        
        today = china_today()
        # Determine expected latest trading date (not simply DB max)
        if ignore_time_checks:
            target_base = today
        else:
            now = china_now()
            if now.time() < datetime.strptime("09:30", "%H:%M").time():
                target_base = today - timedelta(days=1)
            else:
                target_base = today
        target_date = await self.get_latest_trading_date(target_base) or target_base
        seven_days_ago = target_date - timedelta(days=10)  # Look back 10 days to cover weekends
        
        # Get all stock codes we should have data for
        if progress_callback:
            await progress_callback("检查中", 0, 100, "📊 正在获取股票列表...")
        
        all_codes = await self.get_all_stock_codes()
        if not all_codes:
            return []
        
        if progress_callback:
            await progress_callback("检查中", 30, 100, f"🔍 获取到 {len(all_codes)} 只股票，正在检查数据完整性...")
        
        # Get the latest date for each stock in recent period
        rows = await db.pool.fetch("""
            SELECT code, MAX(date) as latest_date
            FROM stock_history
            WHERE date >= $1
            GROUP BY code
        """, seven_days_ago)
        
        code_latest = {row['code']: row['latest_date'] for row in rows}
        
        # Find stocks with missing data
        stocks_to_fix = []
        
        # Stocks that exist in DB but have outdated data
        for code in all_codes:
            if code in code_latest:
                latest = code_latest[code]
                # If latest data is behind the current DB max date, needs update
                days_old = (target_date - latest).days
                if days_old >= 1:  # Missing even 1 day
                    stocks_to_fix.append({
                        'code': code, 
                        'missing_from': latest + timedelta(days=1)
                    })
            else:
                # Stock exists in market but no recent data - needs full 7-day backfill
                stocks_to_fix.append({
                    'code': code,
                    'missing_from': seven_days_ago
                })
        
        if limit:
            return stocks_to_fix[:limit]
        return stocks_to_fix
    
    async def _fix_incomplete_stocks(self, stocks_to_fix: List[Dict], progress_callback: Optional[Callable] = None):
        """Fix stocks with missing recent data."""
        if not stocks_to_fix:
            return
        
        today = china_today()
        end_str = today.strftime("%Y%m%d")
        
        today = china_today()
        end_str = today.strftime("%Y%m%d")
        
        # Concurrency control
        sem = asyncio.Semaphore(5)
        
        success_count = 0
        error_count = 0
        processed_count = 0
        last_progress_time = time.time()
        
        async def fix_one(stock_info):
            nonlocal success_count, error_count, processed_count, last_progress_time
            code = stock_info['code']
            start_date = stock_info['missing_from']
            start_str = start_date.strftime("%Y%m%d")
            
            async with sem:
                # Random sleep to prevent IP blocking
                await asyncio.sleep(random.uniform(0.5, 1.5))
                try:
                    records = await self._fetch_and_save_history(code, start_str, end_str)
                    if records > 0:
                        success_count += 1
                        # Log first few successes for debugging
                        if success_count <= 3:
                            logger.debug(f"✅ Fixed {code}: {records} records ({start_str} to {end_str})")
                    else:
                        pass # Silent fail for empty data
                        
                except Exception as e:
                    error_count += 1
                    if error_count <= 5:
                        logger.warn(f"Failed to fix {code}: {e}")
                finally:
                    processed_count += 1
                    
                    # Progress logging every 50 stocks
                    if processed_count % 50 == 0:
                        logger.info(f"🔧 Integrity fix progress: {processed_count}/{len(stocks_to_fix)} ({success_count} fixed)")
                    
                    # Progress callback (every 2 seconds)
                    if progress_callback and (time.time() - last_progress_time >= 2 or processed_count % 50 == 0):
                        last_progress_time = time.time()
                        pct = int(processed_count / len(stocks_to_fix) * 100)
                        try:
                            await progress_callback("完整性修复", processed_count, len(stocks_to_fix), f"🔧 修复中: {processed_count}/{len(stocks_to_fix)} ({pct}%)")
                        except:
                            pass

        # Run concurrently
        tasks = [fix_one(info) for info in stocks_to_fix]
        await asyncio.gather(*tasks)
        
        if progress_callback:
            await progress_callback("完整性修复", len(stocks_to_fix), len(stocks_to_fix), f"✅ 修复完成: {success_count}/{len(stocks_to_fix)} 只股票")
        
        # Invalidate cache so freshly fixed data is visible immediately
        await self.invalidate_stock_cache()

        logger.info(f"✅ Integrity fix complete: {success_count}/{len(stocks_to_fix)} stocks fixed")
    
    async def _scheduler_loop(self):
        """Background scheduler for daily updates at 15:15 and nightly check at 03:00."""
        update_time = "15:15"
        nightly_time = "03:00"
        triggered_today = set()
        
        while self.is_running:
            try:
                now = china_now()
                time_str = now.strftime("%H:%M")
                date_str = now.strftime("%Y-%m-%d")
                
                # Reset triggered set at midnight
                if time_str == "00:00":
                    triggered_today.clear()
                
                # Run daily update at 15:15 on weekdays (with integrity check)
                update_key = f"{date_str}_update"
                if now.weekday() < 5 and time_str == update_time and update_key not in triggered_today:
                    triggered_today.add(update_key)
                    logger.info("Triggering daily stock history sync with integrity check")
                    asyncio.create_task(self.sync_with_integrity_check())
                
                # Run nightly integrity check at 03:00 (every day including weekends)
                nightly_key = f"{date_str}_nightly"
                if time_str == nightly_time and nightly_key not in triggered_today:
                    triggered_today.add(nightly_key)
                    logger.info("Triggering nightly data integrity check")
                    asyncio.create_task(self.sync_with_integrity_check())
                
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
            
            # Check every 30 seconds
            await asyncio.sleep(30)
    
    # ─────────────────────────────────────────────────────────────────────────
    # Query Methods (for signal detection and trend analysis)
    # ─────────────────────────────────────────────────────────────────────────
    
    async def get_stock_history(
        self, 
        code: str, 
        days: int = 60,
        skip_cache: bool = False
    ) -> List[Dict]:
        """Get recent history for a specific stock.
        
        Args:
            code: Stock code
            days: Number of days to fetch (default 60)
            skip_cache: If True, bypass Redis cache (for real-time services)
        
        Returns:
            List of history records as dicts
        """
        if not db.pool:
            return []
        
        # Try cache first (unless skip_cache is True)
        cache_key = f"stock_history:{code}:{days}"
        
        if not skip_cache and db.redis:
            try:
                from app.core.database import get_cache
                cache = get_cache()
                cached = await cache.get_json(cache_key)
                if cached:
                    return cached
            except Exception:
                pass  # Cache miss or error, fall through to DB
        
        # Query database
        rows = await db.pool.fetch("""
            SELECT code, date, open, high, low, close, volume, 
                   turnover, change_pct, turnover_rate, amplitude
            FROM stock_history
            WHERE code = $1
            ORDER BY date DESC
            LIMIT $2
        """, code, days)
        
        # Convert to serializable format
        result = []
        for r in rows:
            record = dict(r)
            # Convert date to string for JSON serialization
            if record.get('date'):
                record['date'] = record['date'].isoformat()
            # Convert Decimal to float
            for key in ['open', 'high', 'low', 'close', 'turnover', 'change_pct', 'turnover_rate', 'amplitude']:
                if record.get(key) is not None:
                    record[key] = float(record[key])
            result.append(record)
        
        # Cache result (TTL 2 hours - data is relatively static)
        if not skip_cache and db.redis and result:
            try:
                from app.core.database import get_cache
                cache = get_cache()
                await cache.set_json(cache_key, result, ttl=7200)  # 2 hours
            except Exception:
                pass  # Ignore cache errors
        
        return result
    
    async def invalidate_stock_cache(self, code: str = None):
        """Invalidate stock history cache.
        
        Args:
            code: If provided, invalidate only this stock. Otherwise invalidate all.
        """
        if not db.redis:
            return
        
        try:
            if code:
                # Delete specific stock cache (common day values)
                for days in [30, 60, 120, 250]:
                    await db.redis.delete(f"stock_history:{code}:{days}")
            else:
                # Delete all stock history cache (use pattern scan)
                cursor = 0
                while True:
                    cursor, keys = await db.redis.scan(cursor, match="stock_history:*", count=100)
                    if keys:
                        await db.redis.delete(*keys)
                    if cursor == 0:
                        break
        except Exception as e:
            logger.debug(f"Cache invalidation error: {e}")
    
    async def get_latest_date(self) -> Optional[date]:
        """Get the most recent date in the database."""
        if not db.pool:
            return None
        
        return await db.pool.fetchval(
            "SELECT MAX(date) FROM stock_history"
        )
    
    async def get_stats(self) -> Dict:
        """Get database statistics."""
        if not db.pool:
            return {}
        
        result = await db.pool.fetchrow("""
            SELECT 
                COUNT(*) as total_records,
                COUNT(DISTINCT code) as stock_count,
                MIN(date) as min_date,
                MAX(date) as max_date
            FROM stock_history
        """)
        
        return dict(result) if result else {}

    # ─────────────────────────────────────────────────────────────────────────────
    # DB Access Methods for Analysis
    # ─────────────────────────────────────────────────────────────────────────────

    async def get_daily_market_stats(self, target_date: date) -> Optional[Dict]:
        """Get market stats (up/down counts) for a specific date from DB."""
        if not db.pool:
            return None
            
        try:
            # Check if we have data for this date
            count = await db.pool.fetchval(
                "SELECT COUNT(*) FROM stock_history WHERE date = $1", target_date
            )
            if not count or count < 1000: # Need sufficient sample
                return None
                
            # Aggregate stats
            stats = await db.pool.fetchrow("""
                SELECT 
                    COUNT(*) FILTER (WHERE change_pct > 0) as up_count,
                    COUNT(*) FILTER (WHERE change_pct = 0) as flat_count,
                    COUNT(*) FILTER (WHERE change_pct < 0) as down_count,
                    COALESCE(SUM(volume), 0) as total_volume,
                    COALESCE(SUM(turnover), 0) as total_turnover,
                    COALESCE(AVG(change_pct), 0) as avg_change
                FROM stock_history 
                WHERE date = $1
            """, target_date)
            
            return dict(stats)
            
        except Exception as e:
            logger.error(f"Failed to get daily stats: {e}")
            return None

    async def get_top_gainers_db(self, target_date: date, limit: int = 5) -> List[Dict]:
        """Get top gainers for a specific date from DB."""
        if not db.pool:
            return []
            
        try:
            # Join with stock_info to get names
            rows = await db.pool.fetch("""
                SELECT h.code, i.name, h.change_pct, h.close, h.volume
                FROM stock_history h
                LEFT JOIN stock_info i ON h.code = i.code
                WHERE h.date = $1
                ORDER BY h.change_pct DESC
                LIMIT $2
            """, target_date, limit)
            
            return [dict(r) for r in rows]
            
        except Exception as e:
            logger.error(f"Failed to get top gainers from DB: {e}")
            return []

    async def get_stock_df(self, code: str, days: int = 200):
        """Get historical DataFrame for a stock from DB (Pandas)."""
        if not db.pool:
            return None
        
        # Lazy load pandas
        _, pd = self._get_libs()
        if not pd:
            return None
            
        try:
            rows = await db.pool.fetch("""
                SELECT date, open, close, high, low, volume, change_pct
                FROM stock_history
                WHERE code = $1
                ORDER BY date DESC
                LIMIT $2
            """, code, days)
            
            if not rows:
                return None
                
            # Convert to DataFrame
            data = [dict(r) for r in rows]
            df = pd.DataFrame(data)
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date').reset_index(drop=True)
            
            return df
            
        except Exception as e:
            logger.error(f"Failed to get stock DF from DB: {e}")
            return None


# Singleton
stock_history_service = StockHistoryService()
