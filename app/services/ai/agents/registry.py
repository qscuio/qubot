"""
Agent registry for managing available agents.
"""

from typing import Dict, List, Optional
from app.services.ai.agents.base import Agent
from app.core.logger import Logger

logger = Logger("AgentRegistry")


class AgentRegistry:
    """Registry for managing available agents."""
    
    _instance: Optional['AgentRegistry'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._agents: Dict[str, Agent] = {}
        return cls._instance
    
    def register(self, agent: Agent) -> None:
        """Register an agent."""
        self._agents[agent.name] = agent
        logger.debug(f"Registered agent: {agent.name}")
    
    def unregister(self, name: str) -> bool:
        """Unregister an agent by name."""
        if name in self._agents:
            del self._agents[name]
            return True
        return False
    
    def get(self, name: str) -> Optional[Agent]:
        """Get an agent by name."""
        return self._agents.get(name)
    
    def get_default(self) -> Optional[Agent]:
        """Get the default agent (chat)."""
        return self._agents.get("chat") or (
            list(self._agents.values())[0] if self._agents else None
        )
    
    def list_all(self) -> List[Agent]:
        """List all registered agents."""
        return list(self._agents.values())
    
    def list_names(self) -> List[str]:
        """List all agent names."""
        return list(self._agents.keys())
    
    def get_agent_info(self) -> List[Dict[str, str]]:
        """Get info about all agents for display."""
        return [
            {"name": a.name, "description": a.description}
            for a in self._agents.values()
        ]


# Global registry instance
agent_registry = AgentRegistry()


def register_agent(agent: Agent) -> Agent:
    """Register an agent with the registry."""
    agent_registry.register(agent)
    return agent
