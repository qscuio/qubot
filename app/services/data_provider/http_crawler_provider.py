import asyncio
import requests
import pandas as pd
import datetime
import math
from typing import List, Dict, Any, Optional
from io import StringIO
from app.core.logger import Logger
from app.services.data_provider.base import BaseDataProvider

logger = Logger("HttpCrawlerProvider")

class HttpCrawlerProvider(BaseDataProvider):
    """
    Direct HTTP Crawler Provider to bypass Akshare blocking.
    Uses 'requests' with asyncio.to_thread for async compatibility.
    
    Sources:
    - History: Netease (quotes.money.163.com)
    - Real-time: Sina (hq.sinajs.cn)
    - List: EastMoney (push2.eastmoney.com)
    """
    
    def __init__(self):
        self._headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
    def get_name(self) -> str:
        return "http_crawler"

    async def initialize(self) -> bool:
        return True

    async def shutdown(self):
        pass
        
    def _get_sync(self, url, params=None, headers=None, encoding=None):
        """Sync get helper."""
        if not headers: headers = self._headers
        else: headers.update(self._headers)
        
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            if resp.status_code != 200:
                logger.warn(f"HTTP {resp.status_code} for {resp.url}")
                return None
            if encoding:
                resp.encoding = encoding
            return resp
        except Exception as e:
            logger.error(f"HTTP Request failed: {e}")
            return None

    def _safe_float(self, value, default=0.0) -> float:
        try:
            if value in (None, "-", ""):
                return default
            return float(value)
        except Exception:
            return default

    def _safe_int(self, value, default=0) -> int:
        try:
            if value in (None, "-", ""):
                return default
            return int(float(value))
        except Exception:
            return default

    async def get_stock_list(self) -> List[Dict[str, str]]:
        """Fetch stock list from EastMoney."""
        
        # EastMoney API for all A-shares
        url = "http://82.push2.eastmoney.com/api/qt/clist/get"
        page_size = 100
        params = {
            "pn": "1",
            "pz": str(page_size),
            "po": "1",
            "np": "1",
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": "2",
            "invt": "2",
            "fid": "f3",
            "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23,m:0 t:81 s:2048",
            "fields": "f12,f14", # f12=code, f14=name
            "_": str(int(datetime.datetime.now().timestamp()))
        }
        
        try:
            results = []
            total_pages = 1
            page = 1

            while page <= total_pages:
                params["pn"] = str(page)
                resp = await asyncio.to_thread(self._get_sync, url, params)
                if not resp:
                    break

                data = resp.json()
                diff = data.get("data", {}).get("diff", [])
                if page == 1:
                    total = int(data.get("data", {}).get("total") or 0)
                    if total > 0:
                        total_pages = max(1, math.ceil(total / page_size))

                if not diff:
                    break

                for item in diff:
                    code = str(item.get('f12'))
                    name = str(item.get('f14'))
                    # Basic filter for A-shares
                    if code.startswith(('0', '3', '6', '4', '8')):
                        results.append({"code": code, "name": name})

                page += 1

            logger.info(f"Crawled {len(results)} stocks from EastMoney")
            return results
        except Exception as e:
            logger.error(f"Failed to crawl stock list: {e}")
            return []

    async def get_daily_bars(
        self, 
        code: str, 
        start_date: str, 
        end_date: str,
        adjust: str = "qfq"
    ) -> List[Dict[str, Any]]:
        """Fetch history from Tencent (gtimg).
        
        Tencent code format: sh600000, sz000001
        """
        
        try:
            prefix = "sh" if code.startswith("6") else "sz"
            symbol = f"{prefix}{code}"
            
            # Tencent API: param=symbol,scale,start,end,limit,adjust
            # format: sh600519,day,start_date,end_date,320,qfq
            # Actually simpler format often used:
            # http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh600519,day,2021-01-01,2021-12-31,1000,qfq
            
            # Convert YYYYMMDD to YYYY-MM-DD
            s_fmt = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}"
            e_fmt = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"
            
            # Calculate rough limit based on days
            d1 = datetime.datetime.strptime(s_fmt, "%Y-%m-%d")
            d2 = datetime.datetime.strptime(e_fmt, "%Y-%m-%d")
            days = (d2 - d1).days + 10 # Buffer
            limit = min(max(days, 640), 10000) # Ensure at least 640, max 10000
            
            url = "http://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
            params = {
                "param": f"{symbol},day,{s_fmt},{e_fmt},{limit},{adjust}"
            }
            
            resp = await asyncio.to_thread(self._get_sync, url, params)
            if not resp: return []
            
            data = resp.json()
            if not data or 'data' not in data or symbol not in data['data']:
                return []
                
            # Key might be 'qfqday' depending on adjust, or just 'day'
            key = f"{adjust}day" if adjust in ['qfq', 'hfq'] else "day"
            
            if key not in data['data'][symbol]:
                 # Sometimes if no adjust data, it falls back or returns 'day'
                 key = 'day'
                 
            raw_list = data['data'][symbol].get(key, [])
            if not raw_list:
                return []
                
            results = []
            for item in raw_list:
                # Format: [date, open, close, high, low, volume, ...]
                # Date is YYYY-MM-DD
                try:
                    d_str = item[0]
                    # Filter by date range (API sometimes gives more)
                    d_flat = d_str.replace("-", "")
                    if d_flat < start_date or d_flat > end_date:
                        continue
                        
                    date_val = datetime.datetime.strptime(d_str, "%Y-%m-%d").date()
                    
                    record = {
                        "date": date_val,
                        "open": float(item[1]),
                        "close": float(item[2]),
                        "high": float(item[3]),
                        "low": float(item[4]),
                        "volume": float(item[5]),
                        # Tencent doesn't always give turnover/turnover_rate in this endpoint
                        # We might need to approximate or leave 0
                        "turnover": 0.0, 
                        "change_pct": 0.0, # Calculate later if needed
                        "change_amt": 0.0,
                        "turnover_rate": 0.0
                    }
                    
                    # Some items have more fields? 
                    # usually: date, open, close, high, low, vol, info, info...
                    
                    results.append(record)
                except:
                    continue
            
            # Sorted by default? usually yes.
            return results
            
        except Exception as e:
            logger.error(f"Failed to crawl history for {code}: {e}")
            return []

    async def get_trading_dates(self, start_date: str, end_date: str) -> List[datetime.date]:
        """Get trading dates using SH Index."""
        try:
            url = "http://quotes.money.163.com/service/chddata.html"
            params = {
                "code": "0000001", 
                "start": start_date,
                "end": end_date,
                "fields": "TCLOSE"
            }
            
            resp = await asyncio.to_thread(self._get_sync, url, params)
            if not resp: return []
            
            csv_str = resp.content.decode('gbk', errors='ignore')
            df = pd.read_csv(StringIO(csv_str))
            
            if '日期' not in df.columns: return []
                
            dates = []
            for _, row in df.iterrows():
                try:
                    d = datetime.datetime.strptime(str(row['日期']), "%Y-%m-%d").date()
                    dates.append(d)
                except:
                    pass
            
            dates.sort()
            return dates
        except Exception as e:
            logger.warn(f"Failed to fetch trading dates from crawler: {e}")
            return []
            
    async def get_quotes(self, codes: List[str]) -> Dict[str, Dict[str, Any]]:
        """Fetch spot data from Sina."""
        sina_codes = []
        mapping = {}
        
        for code in codes:
            prefix = "sh" if code.startswith("6") else "sz"
            sc = f"{prefix}{code}"
            sina_codes.append(sc)
            mapping[sc] = code
            
        results = {}
        chunk_size = 80
        
        for i in range(0, len(sina_codes), chunk_size):
            chunk = sina_codes[i:i+chunk_size]
            url = f"http://hq.sinajs.cn/list={','.join(chunk)}"
            
            try:
                resp = await asyncio.to_thread(self._get_sync, url, headers={"Referer": "http://finance.sina.com.cn/"}, encoding='gbk')
                if not resp: continue
                text = resp.text
                    
                lines = text.splitlines()
                for line in lines:
                    try:
                        if '="' not in line: continue
                        
                        lhs, rhs = line.split('="')
                        sc = lhs.split('hq_str_')[-1]
                        data_str = rhs.strip('";')
                        
                        if not data_str: continue
                        
                        parts = data_str.split(',')
                        if len(parts) < 30: continue
                        
                        name = parts[0]
                        open_p = float(parts[1])
                        pre_close = float(parts[2])
                        current = float(parts[3])
                        # ... (rest same as before)
                        volume = float(parts[8])
                        turnover = float(parts[9])
                        
                        if pre_close > 0:
                            change_pct = ((current - pre_close) / pre_close) * 100
                        else:
                            change_pct = 0.0
                            
                        original_code = mapping.get(sc)
                        if not original_code: continue
                        
                        results[original_code] = {
                            'name': name,
                            'price': current,
                            'change_pct': change_pct,
                            'volume': volume,
                            'turnover': turnover,
                            'time': parts[31]
                        }
                    except Exception:
                        continue
            except Exception as e:
                logger.warn(f"Sina spot fetch failed for chunk: {e}")
                
        return results

    async def get_sector_list(self, sector_type: str = "industry") -> List[Dict[str, Any]]:
        """Fetch sector list from EastMoney with best-effort fields."""
        sector_type = (sector_type or "industry").lower()
        if sector_type not in ("industry", "concept"):
            return []

        fs_candidates = {
            "industry": ["m:90+t:2", "m:90+t:2+f:!50"],
            "concept": ["m:90+t:3", "m:90+t:3+f:!50"],
        }

        url = "http://82.push2.eastmoney.com/api/qt/clist/get"
        fields = "f12,f14,f2,f3,f6,f104,f105,f128,f140"

        for fs in fs_candidates.get(sector_type, []):
            params = {
                "pn": "1",
                "pz": "5000",
                "po": "1",
                "np": "1",
                "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                "fltt": "2",
                "invt": "2",
                "fid": "f3",
                "fs": fs,
                "fields": fields,
                "_": str(int(datetime.datetime.now().timestamp()))
            }

            try:
                resp = await asyncio.to_thread(self._get_sync, url, params)
                if not resp:
                    continue
                data = resp.json()
            except Exception as e:
                logger.warn(f"Sector list fetch failed ({sector_type}): {e}")
                continue

            diff = data.get("data", {}).get("diff", [])
            if not diff:
                continue

            results = []
            for item in diff:
                code = str(item.get("f12", "")).strip()
                name = str(item.get("f14", "")).strip()
                if not code or not name:
                    continue

                turnover = self._safe_float(item.get("f6", 0))
                results.append({
                    "code": code,
                    "name": name,
                    "type": sector_type,
                    "change_pct": self._safe_float(item.get("f3", 0)),
                    "close_price": self._safe_float(item.get("f2", 0)),
                    "turnover": turnover / 100000000 if turnover else 0.0,
                    "leading_stock": str(item.get("f128", "") or ""),
                    "leading_stock_pct": self._safe_float(item.get("f140", 0)),
                    "up_count": self._safe_int(item.get("f104", 0)),
                    "down_count": self._safe_int(item.get("f105", 0)),
                })

            if results:
                return results

        return []

    async def get_sector_constituents(
        self,
        sector_code: str,
        sector_name: Optional[str],
        sector_type: str = "industry"
    ) -> List[Dict[str, Any]]:
        """Fetch sector constituents from EastMoney using board code."""
        _ = sector_type  # EastMoney uses board code for both
        if not sector_code:
            return []

        code = str(sector_code).strip()
        if not code:
            return []

        candidates = []
        code_upper = code.upper()
        candidates.append(code_upper)
        if not code_upper.startswith("BK"):
            candidates.append(f"BK{code_upper}")

        seen = set()
        fs_candidates = []
        for c in candidates:
            if c in seen:
                continue
            seen.add(c)
            fs_candidates.append(f"b:{c}")
            fs_candidates.append(f"b:{c}+f:!50")

        url = "http://82.push2.eastmoney.com/api/qt/clist/get"
        fields = "f12,f14,f2,f3,f5,f6"

        for fs in fs_candidates:
            params = {
                "pn": "1",
                "pz": "10000",
                "po": "1",
                "np": "1",
                "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                "fltt": "2",
                "invt": "2",
                "fid": "f3",
                "fs": fs,
                "fields": fields,
                "_": str(int(datetime.datetime.now().timestamp()))
            }

            try:
                resp = await asyncio.to_thread(self._get_sync, url, params)
                if not resp:
                    continue
                data = resp.json()
            except Exception as e:
                logger.warn(f"Sector constituents fetch failed ({fs}): {e}")
                continue

            diff = data.get("data", {}).get("diff", [])
            if not diff:
                continue

            results = []
            for item in diff:
                raw_code = str(item.get("f12", "")).strip()
                if not raw_code:
                    continue
                code_val = raw_code.zfill(6)
                name = str(item.get("f14", "")).strip() or code_val
                change_pct = self._safe_float(item.get("f3", 0))
                results.append({
                    "code": code_val,
                    "name": name,
                    "change_pct": change_pct,
                })

            if results:
                return results

        return []

    async def get_all_spot_data(self) -> Optional[pd.DataFrame]:
        """Compatible with get_all_spot_data using EastMoney."""
        
        url = "http://82.push2.eastmoney.com/api/qt/clist/get"
        page_size = 100
        params = {
            "pn": "1",
            "pz": str(page_size),
            "po": "1",
            "np": "1",
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": "2",
            "invt": "2",
            "fid": "f3",
            "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23,m:0 t:81 s:2048",
            "fields": "f12,f14,f2,f3,f17,f15,f16,f5,f6,f8,f7",
            "_": str(int(datetime.datetime.now().timestamp()))
        }
        
        try:
            raw_data = []
            total_pages = 1
            page = 1

            while page <= total_pages:
                params["pn"] = str(page)
                resp = await asyncio.to_thread(self._get_sync, url, params)
                if not resp:
                    break
                data = resp.json()

                diff = data.get("data", {}).get("diff", [])
                if page == 1:
                    total = int(data.get("data", {}).get("total") or 0)
                    if total > 0:
                        total_pages = max(1, math.ceil(total / page_size))

                if not diff:
                    break

                for item in diff:
                    try:
                        raw_data.append({
                            '代码': str(item['f12']),
                            '名称': str(item['f14']),
                            '最新价': item['f2'],
                            '涨跌幅': item['f3'],
                            '今开': item['f17'],
                            '最高': item['f15'],
                            '最低': item['f16'],
                            '成交量': item['f5'],
                            '成交额': item['f6'],
                            '换手率': item['f8'],
                            '振幅': item['f7']
                        })
                    except:
                        continue

                page += 1
                    
            if not raw_data:
                return None
            
            df = pd.DataFrame(raw_data)
            df.replace('-', 0, inplace=True)
            return df
            
        except Exception as e:
            logger.error(f"Failed to fetch all spot data (crawler): {e}")
            return None
