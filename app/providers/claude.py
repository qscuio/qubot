from typing import List, Dict, Any, Optional
import httpx
import json
from app.providers.base import BaseProvider
from app.core.logger import Logger
from app.core.config import settings

logger = Logger("Claude")

class ClaudeProvider(BaseProvider):
    def __init__(self):
        super().__init__("claude", "CLAUDE_API_KEY")
        self.default_model = "claude-sonnet-4-20250514"
        self.fallback_models = {
            "claude-opus-4.5": "claude-opus-4-5-20251124",
            "claude-sonnet-4.5": "claude-sonnet-4-5-20250929",
            "claude-haiku-4.5": "claude-haiku-4-5-20251015",
            "claude-opus-4": "claude-opus-4-20250522",
            "claude-sonnet-4": "claude-sonnet-4-20250514",
        }
        self.base_url = "https://api.anthropic.com/v1/messages"
    
    @property
    def supports_tools(self) -> bool:
        return True
    
    @property
    def supports_thinking(self) -> bool:
        return True

    async def fetch_models(self) -> List[Dict[str, str]]:
        # Claude doesn't have a public models API
        return self.get_fallback_models()

    async def call(self, prompt: str, model: str, history: List[Dict[str, str]] = None, context_prefix: str = "") -> Dict[str, Any]:
        api_key = self.get_api_key()
        if not api_key:
            raise ValueError("CLAUDE_API_KEY is not set")

        if history is None:
            history = []

        messages = []
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})
        
        full_prompt = f"{context_prefix}{prompt}" if context_prefix else prompt
        messages.append({"role": "user", "content": full_prompt})

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    self.base_url,
                    json={"model": model or self.default_model, "max_tokens": 4096, "messages": messages},
                    headers={
                        "Content-Type": "application/json",
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                    },
                    timeout=90.0
                )
                response.raise_for_status()
                data = response.json()

                thinking, content = "", ""
                for block in data.get("content", []):
                    if block.get("type") == "thinking":
                        thinking += block.get("thinking", "")
                    elif block.get("type") == "text":
                        content += block.get("text", "")

                return {"thinking": thinking, "content": content}
            except Exception as e:
                logger.error(f"Claude API call failed: {e}")
                raise
    
    async def call_with_tools(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        system_prompt: str = "",
        tools: List[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Call Claude with tool/function calling support.
        """
        api_key = self.get_api_key()
        if not api_key:
            raise ValueError("CLAUDE_API_KEY is not set")
        
        # Convert messages to Claude format
        claude_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            if role == "tool":
                # Tool result - add as tool_result block
                claude_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.get("tool_call_id", ""),
                        "content": content
                    }]
                })
            elif role == "assistant" and msg.get("tool_calls"):
                # Assistant with tool calls
                blocks = []
                if content:
                    blocks.append({"type": "text", "text": content})
                for tc in msg.get("tool_calls", []):
                    blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", tc.get("name", "")),
                        "name": tc.get("name", ""),
                        "input": tc.get("arguments", {})
                    })
                claude_messages.append({"role": "assistant", "content": blocks})
            else:
                claude_messages.append({"role": role, "content": content})
        
        # Convert tools to Claude format
        claude_tools = []
        if tools:
            for tool in tools:
                func = tool.get("function", {})
                claude_tools.append({
                    "name": func.get("name", ""),
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {})
                })
        
        # Build request
        request_body = {
            "model": model or self.default_model,
            "max_tokens": 4096,
            "messages": claude_messages
        }
        
        if system_prompt:
            request_body["system"] = system_prompt
        
        if claude_tools:
            request_body["tools"] = claude_tools
        
        # Headers with optional extended thinking
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
        
        # Enable extended thinking if configured
        if getattr(settings, "AI_EXTENDED_THINKING", False):
            headers["anthropic-beta"] = "thinking-2025-04-15"
            request_body["thinking"] = {
                "type": "enabled",
                "budget_tokens": 5000
            }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    self.base_url,
                    json=request_body,
                    headers=headers,
                    timeout=120.0
                )
                response.raise_for_status()
                data = response.json()
                
                thinking = ""
                content = ""
                tool_calls = []
                
                for block in data.get("content", []):
                    block_type = block.get("type", "")
                    
                    if block_type == "thinking":
                        thinking += block.get("thinking", "")
                    elif block_type == "text":
                        content += block.get("text", "")
                    elif block_type == "tool_use":
                        tool_calls.append({
                            "id": block.get("id", ""),
                            "name": block.get("name", ""),
                            "arguments": block.get("input", {})
                        })
                
                return {
                    "thinking": thinking,
                    "content": content,
                    "tool_calls": tool_calls
                }
            except Exception as e:
                logger.error(f"Claude API call with tools failed: {e}")
                raise

