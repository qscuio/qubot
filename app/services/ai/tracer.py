"""
AI Agent Tracing Module

Provides full logging for AI agent workflows including:
- Full prompts sent to AI providers
- Full responses received
- Tools and skills used
- Token usage tracking per provider/model
"""
import time
import json
from typing import Dict, Any, List
from datetime import datetime
from dataclasses import dataclass
from app.core.logger import Logger
from app.core.database import db

logger = Logger("AITrace")


@dataclass
class TokenUsage:
    """Tracks token usage for a provider/model combination."""
    provider: str
    model: str
    prompt_tokens: int = 0
    response_tokens: int = 0
    total_tokens: int = 0
    call_count: int = 0


class AITracer:
    """Manages AI agent tracing and token usage tracking."""
    
    def __init__(self):
        self.enabled = True
        self._current_start_time = 0
        self._current_provider = ""
        self._current_model = ""
        self._current_prompt = ""
        self._current_system = ""
        self._current_history = []
        self._current_tools = []
        self._current_skills = []
        self._tool_calls = []
        
        # Token usage tracking: key = "provider:model"
        self._usage: Dict[str, TokenUsage] = {}
    
    def start_trace(
        self,
        provider: str,
        model: str,
        prompt: str,
        system_prompt: str = "",
        history: List[Dict] = None,
        tools: List[str] = None,
        skills: List[str] = None
    ) -> str:
        """Start a new trace. Returns trace_id."""
        if not self.enabled:
            return ""
        
        self._current_start_time = time.time()
        self._current_provider = provider
        self._current_model = model or "unknown"
        self._current_prompt = prompt
        self._current_system = system_prompt
        self._current_history = history or []
        self._current_tools = tools or []
        self._current_skills = skills or []
        self._tool_calls = []
        
        # Calculate tokens
        prompt_tokens = self._estimate_tokens(prompt + system_prompt)
        history_tokens = sum(self._estimate_tokens(h.get("content", "")) for h in (history or []))
        
        # Log full TX
        logger.info("═" * 70)
        logger.info(f"📤 TX | {provider}/{model} | ~{prompt_tokens + history_tokens} tokens")
        logger.info("─" * 70)
        
        if system_prompt:
            logger.info(f"📋 SYSTEM PROMPT:\n{system_prompt}")
            logger.info("─" * 70)
        
        if history:
            logger.info(f"📚 HISTORY ({len(history)} messages):")
            for i, h in enumerate(history[-5:]):  # Last 5 messages
                role = h.get("role", "?")
                content = h.get("content", "")[:300]
                logger.info(f"  [{i+1}] {role}: {content}{'...' if len(h.get('content', '')) > 300 else ''}")
            logger.info("─" * 70)
        
        if tools:
            logger.info(f"🔧 TOOLS AVAILABLE: {', '.join(tools)}")
        
        if skills:
            logger.info(f"🎯 SKILLS: {', '.join(skills)}")
        
        logger.info(f"💬 PROMPT:\n{prompt}")
        logger.info("─" * 70)
        
        return f"trace_{datetime.now().strftime('%H%M%S')}"
    
    def add_tool_call(self, name: str, arguments: Dict = None, result: Any = None, success: bool = True):
        """Record a tool call."""
        if not self.enabled:
            return
        
        self._tool_calls.append({
            "name": name,
            "arguments": arguments,
            "result": str(result)[:500] if result else "",
            "success": success
        })
        
        status = "✅" if success else "❌"
        logger.info(f"⚡ TOOL CALL: {name} {status}")
        if arguments:
            logger.info(f"   Args: {json.dumps(arguments, ensure_ascii=False)[:200]}")
        if result:
            logger.info(f"   Result: {str(result)[:300]}")
    
    def end_trace(
        self,
        response: str = "",
        thinking: str = "",
        success: bool = True,
        error: str = ""
    ):
        """End the current trace, log full result, and update token usage."""
        if not self.enabled:
            return
        
        execution_time = int((time.time() - self._current_start_time) * 1000)
        prompt_tokens = self._estimate_tokens(self._current_prompt + self._current_system)
        response_tokens = self._estimate_tokens(response)
        
        # Update usage tracking
        key = f"{self._current_provider}:{self._current_model}"
        if key not in self._usage:
            self._usage[key] = TokenUsage(
                provider=self._current_provider,
                model=self._current_model
            )
        
        usage = self._usage[key]
        usage.prompt_tokens += prompt_tokens
        usage.response_tokens += response_tokens
        usage.total_tokens += prompt_tokens + response_tokens
        usage.call_count += 1
        
        # Log full RX
        logger.info("─" * 70)
        status = "✅" if success else "❌"
        logger.info(f"📥 RX | {self._current_provider}/{self._current_model} | {status} | {execution_time}ms | ~{response_tokens} tokens")
        logger.info("─" * 70)
        
        if self._tool_calls:
            logger.info(f"🔧 TOOLS CALLED ({len(self._tool_calls)}):")
            for tc in self._tool_calls:
                logger.info(f"   → {tc['name']}: {'✅' if tc['success'] else '❌'}")
        
        if thinking:
            logger.info(f"💭 THINKING:\n{thinking}")
            logger.info("─" * 70)
        
        if error:
            logger.error(f"❌ ERROR: {error}")
        else:
            logger.info(f"📝 RESPONSE:\n{response}")
        
        logger.info("═" * 70)
        
        # Save to DB (token usage only)
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._save_usage(
                    self._current_provider, 
                    self._current_model,
                    prompt_tokens,
                    response_tokens
                ))
        except:
            pass
    
    async def _save_usage(self, provider: str, model: str, prompt_tokens: int, response_tokens: int):
        """Save token usage to database."""
        if not db.pool:
            return
        
        try:
            await db.pool.execute("""
                INSERT INTO ai_token_usage (provider, model, prompt_tokens, response_tokens, total_tokens)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (provider, model) 
                DO UPDATE SET 
                    prompt_tokens = ai_token_usage.prompt_tokens + $3,
                    response_tokens = ai_token_usage.response_tokens + $4,
                    total_tokens = ai_token_usage.total_tokens + $5,
                    call_count = ai_token_usage.call_count + 1,
                    updated_at = NOW()
            """, provider, model, prompt_tokens, response_tokens, prompt_tokens + response_tokens)
        except Exception as e:
            logger.debug(f"Failed to save token usage: {e}")
    
    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimation (4 chars per token for English, 2 for Chinese)."""
        if not text:
            return 0
        return len(text) // 3
    
    def get_usage_summary(self) -> Dict[str, Any]:
        """Get current session's token usage summary."""
        total_prompt = sum(u.prompt_tokens for u in self._usage.values())
        total_response = sum(u.response_tokens for u in self._usage.values())
        total_calls = sum(u.call_count for u in self._usage.values())
        
        return {
            "total_prompt_tokens": total_prompt,
            "total_response_tokens": total_response,
            "total_tokens": total_prompt + total_response,
            "total_calls": total_calls,
            "by_provider": {k: {
                "prompt_tokens": v.prompt_tokens,
                "response_tokens": v.response_tokens,
                "total_tokens": v.total_tokens,
                "call_count": v.call_count
            } for k, v in self._usage.items()}
        }
    
    async def get_db_usage(self) -> List[Dict]:
        """Get token usage from database."""
        if not db.pool:
            return []
        
        try:
            rows = await db.pool.fetch("""
                SELECT provider, model, prompt_tokens, response_tokens, total_tokens, call_count
                FROM ai_token_usage
                ORDER BY total_tokens DESC
            """)
            return [dict(row) for row in rows]
        except:
            return []


# Global tracer instance
ai_tracer = AITracer()
