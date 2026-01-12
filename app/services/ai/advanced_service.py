"""
Advanced AI Service with multi-agent and tool support.
This is a separate service from the simple AiService.
"""

from typing import Dict, Any, List, Optional
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
from app.services.ai.agents.orchestrator import AgentOrchestrator
from app.services.ai.prompts import build_job_prompt
from app.services.ai.agents.registry import agent_registry
from app.services.ai.tools.registry import tool_registry

logger = Logger("AdvancedAiService")

DEFAULT_PROVIDER = "groq"


class AdvancedAiService:
    """
    Advanced AI Service with multi-agent orchestration and tool support.
    
    This service is separate from the simple AiService and provides:
    - Multi-agent support with different specialized agents
    - Tool/function calling with various built-in tools
    - Extended thinking (Claude)
    - Agent orchestration and routing
    """
    
    def __init__(self):
        self.providers: Dict[str, BaseProvider] = {}
        self.active_provider: Optional[BaseProvider] = None
        self.orchestrator: Optional[AgentOrchestrator] = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize the service and register tools/agents."""
        if self._initialized:
            return
        
        self._register_providers()
        self._set_active_provider()
        await self._register_tools_and_agents()
        
        # Create orchestrator with active provider
        self.orchestrator = AgentOrchestrator(self.active_provider)
        
        # Ensure database tables exist
        from app.services.ai.advanced_storage import advanced_ai_storage
        await advanced_ai_storage.ensure_tables()
        
        self._initialized = True
        logger.info("Advanced AI Service initialized")
    
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
        """Set the active provider based on settings with smart fallback."""
        provider_name = getattr(settings, "AI_ADVANCED_PROVIDER", None) or DEFAULT_PROVIDER
        provider_name = provider_name.lower()
        
        # Try the configured provider first
        if provider_name in self.providers:
            provider = self.providers[provider_name]
            if provider.is_configured() and provider.supports_tools:
                self.active_provider = provider
                logger.info(f"✅ Active Advanced AI Provider: {provider_name}")
                return
            elif provider.is_configured():
                logger.warn(f"⚠️ Provider {provider_name} configured but lacks tool support")
            else:
                logger.warn(f"⚠️ Provider {provider_name} selected but not configured")
        else:
            logger.warn(f"⚠️ Unknown provider: {provider_name}")
        
        # Fallback: find any configured provider with tool support
        for name, provider in self.providers.items():
            if provider.is_configured() and provider.supports_tools:
                self.active_provider = provider
                logger.info(f"✅ Fallback to configured provider with tool support: {name}")
                return
        
        # Last resort: find any configured provider (even without tool support)
        for name, provider in self.providers.items():
            if provider.is_configured():
                self.active_provider = provider
                logger.warn(f"⚠️ Fallback to provider without tool support: {name}")
                return
        
        logger.error("❌ No configured AI providers available")
    
    async def _register_tools_and_agents(self):
        """Register all tools and agents."""
        from app.services.ai.tools.builtin import register_builtin_tools
        from app.services.ai.tools.file_tool import register_file_tools
        from app.services.ai.tools.github_tool import register_github_tools
        from app.services.ai.tools.cloudflare_tool import register_cloudflare_tools
        from app.services.ai.agents.builtin import register_builtin_agents
        
        # Register tools
        register_builtin_tools()
        register_file_tools()
        register_github_tools()
        register_cloudflare_tools()
        
        # Register skill tool (on-demand skill loading)
        from app.services.ai.tools.skill_tool import register_skill_tool
        register_skill_tool()
        
        # Register agents
        register_builtin_agents()
        
        logger.info(f"Registered {len(tool_registry.list_all())} tools and {len(agent_registry.list_all())} agents")
    
    def is_available(self) -> bool:
        """Check if advanced AI is available."""
        return self.active_provider is not None and self.active_provider.is_configured()
    
    def list_providers(self) -> List[Dict[str, Any]]:
        """List available AI providers with their tool support status."""
        return [
            {
                "key": key,
                "name": provider.name,
                "configured": provider.is_configured(),
                "active": provider == self.active_provider,
                "supports_tools": provider.supports_tools,
                "supports_thinking": provider.supports_thinking,
            }
            for key, provider in self.providers.items()
        ]
    
    def list_agents(self) -> List[Dict[str, str]]:
        """List available agents."""
        return agent_registry.get_agent_info()

    async def get_models(self, provider_key: str = None) -> List[Dict[str, str]]:
        """Get available models for a provider."""
        provider = self.get_provider(provider_key)
        if not provider:
            return []
        return await provider.fetch_models()
    
    def list_tools(self) -> List[Dict[str, str]]:
        """List available tools."""
        return tool_registry.get_tool_info()
    
    async def chat(
        self,
        message: str,
        agent_name: str = None,
        history: List[Dict[str, str]] = None,
        model: str = None,
        provider_key: str = None,
        auto_route: bool = False
    ) -> Dict[str, Any]:
        """
        Send a message and get AI response with optional agent and tools.
        
        Args:
            message: User message
            agent_name: Specific agent to use (default: chat)
            history: Conversation history
            model: Model override
            auto_route: Automatically route to best agent based on message
            
        Returns:
            {
                "content": str,
                "thinking": str (optional),
                "agent": str,
                "tool_calls": list,
                "tool_results": list
            }
        """
        if not self._initialized:
            await self.initialize()
        
        provider = self.get_provider(provider_key)
        if not provider or not provider.is_configured():
            return {"content": "Advanced AI provider is not configured.", "agent": "none"}
        
        try:
            orchestrator = AgentOrchestrator(provider)
            if auto_route:
                response = await orchestrator.run_with_routing(
                    message=message,
                    history=history,
                    model=model
                )
            else:
                response = await orchestrator.run(
                    message=message,
                    agent_name=agent_name,
                    history=history,
                    model=model
                )
            
            return {
                "content": response.content,
                "thinking": response.thinking,
                "agent": orchestrator.current_agent.name if orchestrator.current_agent else "unknown",
                "tool_calls": response.tool_calls,
                "tool_results": [r.to_dict() for r in response.tool_results],
                "metadata": {
                    **response.metadata,
                    "provider": provider.name,
                    "model": model or getattr(provider, "default_model", None)
                }
            }
        except Exception as e:
            logger.error(f"Chat error: {e}")
            return {"content": f"Error: {e}", "agent": "error"}

    async def run_job(
        self,
        job_id: str,
        payload: Dict = None,
        provider_key: str = None,
        model: str = None,
        history: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Run a prompt-catalog job using the selected advanced provider."""
        if not self._initialized:
            await self.initialize()
        
        provider = self.get_provider(provider_key)
        if not provider or not provider.is_configured():
            raise ValueError("Advanced AI provider is not configured.")
        
        job_data = build_job_prompt(job_id, payload or {})
        model_name = model or getattr(provider, "default_model", None)
        
        return await provider.call(
            prompt=job_data["prompt"],
            model=model_name,
            history=history or [],
            context_prefix=job_data["system"]
        )

    async def export_chat(
        self,
        user_id: int,
        chat_id: int,
        provider_key: str = None,
        model: str = None
    ) -> Dict[str, Any]:
        """Export advanced chat to markdown and optionally push to GitHub."""
        from datetime import datetime
        from app.services.ai.advanced_storage import advanced_ai_storage
        
        chat = await advanced_ai_storage.get_chat_by_id(chat_id)
        messages = await advanced_ai_storage.get_all_chat_messages(chat_id)
        
        if not chat or not messages:
            raise ValueError("No messages to export")
        
        now = datetime.now()
        mmdd = now.strftime("%m%d")
        words = (chat.get("title") or "chat").split()[:3]
        safe_words = "-".join(words)[:30]
        filename = f"{mmdd}-{safe_words or 'chat'}.md"
        
        raw_content = "\n\n---\n\n".join(
            f"**{'User' if m['role'] == 'user' else 'Assistant'}:**\n{m['content']}"
            for m in messages
        )
        
        raw_markdown = (
            f"# {chat.get('title', 'Chat')}\n\n"
            f"> Exported: {now.isoformat()} | {len(messages)} messages\n\n"
            f"{raw_content}\n\n---\n*Exported from QuBot*"
        )
        
        summary_markdown = ""
        try:
            result = await self.run_job(
                "chat_notes",
                {"conversation": raw_content},
                provider_key=provider_key,
                model=model
            )
            summary = result.get("content", "Summary generation failed.")
            summary_markdown = (
                f"# {chat.get('title', 'Chat')} - Notes\n\n"
                f"> Summary of {len(messages)} messages | {now.isoformat()}\n\n"
                f"{summary}\n\n---\n*AI-generated summary from QuBot*"
            )
        except Exception as e:
            logger.warn(f"Summary generation failed: {e}")
            summary_markdown = (
                f"# {chat.get('title', 'Chat')} - Notes\n\n"
                "> Summary generation failed\n\n"
                "See raw file for full conversation."
            )
        
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
    
    async def execute_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """Execute a single tool directly."""
        tool = tool_registry.get(tool_name)
        if not tool:
            return {"success": False, "error": f"Tool '{tool_name}' not found"}
        
        try:
            result = await tool.execute(**kwargs)
            return result.to_dict()
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def switch_provider(self, provider_key: str) -> bool:
        """Switch the active provider."""
        if provider_key not in self.providers:
            return False
        
        provider = self.providers[provider_key]
        if not provider.is_configured():
            return False
        
        self.active_provider = provider
        if self.orchestrator:
            self.orchestrator.set_provider(provider)
        
        logger.info(f"Switched to provider: {provider_key}")
        return True

    def get_provider(self, provider_key: str = None) -> Optional[BaseProvider]:
        """Resolve a provider by key or fall back to active provider."""
        if provider_key:
            return self.providers.get(provider_key.lower())
        return self.active_provider
    
    def get_status(self) -> Dict[str, Any]:
        """Get service status."""
        return {
            "initialized": self._initialized,
            "available": self.is_available(),
            "provider": self.active_provider.name if self.active_provider else None,
            "supports_tools": self.active_provider.supports_tools if self.active_provider else False,
            "supports_thinking": self.active_provider.supports_thinking if self.active_provider else False,
            "tools_count": len(tool_registry.list_all()),
            "agents_count": len(agent_registry.list_all()),
        }


# Global service instance
advanced_ai_service = AdvancedAiService()
