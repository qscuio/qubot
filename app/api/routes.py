from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict
from app.api.auth import verify_api_key
from app.services.monitor import monitor_service
from app.services.rss import rss_service
from app.services.ai import ai_service
from app.core.bot import telegram_service
from app.core.logger import Logger

router = APIRouter(prefix="/api", tags=["API"])
chart_logger = Logger("ChartAPI")


# Request/Response Models
class ChatRequest(BaseModel):
    message: str
    provider: Optional[str] = None
    model: Optional[str] = None
    system_prompt: Optional[str] = ""


class ChatResponse(BaseModel):
    content: str
    provider: str
    model: Optional[str] = None


class SummarizeRequest(BaseModel):
    text: str
    max_length: Optional[int] = 200
    language: Optional[str] = "en"  # "en" or "zh"


class SubscribeRequest(BaseModel):
    url: str
    chat_id: Optional[str] = None


# Health
@router.get("/health")
async def api_health():
    return {
        "status": "ok",
        "telegram": telegram_service.connected,
        "ai_available": ai_service.is_available(),
        "monitor_running": monitor_service.is_running,
    }


# Monitor Endpoints
@router.get("/monitor/status")
async def monitor_status(user_id: str = Depends(verify_api_key)):
    return {
        "running": monitor_service.is_running,
        "sources": len(monitor_service.source_channels),
        "target": monitor_service.target_channel,
    }


@router.post("/monitor/start")
async def monitor_start(user_id: str = Depends(verify_api_key)):
    await monitor_service.start()
    return {"status": "started"}


@router.post("/monitor/stop")
async def monitor_stop(user_id: str = Depends(verify_api_key)):
    await monitor_service.stop()
    return {"status": "stopped"}


# AI Endpoints
@router.get("/ai/providers")
async def ai_providers(user_id: str = Depends(verify_api_key)):
    return {"providers": ai_service.list_providers()}


@router.get("/ai/models/{provider}")
async def ai_models(provider: str, user_id: str = Depends(verify_api_key)):
    models = await ai_service.get_models(provider)
    return {"provider": provider, "models": models}


@router.post("/ai/chat", response_model=ChatResponse)
async def ai_chat(req: ChatRequest, user_id: str = Depends(verify_api_key)):
    if not ai_service.is_available():
        raise HTTPException(status_code=503, detail="AI service not configured")
    
    response = await ai_service.generate_response(
        prompt=req.message,
        history=None,
        system_prompt=req.system_prompt or ""
    )
    
    return ChatResponse(
        content=response,
        provider=ai_service.active_provider.name if ai_service.active_provider else "unknown",
        model=None
    )


@router.post("/ai/summarize")
async def ai_summarize(req: SummarizeRequest, user_id: str = Depends(verify_api_key)):
    """Summarize text in English or Chinese."""
    if not ai_service.is_available():
        raise HTTPException(status_code=503, detail="AI service not configured")
    
    result = await ai_service.summarize(req.text, req.max_length, req.language)
    return {"summary": result, "language": req.language}

# RSS Endpoints
@router.get("/rss/subscriptions")
async def rss_list(user_id: str = Depends(verify_api_key)):
    subs = await rss_service.get_subscriptions(user_id)
    return {"subscriptions": subs}


@router.post("/rss/subscribe")
async def rss_subscribe(req: SubscribeRequest, user_id: str = Depends(verify_api_key)):
    result = await rss_service.subscribe(user_id, req.url, req.chat_id or user_id)
    return result


@router.delete("/rss/unsubscribe/{source_id}")
async def rss_unsubscribe(source_id: str, user_id: str = Depends(verify_api_key)):
    result = await rss_service.unsubscribe(user_id, source_id)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Chart Data Endpoint (for Mini App - no auth required)
# Separate router that's always included, regardless of API_ENABLED
# ─────────────────────────────────────────────────────────────────────────────

chart_router = APIRouter(prefix="/api", tags=["Chart"])

from app.api.auth import verify_api_key, verify_webapp, verify_webapp_optional

@chart_router.get("/chart/data/{code}")
async def chart_data(code: str, days: int = 60, period: str = "daily", user_id: int = Depends(verify_webapp)):
    """Get OHLCV data for stock chart Mini App (Protected).
    
    Args:
        code: Stock code (e.g., 600519)
        days: Number of periods to return
        period: 'daily', 'weekly', or 'monthly'
        user_id: Authenticated Telegram User ID
    """
    import asyncio
    from datetime import time as time_type
    from app.services.stock_history import stock_history_service
    from app.services.sector import sector_service
    from app.core.database import db
    from app.core.timezone import china_now, china_today
    
    import math
    data = []
    name = code  # Default to code if name not found
    sector_info = {}

    def _safe_float(value, default=None):
        try:
            if value is None:
                return default
            f = float(value)
        except Exception:
            return default
        return f if math.isfinite(f) else default

    def _safe_int(value, default=0):
        try:
            if value is None:
                return default
            i = int(value)
        except Exception:
            f = _safe_float(value, default=None)
            if f is None:
                return default
            try:
                i = int(f)
            except Exception:
                return default
        return i

    def _build_bar(time_value, open_v, high_v, low_v, close_v, volume_v, amplitude_v=None, turnover_v=None, volume_ratio_v=None):
        open_f = _safe_float(open_v, default=None)
        high_f = _safe_float(high_v, default=None)
        low_f = _safe_float(low_v, default=None)
        close_f = _safe_float(close_v, default=None)
        if open_f is None or high_f is None or low_f is None or close_f is None:
            return None
        return {
            "time": time_value,
            "open": open_f,
            "high": high_f,
            "low": low_f,
            "close": close_f,
            "volume": _safe_int(volume_v, default=0),
            "amplitude": _safe_float(amplitude_v, default=0.0),
            "turnover_rate": _safe_float(turnover_v, default=0.0),
            "volume_ratio": _safe_float(volume_ratio_v, default=None),
        }

    def _resample_bars(rows, period_name: str):
        if not rows:
            return []
        # rows are sorted ascending by date
        grouped = {}
        order = []
        for r in rows:
            d = r["date"]
            if period_name == "weekly":
                y, w, _ = d.isocalendar()
                key = (y, w)
            else:
                key = (d.year, d.month)
            if key not in grouped:
                grouped[key] = []
                order.append(key)
            grouped[key].append(r)

        bars = []
        for key in order:
            bucket = grouped[key]
            if not bucket:
                continue
            first = bucket[0]
            last = bucket[-1]
            high_vals = []
            low_vals = []
            for b in bucket:
                h = _safe_float(b.get("high"), default=None)
                l = _safe_float(b.get("low"), default=None)
                if h is not None:
                    high_vals.append(h)
                if l is not None:
                    low_vals.append(l)
            if not high_vals or not low_vals:
                continue
            high_v = max(high_vals)
            low_v = min(low_vals)
            open_v = first.get("open")
            close_v = last.get("close")
            volume_v = sum(_safe_int(b.get("volume"), default=0) for b in bucket)
            amplitude_v = None
            open_f = _safe_float(open_v, default=None)
            if open_f and open_f > 0:
                amplitude_v = (high_v - low_v) / open_f * 100
            bar = _build_bar(
                str(last["date"]),
                open_v,
                high_v,
                low_v,
                close_v,
                volume_v,
                amplitude_v,
                None,
                None,
            )
            if bar:
                bars.append(bar)
        return bars
    
    # Validate period
    if period not in ("daily", "weekly", "monthly"):
        period = "daily"
    
    # Try to get stock name from database first (stock_info or limit_up tables)
    if db.pool:
        try:
            # Try stock_info table first
            row = await db.pool.fetchrow("""
                SELECT name FROM stock_info WHERE code = $1 LIMIT 1
            """, code)
            if row and row['name']:
                name = row['name']
            else:
                # Fallback to stock_history (some have name stored)
                row = await db.pool.fetchrow("""
                    SELECT name FROM stock_history WHERE code = $1 AND name IS NOT NULL LIMIT 1
                """, code)
                if row and row.get('name'):
                    name = row['name']
        except Exception:
            pass  # Table might not exist, continue
    
    def _use_realtime_daily(now) -> bool:
        if now.weekday() >= 5:
            return False
        t = now.time()
        return time_type(9, 15) <= t <= time_type(15, 0)

    use_realtime = period == "daily" and _use_realtime_daily(china_now())

    try:
        if period == "daily":
            # Fetch extra days for MA calculation
            history = await stock_history_service.get_stock_history(code, days=days + 5)

            if history:
                # Calculate Volume MA5 for Volume Ratio
                # Volume Ratio = Volume / MA(Volume, 5)
                # We need to compute this manually since we have a list of dicts
                
                # Sort by date ascending for calculation
                history.sort(key=lambda x: x['date'])
                
                # Calculate 5-day volume average
                # We'll use a simple moving average
                volumes = [h['volume'] for h in history]
                vol_ma5 = []
                for i in range(len(volumes)):
                    if i < 4:
                        vol_ma5.append(None) # Not enough data
                    else:
                        # Average of last 5 days (including today)
                        avg = sum(volumes[i-4:i+1]) / 5
                        vol_ma5.append(avg)
                
                # Add volume ratio to history records
                for i, h in enumerate(history):
                    if vol_ma5[i] and vol_ma5[i] > 0:
                        h['volume_ratio'] = round(h['volume'] / vol_ma5[i], 2)
                    else:
                        h['volume_ratio'] = None

                # Slice back to requested days
                if len(history) > days:
                    history = history[-days:]

                for h in history:
                    bar = _build_bar(
                        h['date'],
                        h.get('open'),
                        h.get('high'),
                        h.get('low'),
                        h.get('close'),
                        h.get('volume'),
                        h.get('amplitude'),
                        h.get('turnover_rate'),
                        h.get('volume_ratio'),
                    )
                    if bar:
                        data.append(bar)
    except Exception:
        pass

    async def _fetch_realtime_daily() -> Optional[Dict]:
        try:
            import akshare as ak
            today = china_today()
            today_str = today.strftime("%Y%m%d")
            df = await asyncio.wait_for(
                asyncio.to_thread(
                    ak.stock_zh_a_hist,
                    symbol=code,
                    period="daily",
                    start_date=today_str,
                    end_date=today_str,
                    adjust="qfq"
                ),
                timeout=6
            )
            if df is None or df.empty:
                return None
            row = df.iloc[-1]
            row_date = str(row.get('日期', ''))[:10]
            if row_date != today.strftime("%Y-%m-%d"):
                return None
            
            # Realtime volume ratio requires past data, might be hard to get accurate here without history
            # We can try to approximate or leave None
            # Akshare realtime spot data might have volume ratio (量比)
            
            vol_ratio = None
            try:
                # Try to get spot data for volume ratio
                spot_df = await asyncio.wait_for(
                    asyncio.to_thread(ak.stock_zh_a_spot_em),
                    timeout=4
                )
                if spot_df is not None and not spot_df.empty:
                    spot_row = spot_df[spot_df['代码'] == code]
                    if not spot_row.empty:
                        # 量比 column
                        vr = spot_row.iloc[0].get('量比')
                        if vr:
                            vol_ratio = float(vr)
            except:
                pass

            return _build_bar(
                row_date,
                row.get('开盘', 0),
                row.get('最高', 0),
                row.get('最低', 0),
                row.get('收盘', 0),
                row.get('成交量', 0),
                row.get('振幅', 0),
                row.get('换手率', 0),
                vol_ratio,
            )
        except Exception:
            return None

    if period == "daily" and use_realtime:
        today_str = china_today().strftime("%Y-%m-%d")
        realtime_bar = await _fetch_realtime_daily()
        if realtime_bar:
            if data and data[-1].get("time") == today_str:
                data[-1] = realtime_bar
            else:
                data.append(realtime_bar)
            if len(data) > days:
                data = data[-days:]
    
    # Weekly/monthly: try local DB resample first
    if not data and period in ("weekly", "monthly") and db.pool:
        try:
            fetch_limit = days * (7 if period == "weekly" else 31) + 30
            rows = await db.pool.fetch("""
                SELECT date, open, high, low, close, volume, amplitude, turnover_rate
                FROM stock_history
                WHERE code = $1
                ORDER BY date DESC
                LIMIT $2
            """, code, fetch_limit)
            if rows:
                rows = list(reversed(rows))
                data = _resample_bars(rows, period)
                if len(data) > days:
                    data = data[-days:]
        except Exception:
            pass

    # Fallback or weekly/monthly: fetch from AkShare
    if not data:
        try:
            import akshare as ak
            from datetime import datetime, timedelta
            import time
            
            # For weekly/monthly, request more source data
            extra_days = 30 if period == "daily" else (days * 7 if period == "weekly" else days * 31)
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=days + extra_days)).strftime("%Y%m%d")

            chart_logger.info(
                f"chart_data fallback to akshare: code={code} period={period} "
                f"days={days} start={start_date} end={end_date}"
            )
            started = time.monotonic()
            df = await asyncio.wait_for(
                asyncio.to_thread(
                    ak.stock_zh_a_hist,
                    symbol=code,
                    period=period,
                    start_date=start_date,
                    end_date=end_date,
                    adjust="qfq"
                ),
                timeout=8
            )
            elapsed = time.monotonic() - started
            row_count = 0 if df is None else len(df)
            chart_logger.info(
                f"chart_data akshare done: code={code} period={period} "
                f"rows={row_count} elapsed={elapsed:.1f}s"
            )
            
            if df is not None and not df.empty:
                if '名称' in df.columns:
                    name = str(df['名称'].iloc[0]) if not df['名称'].isna().all() else code
                
                for _, row in df.tail(days).iterrows():
                    bar = _build_bar(
                        str(row['日期'])[:10],
                        row.get('开盘', 0),
                        row.get('最高', 0),
                        row.get('最低', 0),
                        row.get('收盘', 0),
                        row.get('成交量', 0),
                    )
                    if bar:
                        data.append(bar)
        except Exception as e:
            chart_logger.warn(f"chart_data akshare failed: code={code} period={period} error={e}")
    
    if not data:
        raise HTTPException(status_code=404, detail=f"No data for {code}")
    
    return {
        "code": code,
        "name": name,
        "period": period,
        "data": data,
        "sector_info": await sector_service.get_stock_sector_info(code),
    }


@chart_router.get("/chart/chips/{code}")
async def chart_chips(code: str, date: str = None, user_id: int = Depends(verify_webapp)):
    """Get chip distribution data for a stock.
    
    Args:
        code: Stock code (e.g., 600519)
        date: Target date (YYYY-MM-DD), defaults to today
    """
    from datetime import date as date_type
    from app.services.chip_distribution import chip_distribution_service
    
    try:
        target_date = None
        if date:
            target_date = date_type.fromisoformat(date)
        
        result = await chip_distribution_service.get_chip_distribution(code, target_date)
        
        if not result or not result.get('distribution'):
            raise HTTPException(status_code=404, detail=f"No chip data for {code}")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@chart_router.get("/chart/search")
async def chart_search(q: str, user_id: int = Depends(verify_webapp)):
    """Search stocks for chart Mini App."""
    from app.core.database import db
    
    if not q:
        return {"results": []}
    
    try:
        # Search by code or name
        # Limit to 10 results
        query = """
            SELECT code, name FROM stock_info 
            WHERE code LIKE $1 OR name LIKE $1 
            LIMIT 10
        """
        pattern = f"%{q}%"
        rows = await db.pool.fetch(query, pattern)
        
        results = [
            {"code": r['code'], "name": r['name']}
            for r in rows
        ]
        
        return {"results": results}
    except Exception as e:
        chart_logger.error(f"Search failed: {e}")
        return {"results": []}


# ─────────────────────────────────────────────────────────────────────────────
# Watchlist Endpoints (for Mini App)
# ─────────────────────────────────────────────────────────────────────────────

class WatchlistRequest(BaseModel):
    user_id: Optional[int] = None
    code: str
    name: Optional[str] = None

@chart_router.post("/chart/watchlist/add")
async def chart_watchlist_add(req: WatchlistRequest, user_id: int = Depends(verify_webapp)):
    """Add stock to watchlist from Mini App."""
    from app.services.watchlist import watchlist_service
    try:
        # Override req.user_id with authenticated user_id
        result = await watchlist_service.add_stock(user_id, req.code, req.name)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@chart_router.post("/chart/watchlist/remove")
async def chart_watchlist_remove(req: WatchlistRequest, user_id: int = Depends(verify_webapp)):
    """Remove stock from watchlist from Mini App."""
    from app.services.watchlist import watchlist_service
    try:
        success = await watchlist_service.remove_stock(user_id, req.code)
        return {"success": success}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@chart_router.get("/chart/watchlist/status")
async def chart_watchlist_status(code: str, user_id: int = Depends(verify_webapp)):
    """Check if stock is in watchlist."""
    from app.services.watchlist import watchlist_service
    try:
        watchlist = await watchlist_service.get_watchlist(user_id)
        is_in = any(item['code'] == code for item in watchlist)
        return {"in_watchlist": is_in}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@chart_router.get("/chart/watchlist/list")
async def chart_watchlist_list(user_id: int = Depends(verify_webapp)):
    """Get full watchlist for Mini App."""
    from app.services.watchlist import watchlist_service
    try:
        watchlist = await watchlist_service.get_watchlist(user_id)
        return {"watchlist": watchlist}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@chart_router.get("/chart/navigation")
async def get_chart_navigation(code: str, context: str, user_id: int = Depends(verify_webapp_optional)):
    """Get previous and next stock codes based on context."""
    from app.services.limit_up import limit_up_service
    from app.services.watchlist import watchlist_service
    from app.core.database import db
    
    stocks = []
    
    try:
        # Default navigation (by code)
        if not context or context == 'default':
            # Simple numeric sort for A-shares
            # This is a simplified implementation - ideal would be to query DB for next/prev
            return {"prev": None, "next": None}
            
        # Watchlist navigation
        if context == 'watchlist' and user_id:
            query = """
                SELECT code FROM user_watchlist 
                WHERE user_id = $1 
                ORDER BY created_at DESC
            """
            rows = await db.pool.fetch(query, user_id)
            codes = [r['code'] for r in rows]
            
            try:
                idx = codes.index(code)
                prev_code = codes[idx - 1] if idx > 0 else None
                next_code = codes[idx + 1] if idx < len(codes) - 1 else None
                return {"prev": prev_code, "next": next_code}
            except ValueError:
                return {"prev": None, "next": None}

        elif context == "limit_up":
            # Today's sealed limit ups
            data = await limit_up_service.get_realtime_limit_ups()
            stocks = [s for s in data if s.get("is_sealed", True)]
            # Sort: limit_times desc, price desc
            stocks.sort(key=lambda x: (-x.get("limit_times", 1), -x.get("close_price", 0)))
            
        elif context == "limit_up_first":
            # First board
            data = await limit_up_service.get_realtime_limit_ups()
            stocks = [s for s in data if s.get("limit_times", 1) == 1 and s.get("is_sealed", True)]
            stocks.sort(key=lambda x: -x.get("turnover_rate", 0))
            
        elif context == "limit_up_burst":
            # Burst
            data = await limit_up_service.get_realtime_limit_ups()
            stocks = [s for s in data if not s.get("is_sealed", True)]
            stocks.sort(key=lambda x: -x.get("change_pct", 0))
            
        elif context == "limit_up_streak":
            # Streak leaders
            stocks = await limit_up_service.get_streak_leaders()
            # Already sorted by streak count
            
        elif context == "limit_up_strong":
            # Strong stocks
            stocks = await limit_up_service.get_strong_stocks()
            # Already sorted
            
        elif context == "limit_up_watch":
            # Startup watchlist
            stocks = await limit_up_service.get_startup_watchlist()
            # Already sorted
            
        elif context == "morning":
            # Morning report: Yesterday's limit-up stocks (same as send_morning_price_update)
            prices = await limit_up_service.get_previous_limit_prices()
            # Sort by change_pct descending (same order as morning report)
            prices.sort(key=lambda x: -x.get("change_pct", 0))
            stocks = prices  # Already has 'code' field
            
        elif context == "watchlist" and user_id:
            # User watchlist
            stocks = await watchlist_service.get_watchlist(user_id)
            # Usually sorted by add time or custom order
            
        elif context.startswith("scanner_") and user_id:
            # Scanner results (cached in memory)
            # Context format: scanner_{signal_type}
            signal_type = context.replace("scanner_", "")
            
            # Import cache from handlers (assuming same process)
            try:
                from app.bots.crawler.routers.scanner import _scan_results_cache
                user_cache = _scan_results_cache.get(user_id)
                if user_cache:
                    stocks = user_cache.get(signal_type, [])
            except ImportError:
                pass
            
    except Exception as e:
        print(f"Navigation error: {e}")
        return {"prev": None, "next": None}
    
    if not stocks:
        return {"prev": None, "next": None}
        
    # Extract codes list
    codes = [s['code'] for s in stocks]
    
    try:
        idx = codes.index(code)
    except ValueError:
        return {"prev": None, "next": None}
        
    prev_code = codes[idx - 1] if idx > 0 else None
    next_code = codes[idx + 1] if idx < len(codes) - 1 else None
    
    return {"prev": prev_code, "next": next_code}
