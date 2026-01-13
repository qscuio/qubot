from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from app.api.auth import verify_api_key
from app.services.monitor import monitor_service
from app.services.rss import rss_service
from app.services.ai import ai_service
from app.core.bot import telegram_service

router = APIRouter(prefix="/api", tags=["API"])


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

@chart_router.get("/chart/data/{code}")
async def chart_data(code: str, days: int = 60, period: str = "daily"):
    """Get OHLCV data for stock chart Mini App.
    
    Args:
        code: Stock code (e.g., 600519)
        days: Number of periods to return
        period: 'daily', 'weekly', or 'monthly'
    """
    import asyncio
    from app.services.stock_history import stock_history_service
    from app.core.database import db
    
    data = []
    name = code  # Default to code if name not found
    
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
    
    try:
        # Only use database for daily data (weekly/monthly need to fetch fresh)
        if period == "daily":
            history = await stock_history_service.get_stock_history(code, days=days)
            
            if history:
                for h in reversed(history):
                    data.append({
                        "time": h['date'].strftime("%Y-%m-%d"),
                        "open": float(h['open']),
                        "high": float(h['high']),
                        "low": float(h['low']),
                        "close": float(h['close']),
                        "volume": int(h['volume']),
                    })
                    # Get name from first record if available
                    if name == code and h.get('name'):
                        name = h['name']
    except Exception as e:
        pass
    
    # Fallback or weekly/monthly: fetch from AkShare
    if not data:
        try:
            import akshare as ak
            from datetime import datetime, timedelta
            
            # For weekly/monthly, request more source data
            extra_days = 30 if period == "daily" else (days * 7 if period == "weekly" else days * 31)
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=days + extra_days)).strftime("%Y%m%d")
            
            df = await asyncio.to_thread(
                ak.stock_zh_a_hist,
                symbol=code,
                period=period,
                start_date=start_date,
                end_date=end_date,
                adjust="qfq"
            )
            
            if df is not None and not df.empty:
                if '名称' in df.columns:
                    name = str(df['名称'].iloc[0]) if not df['名称'].isna().all() else code
                
                for _, row in df.tail(days).iterrows():
                    try:
                        data.append({
                            "time": str(row['日期'])[:10],
                            "open": float(row.get('开盘', 0)),
                            "high": float(row.get('最高', 0)),
                            "low": float(row.get('最低', 0)),
                            "close": float(row.get('收盘', 0)),
                            "volume": int(row.get('成交量', 0)),
                        })
                    except:
                        continue
        except Exception as e:
            pass
    
    if not data:
        raise HTTPException(status_code=404, detail=f"No data for {code}")
    
    return {
        "code": code,
        "name": name,
        "period": period,
        "data": data,
    }


@chart_router.get("/chart/chips/{code}")
async def chart_chips(code: str, date: str = None):
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


# ─────────────────────────────────────────────────────────────────────────────
# Watchlist Endpoints (for Mini App)
# ─────────────────────────────────────────────────────────────────────────────

class WatchlistRequest(BaseModel):
    user_id: int
    code: str
    name: Optional[str] = None

@chart_router.post("/chart/watchlist/add")
async def chart_watchlist_add(req: WatchlistRequest):
    """Add stock to watchlist from Mini App."""
    from app.services.watchlist import watchlist_service
    try:
        result = await watchlist_service.add_stock(req.user_id, req.code, req.name)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@chart_router.post("/chart/watchlist/remove")
async def chart_watchlist_remove(req: WatchlistRequest):
    """Remove stock from watchlist from Mini App."""
    from app.services.watchlist import watchlist_service
    try:
        success = await watchlist_service.remove_stock(req.user_id, req.code)
        return {"success": success}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@chart_router.get("/chart/watchlist/status")
async def chart_watchlist_status(user_id: int, code: str):
    """Check if stock is in watchlist."""
    from app.services.watchlist import watchlist_service
    try:
        watchlist = await watchlist_service.get_watchlist(user_id)
        is_in = any(item['code'] == code for item in watchlist)
        return {"in_watchlist": is_in}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@chart_router.get("/chart/navigation")
async def get_chart_navigation(code: str, context: str, user_id: int = None):
    """Get previous and next stock codes based on context."""
    from app.services.limit_up import limit_up_service
    from app.services.watchlist import watchlist_service
    
    stocks = []
    
    try:
        if context == "limit_up":
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
                from app.bots.crawler.handlers import _scan_results_cache
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
