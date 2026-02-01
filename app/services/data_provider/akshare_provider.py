import asyncio
import datetime
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
        
        # Circuit breaker handled by DataProviderService
        
    def get_name(self) -> str:
        return "akshare"
    
    def is_available(self) -> bool:
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
        return
        
    def _record_failure(self):
        return

    async def initialize(self) -> bool:
        """Lazy load libraries and configure proxy."""
        try:
            # Configure proxy from settings (must be done before importing akshare)
            from app.core.config import settings
            import os
            if settings.DATA_PROXY:
                proxy_url = settings.DATA_PROXY
                os.environ['HTTP_PROXY'] = proxy_url
                os.environ['HTTPS_PROXY'] = proxy_url
                logger.info(f"AkShare proxy configured: {proxy_url.split('@')[-1] if '@' in proxy_url else proxy_url}")
            
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

    async def get_all_spot_data(self) -> Optional['pandas.DataFrame']:
        """Get full spot data for batch updates."""
        if not self._ak:
            if not await self.initialize(): return None
        
        if not self.is_available():
            logger.warn("Circuit breaker open, skipping batch update")
            return None
            
        try:
            await self._rate_limit()
            # 10m timeout for large request
            df = await asyncio.wait_for(
                asyncio.to_thread(self._ak.stock_zh_a_spot_em),
                timeout=600.0
            )
            
            if df is None or df.empty:
                return None
                
            self._record_success()
            return df
            
        except Exception as e:
            self._record_failure()
            logger.error(f"Failed to get all spot data: {e}")
            return None

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

    async def get_quotes(self, codes: List[str]) -> Dict[str, Dict[str, Any]]:
        if not self._ak:
            if not await self.initialize(): return {}
        
        if not self.is_available():
            return {}
            
        try:
            await self._rate_limit()
            # Fetch all spot data (one request)
            df = await asyncio.to_thread(self._ak.stock_zh_a_spot_em)
            if df is None or df.empty:
                return {}
            
            self._record_success()
            
            # Map results
            result = {}
            # effective codes set for faster lookup
            target_codes = set(codes) if codes else None
            
            for _, row in df.iterrows():
                code = str(row['代码'])
                
                # If codes provided, filter
                if target_codes and code not in target_codes:
                    continue
                    
                try:
                    price = float(row.get('最新价', 0) or 0)
                    change = float(row.get('涨跌幅', 0) or 0)
                    volume = float(row.get('成交量', 0) or 0)
                    turnover = float(row.get('成交额', 0) or 0)
                    name = str(row.get('名称', ''))
                    
                    result[code] = {
                        'name': name,
                        'price': price,
                        'change_pct': change,
                        'volume': volume,
                        'turnover': turnover,
                        'time': datetime.datetime.now().strftime("%H:%M:%S") # Spot API doesn't always have time
                    }
                except:
                    continue
                    
            return result
            
        except Exception as e:
            self._record_failure()
            logger.error(f"Failed to get quotes (AkShare): {e}")
            return {}

    async def get_sector_list(self, sector_type: str = "industry") -> List[Dict[str, Any]]:
        if not self._ak:
            if not await self.initialize():
                return []

        if not self.is_available():
            return []

        sector_type = (sector_type or "industry").lower()
        if sector_type == "industry":
            fetcher = getattr(self._ak, "stock_board_industry_name_em", None)
        elif sector_type == "concept":
            fetcher = getattr(self._ak, "stock_board_concept_name_em", None)
        else:
            return []

        if not callable(fetcher):
            return []

        try:
            await self._rate_limit()
            df = await asyncio.to_thread(fetcher)
            if df is None or df.empty:
                return []

            self._record_success()

            sectors = []
            for _, row in df.iterrows():
                sectors.append({
                    "code": str(row.get("板块代码", "")),
                    "name": str(row.get("板块名称", "")),
                    "type": sector_type,
                    "change_pct": float(row.get("涨跌幅", 0) or 0),
                    "close_price": float(row.get("最新价", 0) or 0),
                    "turnover": float(row.get("成交额", 0) or 0) / 100000000,
                    "leading_stock": str(row.get("领涨股票", "") or ""),
                    "leading_stock_pct": float(row.get("领涨股票-涨跌幅", 0) or 0),
                    "up_count": int(row.get("上涨家数", 0) or 0),
                    "down_count": int(row.get("下跌家数", 0) or 0),
                })
            return sectors
        except Exception as e:
            self._record_failure()
            logger.error(f"Failed to get sector list (AkShare/{sector_type}): {e}")
            return []

    async def get_sector_constituents(
        self,
        sector_code: str,
        sector_name: Optional[str],
        sector_type: str = "industry"
    ) -> List[Dict[str, Any]]:
        if not self._ak:
            if not await self.initialize():
                return []

        if not self.is_available():
            return []

        sector_type = (sector_type or "industry").lower()
        if not sector_name:
            return []

        if sector_type == "industry":
            fetcher = getattr(self._ak, "stock_board_industry_cons_em", None)
        elif sector_type == "concept":
            fetcher = getattr(self._ak, "stock_board_concept_cons_em", None)
        else:
            return []

        if not callable(fetcher):
            return []

        try:
            await self._rate_limit()
            df = await asyncio.to_thread(fetcher, symbol=sector_name)
            if df is None or df.empty:
                return []

            self._record_success()

            code_col = None
            name_col = None
            change_col = None
            for c in ("代码", "股票代码", "证券代码", "成分股代码"):
                if c in df.columns:
                    code_col = c
                    break
            for c in ("名称", "股票名称", "证券简称", "成分股名称"):
                if c in df.columns:
                    name_col = c
                    break
            for c in ("涨跌幅", "涨幅", "涨跌幅(%)"):
                if c in df.columns:
                    change_col = c
                    break

            if not code_col:
                return []

            stocks = []
            for _, row in df.iterrows():
                code_raw = str(row.get(code_col, "")).strip()
                if not code_raw:
                    continue
                code = code_raw.zfill(6)
                name = str(row.get(name_col, code)).strip() if name_col else code
                change_val = row.get(change_col) if change_col else None
                try:
                    change_pct = float(change_val) if change_val is not None else 0.0
                except Exception:
                    change_pct = 0.0
                stocks.append({
                    "code": code,
                    "name": name or code,
                    "change_pct": change_pct,
                })

            return stocks
        except Exception as e:
            self._record_failure()
            logger.warn(f"Failed to get sector constituents (AkShare/{sector_type}): {e}")
            return []
