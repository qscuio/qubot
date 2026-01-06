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
