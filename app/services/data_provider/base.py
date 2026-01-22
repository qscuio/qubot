from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from datetime import date

class BaseDataProvider(ABC):
    """Abstract base class for stock data providers."""
    
    @abstractmethod
    def get_name(self) -> str:
        """Get provider name."""
        pass
        
    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize provider (e.g. login)."""
        pass
        
    @abstractmethod
    async def shutdown(self):
        """Shutdown provider (e.g. logout)."""
        pass
        
    @abstractmethod
    async def get_stock_list(self) -> List[Dict[str, str]]:
        """Fetch list of all stocks.
        
        Returns:
            List of dicts with 'code' and 'name'.
        """
        pass
        
    @abstractmethod
    async def get_daily_bars(
        self, 
        code: str, 
        start_date: str, 
        end_date: str,
        adjust: str = "qfq"
    ) -> List[Dict[str, Any]]:
        """Fetch daily K-line data.
        
        Args:
            code: Stock code (e.g. '600519')
            start_date: 'YYYYMMDD' or 'YYYY-MM-DD' depending on provider needs, 
                        but let's standardize input as 'YYYYMMDD' for internal consistency?
                        Actually, 'YYYYMMDD' is standard for AkShare, YYYY-MM-DD for Baostock.
                        Let's standardize on 'YYYYMMDD' as input and implementation handles conversion.
            end_date: 'YYYYMMDD'
            adjust: 'qfq' (default), 'hfq', or 'none'
            
        Returns:
            List of dicts with standardized keys:
            - date: datetime.date
            - open, high, low, close: float
            - volume: int (shares)
            - turnover: float (amount)
            - change_pct: float (optional)
            - amplitude: float (optional)
            - turnover_rate: float (optional)
        """
        pass

    @abstractmethod
    async def get_trading_dates(self, start_date: str, end_date: str) -> List[date]:
        """Get list of trading dates between range (inclusive).
        
        Args:
            start_date: YYYYMMDD
            end_date: YYYYMMDD
            
        Returns:
            List of datetime.date objects, sorted.
        """
        pass
