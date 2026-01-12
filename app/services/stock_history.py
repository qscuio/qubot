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
        """Initialize service - backfill 5 years of history if needed."""
        if not db.pool:
            logger.warn("Database not connected, skipping initialization")
            return
        
        # Check if we have any data
        count = await db.pool.fetchval("SELECT COUNT(*) FROM stock_history")
        
        if count > 0:
            # Get date range
            result = await db.pool.fetchrow("""
                SELECT MIN(date) as min_date, MAX(date) as max_date, 
                       COUNT(DISTINCT code) as stock_count
                FROM stock_history
            """)
            logger.info(
                f"Found {count:,} records: {result['stock_count']} stocks, "
                f"from {result['min_date']} to {result['max_date']}"
            )
            return
        
        # No data - run initial backfill in background
        logger.info("No history data found, starting 5-year backfill in background...")
        asyncio.create_task(self._backfill_all_stocks())
    
    async def _backfill_all_stocks(self):
        """Backfill 5 years of history for all A-share stocks."""
        ak, pd = self._get_libs()
        if not ak or not pd:
            return
        
        # Calculate date range (5 years)
        end_date = china_today()
        start_date = end_date - timedelta(days=5 * 365)
        
        start_str = start_date.strftime("%Y%m%d")
        end_str = end_date.strftime("%Y%m%d")
        
        logger.info(f"Backfilling history from {start_date} to {end_date}")
        
        # Get all A-share stock codes
        codes = await self.get_all_stock_codes()
        if not codes:
            logger.error("Failed to get stock codes")
            return
        
        logger.info(f"Starting backfill for {len(codes)} stocks...")
        
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
                
                # Rate limiting - 0.3s delay between requests
                await asyncio.sleep(0.3)
                
            except Exception as e:
                error_count += 1
                if error_count <= 10:  # Only log first 10 errors
                    logger.warn(f"Failed to backfill {code}: {e}")
        
        logger.info(
            f"✅ Backfill complete: {success_count}/{len(codes)} stocks, "
            f"{error_count} errors"
        )
    
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
