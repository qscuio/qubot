"""
Chip Distribution Service (筹码分布服务)

Background service that calculates and caches chip distribution for all stocks.
Uses proper algorithm based on:
- Price normalization (复权)
- K-line volume distribution across OHLC range
- Chip decay based on turnover rate
"""

import asyncio
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional
import json

from app.core.logger import Logger
from app.core.database import db
from app.core.config import settings
from app.core.timezone import CHINA_TZ, china_now, china_today

logger = Logger("ChipDistributionService")


class ChipDistributionService:
    """Service for calculating and caching chip distribution."""
    
    def __init__(self):
        self.is_running = False
        self._scheduler_task = None
        self._update_lock = asyncio.Lock()
    
    async def start(self):
        """Start the chip distribution scheduler."""
        if self.is_running:
            return
        
        self.is_running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("✅ Chip Distribution Service started")
    
    async def stop(self):
        """Stop the service."""
        self.is_running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        logger.info("Chip Distribution Service stopped")
    
    async def initialize(self):
        """Initialize database table for chip distribution."""
        if not db.pool:
            return
        
        try:
            await db.pool.execute("""
                CREATE TABLE IF NOT EXISTS stock_chip_distribution (
                    code VARCHAR(10) NOT NULL,
                    date DATE NOT NULL,
                    distribution JSONB NOT NULL,
                    avg_cost DECIMAL(10,2),
                    profit_ratio DECIMAL(5,2),
                    concentration DECIMAL(5,2),
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (code, date)
                )
            """)
            
            await db.pool.execute("""
                CREATE INDEX IF NOT EXISTS idx_chip_code ON stock_chip_distribution(code)
            """)
            
            logger.info("✅ Chip distribution table initialized")
        except Exception as e:
            logger.error(f"Failed to initialize chip table: {e}")
    
    async def calculate_chip_distribution(
        self, 
        code: str, 
        target_date: date = None,
        lookback_days: int = 120
    ) -> Dict:
        """
        Calculate chip distribution for a stock on a specific date.
        
        Algorithm:
        1. Get historical data with adjusted prices
        2. Distribute each day's volume across price range (OHLC)
        3. Apply decay based on turnover rate
        4. Calculate profit ratio, avg cost, concentration
        """
        if not db.pool:
            return {}
        
        target_date = target_date or china_today()
        
        # Fetch historical data
        rows = await db.pool.fetch("""
            SELECT date, open, high, low, close, volume, turnover_rate
            FROM stock_history
            WHERE code = $1 AND date <= $2
            ORDER BY date DESC
            LIMIT $3
        """, code, target_date, lookback_days)
        
        if not rows or len(rows) < 10:
            return {}
        
        # Reverse to chronological order
        data = list(reversed([dict(r) for r in rows]))
        
        # Get current price (latest close)
        current_price = float(data[-1]['close'])
        
        # Find price range
        min_price = min(float(d['low']) for d in data)
        max_price = max(float(d['high']) for d in data)
        
        # Add padding
        padding = (max_price - min_price) * 0.1
        min_price = max(0.01, min_price - padding)
        max_price = max_price + padding
        
        # Create price buckets
        num_buckets = 30
        bucket_size = (max_price - min_price) / num_buckets
        chips = [0.0] * num_buckets  # Current chip distribution
        
        # Process each day
        for i, d in enumerate(data):
            volume = float(d['volume'] or 0)
            if volume <= 0:
                continue
            
            open_p = float(d['open'])
            high_p = float(d['high'])
            low_p = float(d['low'])
            close_p = float(d['close'])
            turnover_rate = float(d.get('turnover_rate') or 0) / 100  # Convert to decimal
            
            # Decay existing chips based on turnover rate
            # Higher turnover = more old chips are "replaced"
            decay_factor = max(0, 1 - turnover_rate)
            chips = [c * decay_factor for c in chips]
            
            # Distribute today's volume into buckets
            # Use weighted distribution based on candle type
            is_bullish = close_p >= open_p
            
            # Calculate volume distribution across price range
            body_low = min(open_p, close_p)
            body_high = max(open_p, close_p)
            
            # Distribute volume: 60% in body, 20% in each shadow
            body_volume = volume * 0.6
            lower_shadow_volume = volume * 0.2
            upper_shadow_volume = volume * 0.2
            
            # Add volume to buckets
            for b in range(num_buckets):
                bucket_low = min_price + b * bucket_size
                bucket_high = bucket_low + bucket_size
                bucket_mid = (bucket_low + bucket_high) / 2
                
                # Check which part of candle this bucket belongs to
                added_volume = 0
                
                # Body
                if bucket_mid >= body_low and bucket_mid <= body_high:
                    body_range = body_high - body_low
                    if body_range > 0:
                        added_volume += body_volume / max(1, (body_high - body_low) / bucket_size)
                
                # Lower shadow
                if bucket_mid >= low_p and bucket_mid < body_low:
                    shadow_range = body_low - low_p
                    if shadow_range > 0:
                        added_volume += lower_shadow_volume / max(1, shadow_range / bucket_size)
                
                # Upper shadow
                if bucket_mid > body_high and bucket_mid <= high_p:
                    shadow_range = high_p - body_high
                    if shadow_range > 0:
                        added_volume += upper_shadow_volume / max(1, shadow_range / bucket_size)
                
                chips[b] += added_volume
        
        # Normalize and create distribution
        max_chip = max(chips) if chips else 1
        distribution = []
        profit_volume = 0
        loss_volume = 0
        weighted_sum = 0
        total_chips = 0
        
        for b in range(num_buckets):
            price = min_price + (b + 0.5) * bucket_size
            chip_value = chips[b]
            percentage = (chip_value / max_chip * 100) if max_chip > 0 else 0
            is_profit = price <= current_price
            
            distribution.append({
                'price': round(price, 2),
                'percentage': round(percentage, 1),
                'isProfit': is_profit
            })
            
            if chip_value > 0:
                if is_profit:
                    profit_volume += chip_value
                else:
                    loss_volume += chip_value
                weighted_sum += price * chip_value
                total_chips += chip_value
        
        avg_cost = weighted_sum / total_chips if total_chips > 0 else current_price
        profit_ratio = (profit_volume / (profit_volume + loss_volume) * 100) if (profit_volume + loss_volume) > 0 else 0
        
        # Concentration: top 5 buckets / total
        sorted_chips = sorted(chips, reverse=True)
        top_sum = sum(sorted_chips[:5])
        total_sum = sum(chips)
        concentration = (top_sum / total_sum * 100) if total_sum > 0 else 0
        
        return {
            'code': code,
            'date': str(target_date),
            'currentPrice': current_price,
            'distribution': list(reversed(distribution)),  # High to low
            'avgCost': round(avg_cost, 2),
            'profitRatio': round(profit_ratio, 1),
            'concentration': round(concentration, 1)
        }
    
    async def get_chip_distribution(self, code: str, target_date: date = None) -> Dict:
        """Get cached chip distribution, or calculate if not available."""
        if not db.pool:
            return {}
        
        target_date = target_date or china_today()
        
        # Try to get from cache
        row = await db.pool.fetchrow("""
            SELECT distribution, avg_cost, profit_ratio, concentration
            FROM stock_chip_distribution
            WHERE code = $1 AND date = $2
        """, code, target_date)
        
        if row:
            dist = row['distribution']
            if isinstance(dist, str):
                dist = json.loads(dist)
            return {
                'code': code,
                'date': str(target_date),
                'distribution': dist,
                'avgCost': float(row['avg_cost'] or 0),
                'profitRatio': float(row['profit_ratio'] or 0),
                'concentration': float(row['concentration'] or 0)
            }
        
        # Calculate and cache
        result = await self.calculate_chip_distribution(code, target_date)
        if result and result.get('distribution'):
            await self._save_chip_distribution(result)
        
        return result
    
    async def _save_chip_distribution(self, data: Dict):
        """Save chip distribution to database."""
        if not db.pool or not data:
            return
        
        try:
            # Use SQL NOW() to avoid timezone-aware/naive mismatch
            await db.pool.execute("""
                INSERT INTO stock_chip_distribution 
                    (code, date, distribution, avg_cost, profit_ratio, concentration, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, NOW())
                ON CONFLICT (code, date) DO UPDATE SET
                    distribution = EXCLUDED.distribution,
                    avg_cost = EXCLUDED.avg_cost,
                    profit_ratio = EXCLUDED.profit_ratio,
                    concentration = EXCLUDED.concentration,
                    updated_at = NOW()
            """, 
                data['code'],
                date.fromisoformat(data['date']),
                json.dumps(data['distribution']),
                data['avgCost'],
                data['profitRatio'],
                data['concentration']
            )
        except Exception as e:
            logger.warn(f"Failed to save chip distribution for {data['code']}: {e}")
    
    async def update_all_stocks(self):
        """Background task to update chip distribution for all stocks."""
        if self._update_lock.locked():
            logger.info("Chip update already in progress, skipping")
            return
        
        async with self._update_lock:
            logger.info("Starting chip distribution update for all stocks...")
            
            # Get all stock codes from history
            rows = await db.pool.fetch("SELECT DISTINCT code FROM stock_history")
            codes = [r['code'] for r in rows]
            
            today = china_today()
            updated = 0
            errors = 0
            
            for code in codes:
                try:
                    result = await self.calculate_chip_distribution(code, today)
                    if result and result.get('distribution'):
                        await self._save_chip_distribution(result)
                        updated += 1
                except Exception as e:
                    errors += 1
                    if errors < 5:
                        logger.warn(f"Failed to update chips for {code}: {e}")
                
                # Small delay to avoid overwhelming DB
                if updated % 100 == 0:
                    await asyncio.sleep(0.1)
            
            logger.info(f"✅ Chip distribution update complete: {updated}/{len(codes)}, {errors} errors")
    
    async def _scheduler_loop(self):
        """Background scheduler for daily chip updates at 15:30."""
        update_time = "15:30"
        triggered_today = set()
        
        while self.is_running:
            try:
                now = china_now()
                time_str = now.strftime("%H:%M")
                date_str = now.strftime("%Y-%m-%d")
                
                if time_str == "00:00":
                    triggered_today.clear()
                
                key = f"{date_str}_chips"
                
                # Update at 15:30 on weekdays (after market close)
                if now.weekday() < 5 and time_str == update_time and key not in triggered_today:
                    triggered_today.add(key)
                    # Run in background task to not block
                    asyncio.create_task(self.update_all_stocks())
                    
            except Exception as e:
                logger.error(f"Chip scheduler error: {e}")
            
            await asyncio.sleep(30)


# Singleton
chip_distribution_service = ChipDistributionService()
