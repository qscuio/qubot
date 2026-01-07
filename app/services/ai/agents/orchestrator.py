"""
Agent orchestrator for managing multi-agent execution and tool loops.
"""

from typing import Dict, Any, List, Optional
from app.services.ai.agents.base import Agent, AgentResponse
from app.services.ai.agents.registry import agent_registry
from app.core.logger import Logger

logger = Logger("AgentOrchestrator")


class AgentOrchestrator:
    """
    Orchestrates agent execution, including:
    - Agent selection and switching
    - Tool execution loops
    - Conversation state management
    """
    
    def __init__(self, provider=None):
        self.provider = provider
        self.current_agent: Optional[Agent] = None
        self.execution_history: List[Dict[str, Any]] = []
    
    def set_provider(self, provider) -> None:
        """Set the AI provider for agent calls."""
        self.provider = provider
    
    def get_agent(self, name: str = None) -> Optional[Agent]:
        """Get an agent by name, or the default agent."""
        if name:
            agent = agent_registry.get(name)
            if agent:
                return agent
        return agent_registry.get_default()
    
    def list_agents(self) -> List[Dict[str, str]]:
        """List all available agents."""
        return agent_registry.get_agent_info()
    
    async def run(
        self,
        message: str,
        agent_name: str = None,
        history: List[Dict[str, str]] = None,
        model: str = None,
        max_tool_calls: int = 10
    ) -> AgentResponse:
        """
        Run an agent with the given message.
        
        Args:
            message: User message
            agent_name: Name of agent to use (default: chat)
            history: Conversation history
            model: Model override
            max_tool_calls: Maximum tool call iterations
            
        Returns:
            AgentResponse with content and tool execution details
        """
        agent = self.get_agent(agent_name)
        if not agent:
            return AgentResponse(
                content=f"Agent '{agent_name}' not found. Available: {agent_registry.list_names()}",
                metadata={"error": "agent_not_found"}
            )
        
        self.current_agent = agent
        
        if not self.provider:
            return AgentResponse(
                content="No AI provider configured",
                metadata={"error": "no_provider"}
            )
        
        logger.info(f"Running agent '{agent.name}' with {len(agent.tools)} tools")
        
        try:
            response = await agent.run(
                message=message,
                history=history,
                max_tool_calls=max_tool_calls,
                provider=self.provider,
                model=model
            )
            
            # Log execution
            self.execution_history.append({
                "agent": agent.name,
                "message": message[:100],
                "tool_calls": len(response.tool_calls),
                "success": not response.metadata.get("error")
            })
            
            return response
            
        except Exception as e:
            logger.error(f"Orchestrator error: {e}")
            return AgentResponse(
                content=f"Agent execution failed: {e}",
                metadata={"error": str(e)}
            )
    
    async def run_with_routing(
        self,
        message: str,
        history: List[Dict[str, str]] = None,
        model: str = None
    ) -> AgentResponse:
        """
        Automatically route to the best agent based on the message.
        This is a simple keyword-based router; could be enhanced with AI classification.
        """
        agent_name = self._route_message(message)
        return await self.run(
            message=message,
            agent_name=agent_name,
            history=history,
            model=model
        )
    
    def _route_message(self, message: str) -> str:
        """
        Simple keyword-based routing to determine best agent.
        Can be enhanced with AI-based classification.
        """
        msg_lower = message.lower()
        
        # Research indicators
        if any(kw in msg_lower for kw in ["search", "find", "research", "look up", "what is", "who is"]):
            return "research"
        
        # Code indicators
        if any(kw in msg_lower for kw in ["code", "function", "class", "bug", "error", "implement", "python", "javascript"]):
            return "code"
        
        # DevOps indicators
        if any(kw in msg_lower for kw in ["github", "repo", "issue", "pr", "cloudflare", "dns", "deploy", "worker"]):
            return "devops"
        
        # Writing indicators
        if any(kw in msg_lower for kw in ["write", "article", "blog", "document", "essay", "draft"]):
            return "writer"
        
        # Default to chat
        return "chat"
    
    def get_execution_summary(self) -> Dict[str, Any]:
        """Get a summary of recent executions."""
        if not self.execution_history:
            return {"total": 0, "by_agent": {}}
        
        by_agent = {}
        for exec in self.execution_history:
            agent = exec["agent"]
            if agent not in by_agent:
                by_agent[agent] = 0
            by_agent[agent] += 1
        
        return {
            "total": len(self.execution_history),
            "by_agent": by_agent,
            "recent": self.execution_history[-5:]
        }


# Global orchestrator instance
orchestrator = AgentOrchestrator()
