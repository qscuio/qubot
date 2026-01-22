import asyncio
import datetime
import time
from typing import List, Dict, Any, Optional
from app.core.logger import Logger
from app.services.data_provider.base import BaseDataProvider

logger = Logger("AkShareProvider")

class AkShareProvider(BaseDataProvider):
    def __init__(self):
        self._ak = None
        self._pd = None
        # Rate Limiting
        self._last_request_time = 0
        self._request_interval = 3.0  # 3 seconds between requests
        self._lock = asyncio.Lock()
        
        # Circuit Breaker
        self._consecutive_failures = 0
        self._circuit_open_until = 0  # Timestamp when circuit closes
        self._failure_threshold = 5   # Open circuit after N failures
        self._circuit_timeout = 60    # Keep circuit open for N seconds
        
    def get_name(self) -> str:
        return "akshare"
    
    def is_available(self) -> bool:
        """Check if provider is available (circuit closed)."""
        if self._circuit_open_until > time.time():
            return False
        return True
        
    async def _rate_limit(self):
        """Ensure minimum interval between requests."""
        async with self._lock:
            now = asyncio.get_event_loop().time()
            elapsed = now - self._last_request_time
            if elapsed < self._request_interval:
                await asyncio.sleep(self._request_interval - elapsed)
            self._last_request_time = asyncio.get_event_loop().time()
    
    def _record_success(self):
        """Record successful request, reset circuit breaker."""
        self._consecutive_failures = 0
        
    def _record_failure(self):
        """Record failed request, possibly open circuit."""
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._failure_threshold:
            self._circuit_open_until = time.time() + self._circuit_timeout
            logger.warn(f"Circuit breaker OPEN: Too many failures ({self._consecutive_failures}). Disabled for {self._circuit_timeout}s")
            self._consecutive_failures = 0  # Reset counter

    async def initialize(self) -> bool:
        """Lazy load libraries."""
        try:
            import akshare as ak
            import pandas as pd
            self._ak = ak
            self._pd = pd
            return True
        except ImportError:
            logger.error("AkShare or Pandas not installed.")
            return False

    async def shutdown(self):
        pass

    async def get_stock_list(self) -> List[Dict[str, str]]:
        if not self._ak:
            if not await self.initialize(): return []
        
        if not self.is_available():
            return []
            
        try:
            await self._rate_limit()
            df = await asyncio.to_thread(self._ak.stock_zh_a_spot_em)
            if df is None or df.empty:
                return []
            
            self._record_success()
                
            # Filter main board
            # Columns: 代码, 名称 ...
            results = []
            for _, row in df.iterrows():
                code = str(row['代码'])
                name = str(row['名称'])
                # Basic filtering
                if code.startswith(('0', '3', '6', '4', '8')):
                    results.append({"code": code, "name": name})
            return results
        except Exception as e:
            self._record_failure()
            logger.error(f"Failed to get stock list: {e}")
            return []

    async def get_daily_bars(
        self, 
        code: str, 
        start_date: str, 
        end_date: str,
        adjust: str = "qfq"
    ) -> List[Dict[str, Any]]:
        if not self._ak:
            if not await self.initialize(): return []
        
        if not self.is_available():
            return []

        try:
            await self._rate_limit()
            # start_date/end_date should be YYYYMMDD
            df = await asyncio.to_thread(
                self._ak.stock_zh_a_hist,
                symbol=code,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust=adjust
            )
            
            if df is None or df.empty:
                return []
            
            self._record_success()

            results = []
            for _, row in df.iterrows():
                try:
                    # Convert '2023-01-01' string to date object
                    date_val = self._pd.to_datetime(row['日期']).date()
                    
                    item = {
                        "date": date_val,
                        "open": float(row.get('开盘', 0)),
                        "high": float(row.get('最高', 0)),
                        "low": float(row.get('最低', 0)),
                        "close": float(row.get('收盘', 0)),
                        "volume": int(row.get('成交量', 0)),
                        "turnover": float(row.get('成交额', 0)),
                        "amplitude": float(row.get('振幅', 0)),
                        "change_pct": float(row.get('涨跌幅', 0)),
                        "change_amt": float(row.get('涨跌额', 0)),
                        "turnover_rate": float(row.get('换手率', 0))
                    }
                    results.append(item)
                except Exception:
                    continue
            return results
            
        except Exception as e:
            self._record_failure()
            logger.warn(f"AkShare fetch error for {code}: {e}")
            return []

    async def get_trading_dates(self, start_date: str, end_date: str) -> List[datetime.date]:
        if not self._ak:
            if not await self.initialize(): return []
        
        if not self.is_available():
            return []
            
        try:
            await self._rate_limit()
            # Use tool_trade_date_hist_sina
            df = await asyncio.to_thread(self._ak.tool_trade_date_hist_sina)
            if df is None or df.empty:
                return []
            
            self._record_success()
                
            dates = self._pd.to_datetime(df['trade_date']).dt.date.tolist()
            
            # Filter range
            s_date = datetime.datetime.strptime(start_date, "%Y%m%d").date()
            e_date = datetime.datetime.strptime(end_date, "%Y%m%d").date()
            
            valid_dates = [d for d in dates if s_date <= d <= e_date]
            valid_dates.sort()
            return valid_dates
        except Exception as e:
            self._record_failure()
            logger.error(f"Failed to get trading dates (AkShare): {e}")
            return []
