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
from typing import List, Dict, Optional

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
        
        try:
            # Get current stock list
            df = await asyncio.to_thread(ak.stock_zh_a_spot_em)
            
            if df is None or df.empty:
                logger.error("Failed to fetch stock list")
                return []
            
            # Filter main board stocks (exclude ST, 退市)
            # A-share codes: 00xxxx (SZ), 30xxxx (创业板), 60xxxx (SH), 68xxxx (科创板)
            codes = df[
                ~df['名称'].str.contains('ST|退', na=False) &
                (df['代码'].str.match(r'^[036]'))
            ]['代码'].tolist()
            
            logger.info(f"Found {len(codes)} A-share stocks")
            return [str(c) for c in codes]
            
        except Exception as e:
            logger.error(f"Failed to get stock codes: {e}")
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
    
    async def update_all_stocks(self):
        """Daily update - fetch today's data for all stocks."""
        ak, pd = self._get_libs()
        if not ak or not pd or not db.pool:
            return
        
        today = china_today()
        
        # Skip weekends
        if today.weekday() >= 5:
            logger.info("Weekend, skipping daily update")
            return
        
        date_str = today.strftime("%Y%m%d")
        logger.info(f"Starting daily update for {date_str}")
        
        # Get all stock codes
        codes = await self.get_all_stock_codes()
        if not codes:
            return
        
        success_count = 0
        error_count = 0
        
        for i, code in enumerate(codes):
            try:
                records = await self._fetch_and_save_history(code, date_str, date_str)
                if records > 0:
                    success_count += 1
                
                # Progress logging
                if (i + 1) % 200 == 0:
                    logger.info(f"Daily update progress: {i + 1}/{len(codes)} stocks")
                
                # Rate limiting
                await asyncio.sleep(0.2)
                
            except Exception as e:
                error_count += 1
                if error_count <= 5:
                    logger.warn(f"Failed to update {code}: {e}")
        
        logger.info(
            f"✅ Daily update complete: {success_count}/{len(codes)} stocks updated"
        )
    
    async def _scheduler_loop(self):
        """Background scheduler for daily updates at 15:15."""
        update_time = "15:15"
        triggered_today = set()
        
        while self.is_running:
            try:
                now = china_now()
                time_str = now.strftime("%H:%M")
                date_str = now.strftime("%Y-%m-%d")
                
                # Reset triggered set at midnight
                if time_str == "00:00":
                    triggered_today.clear()
                
                key = f"{date_str}_update"
                
                # Run daily update at 15:15 on weekdays
                if now.weekday() < 5 and time_str == update_time and key not in triggered_today:
                    triggered_today.add(key)
                    logger.info("Triggering daily stock history update")
                    asyncio.create_task(self.update_all_stocks())
                
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
        days: int = 60
    ) -> List[Dict]:
        """Get recent history for a specific stock."""
        if not db.pool:
            return []
        
        rows = await db.pool.fetch("""
            SELECT code, date, open, high, low, close, volume, 
                   turnover, change_pct, turnover_rate
            FROM stock_history
            WHERE code = $1
            ORDER BY date DESC
            LIMIT $2
        """, code, days)
        
        return [dict(r) for r in rows]
    
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
