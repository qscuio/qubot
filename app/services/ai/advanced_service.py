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
from app.services.ai.agents.registry import agent_registry
from app.services.ai.tools.registry import tool_registry

logger = Logger("AdvancedAiService")

DEFAULT_PROVIDER = "claude"


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
    
    def list_tools(self) -> List[Dict[str, str]]:
        """List available tools."""
        return tool_registry.get_tool_info()
    
    async def chat(
        self,
        message: str,
        agent_name: str = None,
        history: List[Dict[str, str]] = None,
        model: str = None,
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
        
        if not self.is_available():
            return {"content": "Advanced AI Service is not configured.", "agent": "none"}
        
        try:
            if auto_route:
                response = await self.orchestrator.run_with_routing(
                    message=message,
                    history=history,
                    model=model
                )
            else:
                response = await self.orchestrator.run(
                    message=message,
                    agent_name=agent_name,
                    history=history,
                    model=model
                )
            
            return {
                "content": response.content,
                "thinking": response.thinking,
                "agent": self.orchestrator.current_agent.name if self.orchestrator.current_agent else "unknown",
                "tool_calls": response.tool_calls,
                "tool_results": [r.to_dict() for r in response.tool_results],
                "metadata": response.metadata
            }
        except Exception as e:
            logger.error(f"Chat error: {e}")
            return {"content": f"Error: {e}", "agent": "error"}
    
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
