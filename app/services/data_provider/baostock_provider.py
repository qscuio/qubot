import asyncio
import datetime
from typing import List, Dict, Any, Optional
from app.core.logger import Logger
from app.services.data_provider.base import BaseDataProvider

logger = Logger("BaostockProvider")

class BaostockProvider(BaseDataProvider):
    def __init__(self):
        self._bs = None
        self.is_logged_in = False
        
    def get_name(self) -> str:
        return "baostock"

    async def initialize(self) -> bool:
        """Lazy load and login."""
        if self._bs is None:
            try:
                import baostock as bs
                self._bs = bs
            except ImportError:
                logger.error("Baostock not installed.")
                return False
                
        if not self.is_logged_in:
            try:
                lg = await asyncio.to_thread(self._bs.login)
                if lg.error_code == '0':
                    self.is_logged_in = True
                    return True
                else:
                    logger.error(f"Baostock login failed: {lg.error_msg}")
                    return False
            except Exception as e:
                logger.error(f"Baostock login error: {e}")
                return False
        return True

    async def shutdown(self):
        if self._bs and self.is_logged_in:
            try:
                await asyncio.to_thread(self._bs.logout)
                self.is_logged_in = False
            except Exception:
                pass

    async def get_stock_list(self) -> List[Dict[str, str]]:
        if not await self.initialize():
            return []

        # Baostock stock list is date-based; try recent days to handle weekends/holidays.
        today = datetime.datetime.now().date()

        for back in range(0, 7):
            date_str = (today - datetime.timedelta(days=back)).strftime("%Y-%m-%d")
            try:
                rs = await asyncio.to_thread(self._bs.query_all_stock, date_str)
                if rs.error_code != '0':
                    logger.warn(f"Baostock query_all_stock failed ({date_str}): {rs.error_msg}")
                    continue

                results: List[Dict[str, str]] = []
                while rs.next():
                    row = rs.get_row_data()
                    if not row:
                        continue

                    raw_code = (row[0] if len(row) > 0 else "").strip()
                    name = (row[2] if len(row) > 2 else raw_code).strip()
                    if not raw_code:
                        continue

                    code = raw_code.split(".")[-1].strip()
                    if not code:
                        continue

                    code_val = code.zfill(6) if code.isdigit() else code
                    if code_val.startswith(("0", "3", "6", "4", "8")):
                        results.append({"code": code_val, "name": name or code_val})

                if results:
                    logger.info(f"Fetched {len(results)} stocks from baostock for {date_str}")
                    return results
            except Exception as e:
                logger.warn(f"Baostock query_all_stock error ({date_str}): {e}")

        return []

    async def get_daily_bars(
        self, 
        code: str, 
        start_date: str, 
        end_date: str,
        adjust: str = "qfq"
    ) -> List[Dict[str, Any]]:
        # start_date/end_date in YYYYMMDD
        if not await self.initialize(): return []

        # Convert date to YYYY-MM-DD
        s_date = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}"
        e_date = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"
        
        # Convert code
        bs_code = code
        if not (code.startswith("sh.") or code.startswith("sz.")):
             if code.startswith("6"):
                 bs_code = f"sh.{code}"
             elif code.startswith("0") or code.startswith("3"):
                 bs_code = f"sz.{code}"
             elif code.startswith(("4", "8")):
                 bs_code = f"bj.{code}"

        # Adjust flag: 1: hfq, 2: qfq, 3: none
        adj = "3"
        if adjust == "qfq": adj = "2"
        elif adjust == "hfq": adj = "1"

        try:
            fields = "date,open,high,low,close,volume,amount,adjustflag,turn,pctChg"
            rs = await asyncio.to_thread(
                self._bs.query_history_k_data_plus,
                bs_code,
                fields,
                start_date=s_date,
                end_date=e_date,
                frequency="d",
                adjustflag=adj
            )
            
            if rs.error_code != '0':
                return []

            results = []
            while rs.next():
                row = rs.get_row_data()
                # [date, open, high, low, close, volume, amount, adjustflag, turn, pctChg]
                try:
                    if not row[1] or row[1] == "": continue
                    
                    try:
                         d_obj = datetime.datetime.strptime(row[0], "%Y-%m-%d").date()
                    except:
                        continue
                        
                    item = {
                        "date": d_obj,
                        "open": float(row[1]),
                        "high": float(row[2]),
                        "low": float(row[3]),
                        "close": float(row[4]),
                        "volume": int(row[5]) if row[5] else 0,
                        "turnover": float(row[6]) if row[6] else 0.0,
                        # Baostock doesn't return amplitude directly in this query
                        "amplitude": 0.0, 
                        "change_pct": float(row[9]) if row[9] else 0.0,
                        # Change amt not returned directly usually?
                        "change_amt": 0.0,
                        "turnover_rate": float(row[8]) if row[8] else 0.0
                    }
                    results.append(item)
                except ValueError:
                    continue
            return results

        except Exception as e:
            logger.warn(f"Baostock fetch error for {code}: {e}")
            return []

    async def get_trading_dates(self, start_date: str, end_date: str) -> List[datetime.date]:
        if not await self.initialize(): return []
        
        s_date = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}"
        e_date = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"
        
        try:
            rs = await asyncio.to_thread(
                self._bs.query_trade_dates,
                start_date=s_date,
                end_date=e_date
            )
            
            if rs.error_code != '0':
                return []
            
            dates = []
            while rs.next():
                # calendar_date, is_trading_day
                row = rs.get_row_data()
                if row[1] == '1': # is_trading_day = 1
                    try:
                        d = datetime.datetime.strptime(row[0], "%Y-%m-%d").date()
                        dates.append(d)
                    except:
                        pass
            return dates
        except Exception as e:
            logger.error(f"Failed to get trading dates (Baostock): {e}")
            return []

    async def get_quotes(self, codes: List[str]) -> Dict[str, Dict[str, Any]]:
        """Baostock does not support real-time quotes."""
        return {}

    async def get_sector_list(self, sector_type: str = "industry") -> List[Dict[str, Any]]:
        """Baostock does not support sector lists."""
        return []

    async def get_sector_constituents(
        self,
        sector_code: str,
        sector_name: Optional[str],
        sector_type: str = "industry"
    ) -> List[Dict[str, Any]]:
        """Baostock does not support sector constituents."""
        return []
