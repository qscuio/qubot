"""
A-Share Stock History Service (A股历史数据服务)

Background service that builds and maintains a local PostgreSQL copy of
5-year A-share stock history data for signal detection and trend analysis.

Features:
- Fetches all A-share stock codes (~5000 stocks)
- Backfills 5 years of OHLCV history on first run
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
        self._ak = None  # AkShare module (lazy load)
        self._pd = None  # Pandas module (lazy load)
        # Use single-worker thread pool for background operations
        # This ensures backfill doesn't block the event loop
        from concurrent.futures import ThreadPoolExecutor
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="stock_history")
    
    def _get_libs(self):
        """Lazy load akshare and pandas modules."""
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
            try:
                info_stats = await db.pool.fetchrow("""
                    SELECT COUNT(*) as count, MAX(updated_at) as last_update 
                    FROM stock_info
                """)
                if info_stats and info_stats['count'] > 4000:
                    last_update = info_stats['last_update']
                    today = china_today()
                    if last_update and last_update.date() == today:
                        logger.info(f"✅ Stock list is up to date (Updated: {last_update}), skipping initialization check")
                        return
            except Exception as e:
                logger.warn(f"Failed to check stock_info stats: {e}")
        
        # Get all current A-share stock codes
        all_codes = await self.get_all_stock_codes()
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
                # Run in background thread to avoid blocking event loop
                loop = asyncio.get_event_loop()
                loop.run_in_executor(self._executor, self._update_stale_stocks_sync, stale_stocks)
        
        # Handle missing stocks
        if coverage < 0.9:
            if missing_codes:
                logger.info(
                    f"Stock coverage: {coverage:.1%} ({db_stock_count}/{len(all_codes)}), "
                    f"resuming backfill for {len(missing_codes)} missing stocks..."
                )
                # Run in background thread to avoid blocking event loop
                loop = asyncio.get_event_loop()
                loop.run_in_executor(self._executor, self._backfill_stocks_sync, missing_codes)
            else:
                logger.info("All stocks have history data")
        else:
            logger.info(f"Stock coverage: {coverage:.1%} ({db_stock_count}/{len(all_codes)}) - sufficient")
    
    async def _backfill_all_stocks(self):
        """Backfill 5 years of history for all A-share stocks."""
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
        """Backfill 5 years of history for specified stock codes."""
        ak, pd = self._get_libs()
        if not ak or not pd:
            return
        
        # Calculate date range (5 years)
        end_date = china_today()
        start_date = end_date - timedelta(days=5 * 365)
        
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
    
    def _update_stale_stocks_sync(self, codes: List[str]):
        """Synchronous version that runs entirely in background thread."""
        import time
        import asyncpg
        
        ak, pd = self._get_libs()
        if not ak or not pd:
            return
        
        today = china_today()
        logger.info(f"[BG Thread] Updating {len(codes)} stocks with stale data...")
        
        success_count = 0
        error_count = 0
        
        # Create sync database connection using DATABASE_URL from settings
        try:
            import asyncio
            from app.core.config import settings
            loop = asyncio.new_event_loop()
            conn = loop.run_until_complete(
                asyncpg.connect(settings.DATABASE_URL)
            )
        except Exception as e:
            logger.error(f"[BG Thread] Failed to connect to DB: {e}")
            return
        
        try:
            for i, code in enumerate(codes):
                try:
                    latest = loop.run_until_complete(
                        conn.fetchval("SELECT MAX(date) FROM stock_history WHERE code = $1", code)
                    )
                    
                    if not latest:
                        continue
                    
                    start_date = latest + timedelta(days=1)
                    start_str = start_date.strftime("%Y%m%d")
                    end_str = today.strftime("%Y%m%d")
                    
                    # Fetch data
                    df = ak.stock_zh_a_hist(
                        symbol=code, period="daily",
                        start_date=start_str, end_date=end_str, adjust="qfq"
                    )
                    
                    if df is not None and not df.empty:
                        records = self._prepare_records(code, df, pd)
                        if records:
                            loop.run_until_complete(self._save_records_sync(conn, records))
                            success_count += 1
                    
                    if (i + 1) % 100 == 0:
                        logger.info(f"[BG Thread] Update: {i+1}/{len(codes)} ({success_count} success)")
                    
                    time.sleep(0.5)
                    
                except Exception as e:
                    error_count += 1
                    if error_count <= 10:
                        logger.warn(f"[BG Thread] Failed to update {code}: {e}")
        finally:
            loop.run_until_complete(conn.close())
            loop.close()
        
        logger.info(f"✅ [BG Thread] Update complete: {success_count}/{len(codes)}, {error_count} errors")
    
    def _backfill_stocks_sync(self, codes: List[str]):
        """Synchronous version that runs entirely in background thread."""
        import time
        import asyncpg
        
        ak, pd = self._get_libs()
        if not ak or not pd:
            return
        
        end_date = china_today()
        start_date = end_date - timedelta(days=5 * 365)
        start_str = start_date.strftime("%Y%m%d")
        end_str = end_date.strftime("%Y%m%d")
        
        logger.info(f"[BG Thread] Backfilling {len(codes)} stocks from {start_date} to {end_date}")
        
        success_count = 0
        error_count = 0
        
        # Create sync database connection using DATABASE_URL from settings
        try:
            import asyncio
            from app.core.config import settings
            loop = asyncio.new_event_loop()
            conn = loop.run_until_complete(
                asyncpg.connect(settings.DATABASE_URL)
            )
        except Exception as e:
            logger.error(f"[BG Thread] Failed to connect to DB: {e}")
            return
        
        try:
            for i, code in enumerate(codes):
                try:
                    df = ak.stock_zh_a_hist(
                        symbol=code, period="daily",
                        start_date=start_str, end_date=end_str, adjust="qfq"
                    )
                    
                    if df is not None and not df.empty:
                        records = self._prepare_records(code, df, pd)
                        if records:
                            loop.run_until_complete(self._save_records_sync(conn, records))
                            success_count += 1
                    
                    if (i + 1) % 100 == 0:
                        logger.info(f"[BG Thread] Backfill: {i+1}/{len(codes)} ({success_count} success)")
                    
                    time.sleep(0.5)
                    
                except Exception as e:
                    error_count += 1
                    if error_count <= 10:
                        logger.warn(f"[BG Thread] Failed to backfill {code}: {e}")
        finally:
            loop.run_until_complete(conn.close())
            loop.close()
        
        logger.info(f"✅ [BG Thread] Backfill complete: {success_count}/{len(codes)}, {error_count} errors")
    
    def _prepare_records(self, code: str, df, pd):
        """Prepare records for database insertion."""
        records = []
        for _, row in df.iterrows():
            try:
                record = (
                    code,
                    pd.to_datetime(row['日期']).date(),
                    float(row.get('开盘', 0)),
                    float(row.get('最高', 0)),
                    float(row.get('最低', 0)),
                    float(row.get('收盘', 0)),
                    int(row.get('成交量', 0)),
                    float(row.get('成交额', 0)),
                    float(row.get('振幅', 0)),
                    float(row.get('涨跌幅', 0)),
                    float(row.get('涨跌额', 0)),
                    float(row.get('换手率', 0)),
                )
                records.append(record)
            except:
                continue
        return records
    
    async def _save_records_sync(self, conn, records):
        """Save records using provided connection."""
        await conn.executemany("""
            INSERT INTO stock_history 
            (code, date, open, high, low, close, volume, turnover, 
             amplitude, change_pct, change_amt, turnover_rate)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            ON CONFLICT (code, date) DO UPDATE SET
            open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
            close = EXCLUDED.close, volume = EXCLUDED.volume, turnover = EXCLUDED.turnover,
            amplitude = EXCLUDED.amplitude, change_pct = EXCLUDED.change_pct,
            change_amt = EXCLUDED.change_amt, turnover_rate = EXCLUDED.turnover_rate
        """, records)
    
    async def get_all_stock_codes(self) -> List[str]:
        """Fetch all A-share stock codes."""
        ak, pd = self._get_libs()
        if not ak or not pd:
            return []

        import time
        start_time = time.monotonic()
        logger.info("Fetching A-share stock list via Akshare (may show progress bar)...")

        try:
            # Get current stock list
            logger.info("Calling ak.stock_zh_a_spot_em (60s timeout)...")
            try:
                # Add timeout to prevent hanging indefinitely
                df = await asyncio.wait_for(
                    asyncio.to_thread(ak.stock_zh_a_spot_em),
                    timeout=60.0
                )
            except asyncio.TimeoutError:
                logger.error("Timeout calling ak.stock_zh_a_spot_em")
                return []
            except Exception as e:
                logger.error(f"Error calling stock_zh_a_spot_em: {e}")
                raise e
            
            if df is None or df.empty:
                logger.error("Failed to fetch stock list: stock_zh_a_spot_em returned None or empty")
                return []
            
            # Filter main board stocks (exclude ST, 退市)
            # A-share codes: 00xxxx (SZ), 30xxxx (创业板), 60xxxx (SH), 68xxxx (科创板)
            df_filtered = df[
                ~df['名称'].str.contains('ST|退', na=False) &
                (df['代码'].str.match(r'^[036]'))
            ][['代码', '名称']]
            
            codes = df_filtered['代码'].tolist()
            
            # Best-effort: update stock name mapping for UI display
            if db.pool:
                try:
                    records = []
                    for _, row in df_filtered.iterrows():
                        code_val = row.get('代码')
                        name_val = row.get('名称')
                        if pd.notna(code_val) and pd.notna(name_val):
                            records.append((str(code_val), str(name_val)))
                    if records:
                        await db.pool.executemany("""
                            INSERT INTO stock_info (code, name, updated_at)
                            VALUES ($1, $2, NOW())
                            ON CONFLICT (code) DO UPDATE SET
                                name = EXCLUDED.name,
                                updated_at = NOW()
                        """, records)
                except Exception as e:
                    logger.debug(f"Failed to update stock_info: {e}")
            
            elapsed = time.monotonic() - start_time
            logger.info(f"Found {len(codes)} A-share stocks (elapsed={elapsed:.1f}s)")
            return [str(c) for c in codes]
            
        except Exception as e:
            elapsed = time.monotonic() - start_time
            logger.error(f"Failed to get stock codes after {elapsed:.1f}s: {e}")
            return []
    
    async def _fetch_and_save_history(
        self, 
        code: str, 
        start_date: str, 
        end_date: str
    ) -> int:
        """Fetch history for a single stock and save to database."""
        ak, pd = self._get_libs()
        if not ak or not pd or not db.pool:
            return 0
        
        try:
            # Fetch historical data with forward-adjusted prices
            df = await asyncio.to_thread(
                ak.stock_zh_a_hist,
                symbol=code,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust="qfq"  # 前复权
            )
            
            if df is None or df.empty:
                return 0
            
            # Column mapping from akshare
            # 日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额, 振幅, 涨跌幅, 涨跌额, 换手率
            records = []
            for _, row in df.iterrows():
                record = (
                    code,
                    pd.to_datetime(row['日期']).date(),
                    float(row.get('开盘', 0)),
                    float(row.get('最高', 0)),
                    float(row.get('最低', 0)),
                    float(row.get('收盘', 0)),
                    int(row.get('成交量', 0)),
                    float(row.get('成交额', 0)),
                    float(row.get('振幅', 0)),
                    float(row.get('涨跌幅', 0)),
                    float(row.get('涨跌额', 0)),
                    float(row.get('换手率', 0)),
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
            raise e
    
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
        
        async def update_one(code):
            nonlocal success_count, error_count, processed_count, last_progress_time
            async with sem:
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
                    
                    # Progress logging (every 200)
                    if processed_count % 200 == 0:
                        logger.info(f"Daily update progress: {processed_count}/{len(codes)} stocks")
                    
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

    async def update_all_stocks(self, progress_callback: Optional[Callable] = None):
        """Daily update - fetch today's data for all stocks.
        
        Tries batch update first, falls back to concurrent individual update.
        """
        today = china_today()
        # Skip weekends
        if today.weekday() >= 5:
            logger.info("Weekend, skipping daily update")
            return

        # Try batch update first
        success = await self.update_all_stocks_batch(progress_callback)
        
        if success:
            return
            
        # Fallback to concurrent update
        logger.warn("Batch update failed, falling back to concurrent individual update...")
        if progress_callback:
            await progress_callback("数据同步", 0, 100, "⚠️ 批量更新失败，切换到备用模式...")
            
        await self._update_all_stocks_concurrent(progress_callback)
    
    async def update_all_stocks_batch(self, progress_callback: Optional[Callable] = None) -> bool:
        """Batch update using ak.stock_zh_a_spot_em() - much faster.
        
        Returns:
            bool: True if successful, False if failed (triggering fallback)
        """
        ak, pd = self._get_libs()
        if not ak or not pd or not db.pool:
            return False
        
        today = china_today()
        date_str = today.strftime("%Y-%m-%d")
        logger.info(f"Starting batch daily update for {date_str}")
        
        if progress_callback:
            await progress_callback("数据同步", 0, 100, "⏳ 正在批量获取实时数据...")
            
        # Retry logic (3 attempts)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    logger.info(f"Retry attempt {attempt + 1}/{max_retries}...")
                    if progress_callback:
                        await progress_callback("数据同步", 0, 100, f"⏳ 正在重试 ({attempt + 1}/{max_retries})...")
                    await asyncio.sleep(2 * attempt)  # Exponential backoff
                
                # Fetch all spot data with timeout
                logger.info("Calling ak.stock_zh_a_spot_em()...")
                df = await asyncio.wait_for(
                    asyncio.to_thread(ak.stock_zh_a_spot_em),
                    timeout=300.0  # 5 minute timeout
                )
                
                if df is None or df.empty:
                    logger.warn("Batch update returned empty data")
                    continue
                    
                # Filter valid A-share stocks
                df_filtered = df[
                    ~df['名称'].str.contains('ST|退', na=False) &
                    (df['代码'].str.match(r'^[036]'))
                ].copy()
                
                total_stocks = len(df_filtered)
                logger.info(f"Got {total_stocks} valid stocks from API")
                
                if progress_callback:
                    await progress_callback("数据同步", 10, 100, f"⏳ 获取到 {total_stocks} 只股票，准备入库...")
                
                # Prepare records for bulk insert
                records = []
                for _, row in df_filtered.iterrows():
                    try:
                        code = str(row['代码'])
                        close = float(row['最新价'])
                        open_price = float(row['今开'])
                        high = float(row['最高'])
                        low = float(row['最低'])
                        volume = float(row['成交量'])
                        turnover = float(row['成交额'])
                        change_pct = float(row['涨跌幅'])
                        turnover_rate = float(row['换手率']) if pd.notna(row['换手率']) else 0.0
                        amplitude = float(row['振幅']) if pd.notna(row['振幅']) else 0.0
                        
                        if close <= 0 or open_price <= 0:
                            continue
                            
                        records.append((
                            code, today, open_price, high, low, close, 
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
                logger.error(f"Batch update attempt {attempt + 1} failed: {e}")
                
        # All retries failed
        logger.error("All batch update attempts failed")
        return False
    
    async def sync_with_integrity_check(self, progress_callback: Optional[Callable] = None):
        """Sync data with integrity check - fills in missing 7-day data first.
        
        This method:
        1. Checks for stocks missing data in the last 7 trading days
        2. Fills in the gaps for those stocks
        3. Updates all stocks with today's data
        
        Args:
            progress_callback: Optional async callback(stage, current, total, message)
        
        Called by /dbsync command and daily 15:15 scheduled task.
        """
        ak, pd = self._get_libs()
        if not ak or not pd or not db.pool:
            return
        
        today = china_today()
        
        # Skip weekends
        if today.weekday() >= 5:
            logger.info("Weekend, skipping sync")
            return
        
        logger.info("🔍 Starting sync with data integrity check...")
        
        # Notify start
        if progress_callback:
            await progress_callback("开始同步", 0, 100, "🔍 正在检查数据完整性...")
        
        # Step 1: Find stocks with missing 7-day data
        try:
            stocks_to_fix = await self._check_recent_data_integrity(progress_callback)
            
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
        
        # Step 2: Regular daily update for today's data
        await self.update_all_stocks(progress_callback)
    
    async def _check_recent_data_integrity(self, progress_callback: Optional[Callable] = None) -> List[Dict]:
        """Check which stocks are missing data in the last 7 trading days.
        
        Returns list of dicts with 'code' and 'missing_from' date.
        """
        if not db.pool:
            return []
        
        today = china_today()
        seven_days_ago = today - timedelta(days=10)  # Look back 10 days to cover weekends
        
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
                # If latest data is not today, needs update
                days_old = (today - latest).days
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
        
        return stocks_to_fix[:500]  # Limit to 500 stocks per run to avoid overload
    
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


# Singleton
stock_history_service = StockHistoryService()
