from typing import List, Dict, Any, Optional
import asyncio
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

    async def initialize(self):
        """Initialize all providers."""
        for p in self.providers:
            await p.initialize()
            logger.info(f"Initialized provider: {p.get_name()}")

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
        """Fetch daily bars with fallback logic."""
        
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

data_provider = DataProviderService()
