from typing import List, Dict, Any, Optional
import asyncio
import time
from datetime import datetime, timedelta
from app.core.logger import Logger
from app.services.data_provider.base import BaseDataProvider
from app.services.data_provider.akshare_provider import AkShareProvider
from app.services.data_provider.baostock_provider import BaostockProvider
from app.services.data_provider.http_crawler_provider import HttpCrawlerProvider

logger = Logger("DataProvider")

class DataProviderService:
    """Facade for accessing stock data from multiple providers."""
    
    def __init__(self):
        self.providers: List[BaseDataProvider] = []
        # Primary provider
        self.ak_provider = AkShareProvider()
        # Secondary provider
        self.bs_provider = BaostockProvider()
        # Fallback/Primary Crawler
        self.crawler_provider = HttpCrawlerProvider()
        
        # Register base order: AkShare -> BaoStock -> Crawler
        self.providers = [self.ak_provider, self.bs_provider, self.crawler_provider]
        
        # Cache for trading dates
        self._trading_dates = []
        self._cache_time = None

        # Provider circuit breaker (for providers without internal protection)
        self._provider_failures = {}
        self._provider_open_until = {}
        self._failure_threshold = 2  # Open circuit after N failures
        self._circuit_timeout = 1800  # Seconds to keep circuit open (30m)

        # Sticky preferred provider (1 day)
        self._preferred_provider_name: Optional[str] = None
        self._preferred_until = 0.0
        self._preferred_ttl = 86400

    def _provider_is_available(self, provider: BaseDataProvider) -> bool:
        name = provider.get_name()
        now = time.time()
        if self._provider_open_until.get(name, 0) > now:
            return False
        is_available = getattr(provider, "is_available", None)
        if callable(is_available) and not is_available():
            return False
        return True

    def _record_provider_success(self, provider: BaseDataProvider):
        name = provider.get_name()
        self._provider_failures[name] = 0
        if name in self._provider_open_until:
            self._provider_open_until[name] = 0

    def _record_provider_failure(self, provider: BaseDataProvider):
        name = provider.get_name()
        count = self._provider_failures.get(name, 0) + 1
        self._provider_failures[name] = count
        if count >= self._failure_threshold:
            now = time.time()
            self._provider_open_until[name] = now + self._circuit_timeout
            self._provider_failures[name] = 0
            logger.warn(f"Circuit breaker OPEN for {name} ({self._circuit_timeout}s)")

    def _set_preferred_provider(self, provider: BaseDataProvider):
        self._preferred_provider_name = provider.get_name()
        self._preferred_until = time.time() + self._preferred_ttl

    def _get_ordered_providers(self) -> List[BaseDataProvider]:
        if not self._preferred_provider_name:
            return self.providers

        now = time.time()
        if now >= self._preferred_until:
            return self.providers

        preferred = None
        for p in self.providers:
            if p.get_name() == self._preferred_provider_name:
                preferred = p
                break

        if preferred and self._provider_is_available(preferred):
            return [preferred] + [p for p in self.providers if p is not preferred]

        return self.providers

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
        """Fetch stock list from providers with fallback."""
        for provider in self._get_ordered_providers():
            if not self._provider_is_available(provider):
                continue
            try:
                data = await provider.get_stock_list()
                if data:
                    self._record_provider_success(provider)
                    self._set_preferred_provider(provider)
                    logger.info(f"Fetched {len(data)} stocks from {provider.get_name()}")
                    return data
                self._record_provider_failure(provider)
            except Exception as e:
                self._record_provider_failure(provider)
                logger.warn(f"Failed to fetch stock list from {provider.get_name()}: {e}")
        return []

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
        
        for provider in self._get_ordered_providers():
            if not self._provider_is_available(provider):
                continue
            try:
                data = await provider.get_daily_bars(code, start_date, end_date, adjust)
                if data:
                    # Log source if not primary
                    if provider.get_name() != self.providers[0].get_name():
                        logger.info(f"Fetched {len(data)} records for {code} from {provider.get_name()}")
                    self._record_provider_success(provider)
                    self._set_preferred_provider(provider)
                    return data
                # Treat empty result as failure for this provider
                self._record_provider_failure(provider)
            except Exception as e:
                self._record_provider_failure(provider)
                errors.append(f"{provider.get_name()}: {e}")
        
        if errors:
            logger.debug(f"Failed to fetch data for {code} from all providers. Errors: {errors}")
            
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

        # Fallback to providers
        for provider in self._get_ordered_providers():
            if not self._provider_is_available(provider):
                continue
            try:
                dates = await provider.get_trading_dates(start_date, end_date)
                if dates:
                    self._record_provider_success(provider)
                    self._set_preferred_provider(provider)
                    return dates
            except Exception as e:
                self._record_provider_failure(provider)
                logger.warn(f"Failed to get trading dates from {provider.get_name()}: {e}")
            
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

    async def get_quotes(self, codes: List[str]) -> Dict[str, Dict[str, Any]]:
        """Fetch real-time quotes with fallback."""
        if not codes:
            return {}
        errors = []
        for provider in self._get_ordered_providers():
            if not self._provider_is_available(provider):
                continue
            try:
                quotes = await provider.get_quotes(codes)
                if quotes:
                    self._record_provider_success(provider)
                    self._set_preferred_provider(provider)
                    return quotes
                self._record_provider_failure(provider)
            except Exception as e:
                self._record_provider_failure(provider)
                errors.append(f"{provider.get_name()}: {e}")
                
        if errors:
            logger.warn(f"Failed to get quotes from all providers: {errors}")
            
        return {}

    async def get_all_spot_data(self):
        """Fetch full market spot data with fallback (provider optional)."""
        errors = []
        for provider in self._get_ordered_providers():
            if not self._provider_is_available(provider):
                continue
            getter = getattr(provider, "get_all_spot_data", None)
            if not callable(getter):
                continue
            try:
                data = await getter()
                if data is not None and not getattr(data, "empty", False):
                    self._record_provider_success(provider)
                    self._set_preferred_provider(provider)
                    return data
                self._record_provider_failure(provider)
            except Exception as e:
                self._record_provider_failure(provider)
                errors.append(f"{provider.get_name()}: {e}")

        if errors:
            logger.warn(f"Failed to get all spot data from all providers: {errors}")
        return None

    async def get_sector_list(self, sector_type: str = "industry") -> List[Dict[str, Any]]:
        """Fetch sector list with fallback."""
        sector_type = (sector_type or "industry").lower()
        if sector_type not in ("industry", "concept"):
            return []

        errors = []
        for provider in self._get_ordered_providers():
            if not self._provider_is_available(provider):
                continue
            try:
                data = await provider.get_sector_list(sector_type)
                if data:
                    self._record_provider_success(provider)
                    self._set_preferred_provider(provider)
                    return data
                self._record_provider_failure(provider)
            except Exception as e:
                self._record_provider_failure(provider)
                errors.append(f"{provider.get_name()}: {e}")

        if errors:
            logger.warn(f"Failed to get sectors ({sector_type}) from all providers: {errors}")
        return []

    async def get_sector_constituents(
        self,
        sector_code: str,
        sector_name: Optional[str],
        sector_type: str = "industry"
    ) -> List[Dict[str, Any]]:
        """Fetch sector constituents with fallback."""
        sector_type = (sector_type or "industry").lower()
        if sector_type not in ("industry", "concept"):
            return []

        errors = []
        for provider in self._get_ordered_providers():
            if not self._provider_is_available(provider):
                continue
            try:
                data = await provider.get_sector_constituents(sector_code, sector_name, sector_type)
                if data:
                    self._record_provider_success(provider)
                    self._set_preferred_provider(provider)
                    return data
                self._record_provider_failure(provider)
            except Exception as e:
                self._record_provider_failure(provider)
                errors.append(f"{provider.get_name()}: {e}")

        if errors:
            logger.warn(f"Failed to get sector constituents from all providers: {errors}")
        return []

data_provider = DataProviderService()
