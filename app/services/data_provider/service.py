from typing import List, Dict, Any, Optional
import asyncio
from datetime import datetime, timedelta
from app.core.logger import Logger
from app.services.data_provider.base import BaseDataProvider
from app.services.data_provider.akshare_provider import AkShareProvider
from app.services.data_provider.baostock_provider import BaostockProvider

logger = Logger("DataProvider")

class DataProviderService:
    """Facade for accessing stock data from multiple providers."""
    
    def __init__(self):
        self.providers: List[BaseDataProvider] = []
        # Primary provider
        self.ak_provider = AkShareProvider()
        # Secondary provider
        self.bs_provider = BaostockProvider()
        
        # Register order logic could be dynamic, but for now hardcode priority
        self.providers = [self.ak_provider, self.bs_provider]
        
        # Cache for trading dates
        self._trading_dates = []
        self._cache_time = None

    async def initialize(self):
        """Initialize all providers."""
        for p in self.providers:
            await p.initialize()
            logger.info(f"Initialized provider: {p.get_name()}")
        
        # Pre-fill cache
        await self._refresh_cache_if_needed()

    async def shutdown(self):
        """Shutdown all providers."""
        for p in self.providers:
            await p.shutdown()

    async def get_stock_list(self) -> List[Dict[str, str]]:
        """Fetch stock list from primary provider (AkShare usually best for this)."""
        # Specific logic: AkShare has best list
        return await self.ak_provider.get_stock_list()

    async def get_daily_bars(
        self, 
        code: str, 
        start_date: str, 
        end_date: str,
        adjust: str = "qfq"
    ) -> List[Dict[str, Any]]:
        """Fetch daily bars with fallback logic and local filtering."""
        
        # Optimization: Local Filter
        # Check if the requested range contains any trading days
        # If not (e.g. weekend), return empty immediately
        if await self._should_skip_request(start_date, end_date):
            return []
        
        errors = []
        
        for provider in self.providers:
            try:
                data = await provider.get_daily_bars(code, start_date, end_date, adjust)
                if data:
                    if provider.get_name() != "akshare":
                        logger.info(f"Fetched {len(data)} records for {code} from {provider.get_name()}")
                    return data
            except Exception as e:
                errors.append(f"{provider.get_name()}: {e}")
        
        if errors:
            logger.warn(f"Failed to fetch data for {code} from all providers. Errors: {errors}")
            
        return []

    async def get_trading_dates(self, start_date: str, end_date: str) -> List[Any]:
        """Fetch trading dates."""
        # Check cache first
        await self._refresh_cache_if_needed()
        
        # Filter from cache
        try:
            s_d = datetime.strptime(start_date, "%Y%m%d").date()
            e_d = datetime.strptime(end_date, "%Y%m%d").date()
            return [d for d in self._trading_dates if s_d <= d <= e_d]
        except Exception:
            pass

        # If cache failed or empty, fallback to providers
        # Prefer AkShare for better holiday handling usually, but Baostock also works
        try:
            dates = await self.ak_provider.get_trading_dates(start_date, end_date)
            if dates: return dates
            
            # Fallback
            dates = await self.bs_provider.get_trading_dates(start_date, end_date)
            if dates: return dates
            
        except Exception as e:
            logger.error(f"DataProvider trading dates error: {e}")
            
        return []

    async def _refresh_cache_if_needed(self):
        """Refresh trading dates cache if stale (> 6 hours)."""
        import time
        now = time.time()
        
        if self._trading_dates and self._cache_time and (now - self._cache_time < 21600):
            return

        try:
            # Fetch last 365 days + 30 days future to cover immediate needs
            # Or just fetch all if efficiently possible. AkShare usually fetches all.
            # Let's ask AkShare for a wide range.
            
            end = datetime.now() + timedelta(days=30)
            start = end - timedelta(days=365*2) # 2 years
            
            s_str = start.strftime("%Y%m%d")
            e_str = end.strftime("%Y%m%d")
            
            dates = await self.ak_provider.get_trading_dates(s_str, e_str)
            if dates:
                self._trading_dates = dates
                self._cache_time = now
                logger.info(f"Refreshed trading dates cache: {len(dates)} days")
        except Exception as e:
            logger.warn(f"Failed to refresh trading dates cache: {e}")

    async def _should_skip_request(self, start_date: str, end_date: str) -> bool:
        """Check if request can be skipped (no trading days in range)."""
        await self._refresh_cache_if_needed()
        
        if not self._trading_dates:
            return False # Conservative: don't skip if cache empty
            
        try:
            s_d = datetime.strptime(start_date, "%Y%m%d").date()
            e_d = datetime.strptime(end_date, "%Y%m%d").date()
            
            # Use binary search or simple iteration (dates are sorted)
            # Find any date d where s_d <= d <= e_d
            # Since _trading_dates is sorted:
            import bisect
            # Find insertion point for s_d
            idx = bisect.bisect_left(self._trading_dates, s_d)
            
            # Check if this index is within bounds and <= e_d
            if idx < len(self._trading_dates) and self._trading_dates[idx] <= e_d:
                return False # Found a trading day in range
            
            return True # No trading day found in range
            
        except Exception:
            return False

data_provider = DataProviderService()
