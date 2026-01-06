from typing import Dict, Optional, List, Any
from app.core.config import settings
from app.core.logger import Logger
from app.providers.base import BaseProvider
from app.providers.openai import OpenAIProvider
from app.providers.groq import GroqProvider
from app.providers.gemini import GeminiProvider
from app.providers.claude import ClaudeProvider
from app.providers.nvidia import NvidiaProvider
from app.providers.glm import GLMProvider
from app.providers.minimax import MiniMaxProvider
from app.providers.openrouter import OpenRouterProvider
from app.services.ai.prompts import build_job_prompt, list_jobs
from app.services.ai.storage import ai_storage

logger = Logger("AiService")

DEFAULT_PROVIDER = "groq"


class AiService:
    def __init__(self):
        self.providers: Dict[str, BaseProvider] = {}
        self.active_provider: Optional[BaseProvider] = None
        self._register_providers()
        self._set_active_provider()

    def _register_providers(self):
        """Register all available providers."""
        self.providers["openai"] = OpenAIProvider()
        self.providers["groq"] = GroqProvider()
        self.providers["gemini"] = GeminiProvider()
        self.providers["claude"] = ClaudeProvider()
        self.providers["nvidia"] = NvidiaProvider()
        self.providers["glm"] = GLMProvider()
        self.providers["minimax"] = MiniMaxProvider()
        self.providers["openrouter"] = OpenRouterProvider()

    def _set_active_provider(self):
        """Set the active provider based on settings."""
        provider_name = (settings.AI_PROVIDER or DEFAULT_PROVIDER).lower()
        
        if provider_name in self.providers:
            self.active_provider = self.providers[provider_name]
            if self.active_provider.is_configured():
                logger.info(f"✅ Active AI Provider: {provider_name}")
            else:
                logger.warn(f"⚠️ Provider {provider_name} selected but not configured (missing API key).")
        else:
            logger.warn(f"Unknown AI provider: {provider_name}. Defaulting to {DEFAULT_PROVIDER}.")
            if DEFAULT_PROVIDER in self.providers:
                self.active_provider = self.providers[DEFAULT_PROVIDER]

    def is_available(self) -> bool:
        """Check if AI is available (at least one provider configured)."""
        return self.active_provider is not None and self.active_provider.is_configured()

    def list_providers(self) -> List[Dict[str, Any]]:
        """List available AI providers with their configuration status."""
        return [
            {
                "key": key,
                "name": provider.name,
                "configured": provider.is_configured(),
                "active": provider == self.active_provider,
            }
            for key, provider in self.providers.items()
        ]

    async def get_models(self, provider_key: str = None) -> List[Dict[str, str]]:
        """Get available models for a provider."""
        provider_key = provider_key or (self.active_provider.name if self.active_provider else DEFAULT_PROVIDER)
        provider = self.providers.get(provider_key.lower())
        
        if not provider:
            return []
        
        return await provider.fetch_models()

    async def generate_response(self, prompt: str, history: List[Dict[str, str]] = None, system_prompt: str = "") -> str:
        """Generate a response using the active provider."""
        if not self.is_available():
            return "AI Service is not configured."
        
        if history is None:
            history = []

        try:
            result = await self.active_provider.call(
                prompt=prompt,
                model=settings.AI_MODEL,
                history=history,
                context_prefix=system_prompt
            )
            return result["content"]
        except Exception as e:
            logger.error("Error generating response", e)
            return "Sorry, I encountered an error while processing your request."

    async def quick_chat(self, prompt: str, provider_key: str = None) -> Dict[str, Any]:
        """Quick one-shot chat without user context. Used for summarization, etc."""
        provider_key = provider_key or (self.active_provider.name if self.active_provider else DEFAULT_PROVIDER)
        provider = self.providers.get(provider_key.lower())
        
        if not provider or not provider.get_api_key():
            # Try groq as fallback (fast and cheap)
            provider = self.providers.get("groq")
        
        if not provider or not provider.get_api_key():
            return {"content": "No AI provider configured"}
        
        try:
            result = await provider.call(
                prompt=prompt,
                model=provider.default_model,
                history=[],
                context_prefix=""
            )
            return result
        except Exception as e:
            logger.error(f"quick_chat error: {e}")
            return {"content": f"Error: {e}"}

    async def analyze(self, prompt: str, options: Dict = None) -> Dict[str, str]:
        """
        Analyze content with AI (general-purpose, no user context needed).
        This is the main method for other services to call.
        """
        options = options or {}
        provider_key = options.get("provider", self.active_provider.name if self.active_provider else DEFAULT_PROVIDER)
        provider = self.providers.get(provider_key.lower(), self.active_provider)
        
        if not provider or not provider.is_configured():
            raise ValueError(f"Provider {provider_key} is not configured.")

        model = options.get("model") or getattr(provider, "default_model", None)
        system_prompt = options.get("system_prompt", "")

        return await provider.call(
            prompt=prompt,
            model=model,
            history=[],
            context_prefix=system_prompt
        )

    async def summarize(self, text: str, max_length: int = 200, language: str = "en", options: Dict = None) -> str:
        """Summarize text content in specified language (en or zh)."""
        if language == "zh":
            prompt = f"""请用中文对以下内容进行专业总结（限{max_length}字以内）。

要求：
1. 提取核心观点和关键信息
2. 保留重要的数据、名称和结论
3. 使用简洁专业的语言
4. 突出可操作的信息或建议

内容：
{text}

总结："""
        else:
            prompt = f"""Provide a professional summary of the following content ({max_length} chars max).

Requirements:
1. Extract core points and key information
2. Preserve important data, names, and conclusions
3. Use concise, professional language
4. Highlight actionable insights

Content:
{text}

Summary:"""
        result = await self.analyze(prompt, options)
        return result.get("content", "")

    async def translate(self, text: str, target_language: str, source_language: str = "", options: Dict = None) -> str:
        """Translate text between languages."""
        source_part = f" from {source_language}" if source_language else ""
        prompt = f"Translate the following text{source_part} to {target_language}:\n\n{text}"
        result = await self.analyze(prompt, options)
        return result.get("content", "")

    async def categorize(self, text: str, categories: List[str], options: Dict = None) -> Dict:
        """Categorize content into predefined categories."""
        cats = ", ".join(categories)
        prompt = f"""Categorize the following text into one of these categories: {cats}

Text: {text}

Respond with JSON: {{"category": "chosen_category", "confidence": "high/medium/low", "reasoning": "brief explanation"}}"""
        
        result = await self.analyze(prompt, options)
        # Try to parse JSON from response
        import json
        try:
            return json.loads(result.get("content", "{}"))
        except:
            return {"category": "unknown", "confidence": "low", "reasoning": result.get("content", "")}

    async def get_sentiment(self, text: str, options: Dict = None) -> Dict:
        """Get sentiment analysis for a message."""
        prompt = f"""Analyze the sentiment of this text and respond with JSON:
{{"sentiment": "positive/negative/neutral", "score": 0.0-1.0}}

Text: {text}"""
        
        result = await self.analyze(prompt, options)
        import json
        try:
            return json.loads(result.get("content", "{}"))
        except:
            return {"sentiment": "neutral", "score": 0.5}

    # ============= Chat Session Methods =============
    
    async def chat(self, user_id: int, message: str) -> Dict[str, Any]:
        """Send a message and get AI response with history."""
        user_settings = await ai_storage.get_settings(user_id)
        provider = self.providers.get(user_settings.get("provider", DEFAULT_PROVIDER).lower())
        
        if not provider or not provider.is_configured():
            provider = self.active_provider
        
        if not provider or not provider.is_configured():
            raise ValueError("No AI provider configured")
        
        # Get/create active chat
        active_chat = await ai_storage.get_or_create_active_chat(user_id)
        chat_id = active_chat.get("id")
        
        if chat_id:
            await ai_storage.save_message(chat_id, "user", message)
            
            # Auto-title on first message
            msg_count = await ai_storage.get_message_count(chat_id)
            if msg_count == 1 and active_chat.get("title") == "New Chat":
                short_title = message[:40] + ("..." if len(message) > 40 else "")
                await ai_storage.rename_chat(chat_id, short_title)
        
        # Build history
        history = []
        summary_prefix = ""
        if chat_id:
            recent = await ai_storage.get_chat_messages(chat_id, 4)
            history = [{"role": m["role"], "content": m["content"]} for m in reversed(recent)]
            if active_chat.get("summary"):
                summary_prefix = f"[Previous conversation summary: {active_chat['summary']}]"
        
        # Call AI
        job_data = build_job_prompt("chat", {"message": message})
        model = user_settings.get("model") or getattr(provider, "default_model", None)
        
        result = await provider.call(
            prompt=job_data["prompt"],
            model=model,
            history=history,
            context_prefix=summary_prefix + job_data["system"]
        )
        
        content = result.get("content", "")
        
        # Save assistant message
        if chat_id and content:
            await ai_storage.save_message(chat_id, "assistant", content)
        
        return {
            "content": content,
            "thinking": result.get("thinking", ""),
            "chat_id": chat_id,
            "provider": provider.name,
            "model": model
        }

    async def run_job(self, job_id: str, payload: Dict = None, options: Dict = None) -> Dict[str, str]:
        """Run a job from the prompt catalog."""
        options = options or {}
        job_data = build_job_prompt(job_id, payload or {})
        
        provider_key = options.get("provider", self.active_provider.name if self.active_provider else DEFAULT_PROVIDER)
        provider = self.providers.get(provider_key.lower(), self.active_provider)
        
        if not provider or not provider.is_configured():
            raise ValueError(f"Provider {provider_key} not configured")
        
        model = options.get("model") or getattr(provider, "default_model", None)
        history = options.get("history", [])
        context = options.get("contextPrefix", "") + job_data["system"]
        
        return await provider.call(
            prompt=job_data["prompt"],
            model=model,
            history=history,
            context_prefix=context
        )

    async def get_settings(self, user_id: int) -> Dict:
        return await ai_storage.get_settings(user_id)

    async def update_settings(self, user_id: int, provider: str, model: str):
        await ai_storage.update_settings(user_id, provider, model)

    async def get_chats(self, user_id: int, limit: int = 10) -> List[Dict]:
        return await ai_storage.get_user_chats(user_id, limit)

    async def create_chat(self, user_id: int) -> Dict:
        return await ai_storage.create_new_chat(user_id)

    async def switch_chat(self, user_id: int, chat_id: int) -> Optional[Dict]:
        await ai_storage.set_active_chat(user_id, chat_id)
        return await ai_storage.get_chat_by_id(chat_id)

    async def rename_chat(self, chat_id: int, title: str):
        await ai_storage.rename_chat(chat_id, title)

    async def clear_chat(self, chat_id: int):
        await ai_storage.clear_chat_messages(chat_id)

    async def export_chat(self, user_id: int, chat_id: int) -> Dict[str, Any]:
        """Export chat to markdown and optionally push to GitHub."""
        from datetime import datetime
        
        chat = await ai_storage.get_chat_by_id(chat_id)
        messages = await ai_storage.get_chat_messages(chat_id, 100)
        
        if not chat or not messages:
            raise ValueError("No messages to export")
        
        # Generate filename
        now = datetime.now()
        mmdd = now.strftime("%m%d")
        words = (chat.get("title") or "chat").split()[:3]
        safe_words = "-".join(words)[:30]
        filename = f"{mmdd}-{safe_words or 'chat'}.md"
        
        # Build raw content
        raw_content = "\n\n---\n\n".join(
            f"**{'User' if m['role'] == 'user' else 'Assistant'}:**\n{m['content']}"
            for m in reversed(messages)
        )
        
        raw_markdown = f"# {chat.get('title', 'Chat')}\n\n> Exported: {now.isoformat()} | {len(messages)} messages\n\n{raw_content}\n\n---\n*Exported from QuBot*"
        
        # Generate summary using AI
        summary_markdown = ""
        try:
            result = await self.run_job("chat_notes", {"conversation": raw_content})
            summary = result.get("content", "Summary generation failed.")
            summary_markdown = f"# {chat.get('title', 'Chat')} - Notes\n\n> Summary of {len(messages)} messages | {now.isoformat()}\n\n{summary}\n\n---\n*AI-generated summary from QuBot*"
        except Exception as e:
            logger.warn(f"Summary generation failed: {e}")
            summary_markdown = f"# {chat.get('title', 'Chat')} - Notes\n\n> Summary generation failed\n\nSee raw file for full conversation."
        
        # Push to GitHub if configured
        urls = None
        if settings.NOTES_REPO:
            try:
                from app.services.github import github_service
                if github_service.is_ready:
                    raw_url = github_service.save_note(f"raw/{filename}", raw_markdown, f"Export raw: {chat.get('title')}")
                    notes_url = github_service.save_note(f"notes/{filename}", summary_markdown, f"Export notes: {chat.get('title')}")
                    urls = {"raw": raw_url, "notes": notes_url}
            except Exception as e:
                logger.error(f"GitHub push failed: {e}")
        
        return {
            "filename": filename,
            "raw_markdown": raw_markdown,
            "summary_markdown": summary_markdown,
            "urls": urls,
            "message_count": len(messages)
        }

    def list_jobs(self) -> List[Dict[str, str]]:
        return list_jobs()


ai_service = AiService()
