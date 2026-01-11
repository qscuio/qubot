"""
Vibe Remote Service - Main orchestrator for CLI agent control.

Provides a unified interface for agent management, Git operations,
and GitHub Actions integration.
"""

import os
from typing import Any, Callable, Dict, Optional

from app.core.config import settings
from app.core.logger import Logger

from app.services.vibe_remote.agents.base import AgentRequest, AgentMessage, BaseCLIAgent
from app.services.vibe_remote.agents.claude_agent import ClaudeAgent
from app.services.vibe_remote.agents.gemini_agent import GeminiAgent
from app.services.vibe_remote.agents.codex_agent import CodexAgent
from app.services.vibe_remote.router import AgentRouter
from app.services.vibe_remote.session import SessionManager, VibeSession
from app.services.vibe_remote.git_ops import GitOperations
from app.services.vibe_remote.github_actions import GitHubActionsClient

logger = Logger("VibeRemoteService")


class VibeRemoteService:
    """Main service for vibe_remote functionality."""
    
    def __init__(self):
        self._agents: Dict[str, BaseCLIAgent] = {}
        self._router: Optional[AgentRouter] = None
        self._session_manager: Optional[SessionManager] = None
        self._git_ops: Optional[GitOperations] = None
        self._github_actions: Optional[GitHubActionsClient] = None
        self._is_initialized = False
    
    def init(self) -> None:
        """Initialize the service."""
        if self._is_initialized:
            return
        
        # Determine default working directory
        default_cwd = getattr(settings, "VIBE_DEFAULT_CWD", None)
        if not default_cwd:
            default_cwd = os.path.expanduser("~/vibe-workspace")
        
        # Initialize components
        self._session_manager = SessionManager(default_cwd)
        
        # Initialize router
        default_agent = getattr(settings, "VIBE_DEFAULT_AGENT", "gemini")
        self._router = AgentRouter(global_default=default_agent)
        
        # Initialize agents
        self._agents = {
            "claude": ClaudeAgent(self),
            "gemini": GeminiAgent(self),
            "codex": CodexAgent(self),
        }
        
        # Initialize Git operations
        ssh_key = getattr(settings, "GIT_SSH_KEY_PATH", None)
        self._git_ops = GitOperations(ssh_key)
        
        # Initialize GitHub Actions
        self._github_actions = GitHubActionsClient()
        
        self._is_initialized = True
        
        # Log available agents
        available = [name for name, agent in self._agents.items() if agent.is_available()]
        logger.info(f"VibeRemoteService initialized. Available agents: {available}")
    
    @property
    def router(self) -> AgentRouter:
        """Get agent router."""
        if not self._router:
            self.init()
        return self._router
    
    @property
    def session_manager(self) -> SessionManager:
        """Get session manager."""
        if not self._session_manager:
            self.init()
        return self._session_manager
    
    @property
    def git(self) -> GitOperations:
        """Get Git operations."""
        if not self._git_ops:
            self.init()
        return self._git_ops
    
    @property
    def github_actions(self) -> GitHubActionsClient:
        """Get GitHub Actions client."""
        if not self._github_actions:
            self.init()
        return self._github_actions
    
    def get_agent(self, name: str) -> Optional[BaseCLIAgent]:
        """Get agent by name."""
        if not self._is_initialized:
            self.init()
        return self._agents.get(name)
    
    def get_available_agents(self) -> Dict[str, bool]:
        """Get availability status of all agents."""
        if not self._is_initialized:
            self.init()
        return {name: agent.is_available() for name, agent in self._agents.items()}
    
    async def handle_message(
        self,
        user_id: int,
        chat_id: int,
        message: str,
        reply_callback: Optional[Callable[[str], Any]] = None
    ) -> None:
        """Handle a user message by routing to the appropriate agent."""
        if not self._is_initialized:
            self.init()
        
        # Get or create session
        session = self.session_manager.get_or_create_session(user_id, chat_id)
        
        # Resolve agent
        agent_name = self.router.resolve(chat_id, user_id)
        if agent_name != session.agent:
            session.agent = agent_name
        
        agent = self.get_agent(agent_name)
        if not agent:
            if reply_callback:
                await reply_callback(f"❌ Unknown agent: {agent_name}")
            return
        
        if not agent.is_available():
            if reply_callback:
                await reply_callback(f"❌ Agent `{agent_name}` is not available. Check CLI installation.")
            return
        
        # Create request
        request = AgentRequest(
            user_id=user_id,
            chat_id=chat_id,
            message=message,
            working_path=session.working_path,
            session_id=session.session_id,
            reply_callback=reply_callback
        )
        
        # Process message
        await agent.handle_message(request)
    
    async def handle_stop(
        self,
        user_id: int,
        chat_id: int
    ) -> bool:
        """Stop the current task."""
        session = self.session_manager.get_session(user_id, chat_id)
        if not session:
            return False
        
        agent = self.get_agent(session.agent)
        if not agent:
            return False
        
        request = AgentRequest(
            user_id=user_id,
            chat_id=chat_id,
            message="",
            working_path=session.working_path,
            session_id=session.session_id
        )
        
        return await agent.handle_stop(request)
    
    async def clear_session(self, user_id: int, chat_id: int) -> bool:
        """Clear session state."""
        session = self.session_manager.get_session(user_id, chat_id)
        if not session:
            return False
        
        # Clear agent state
        agent = self.get_agent(session.agent)
        if agent:
            await agent.clear_sessions(session.session_id)
        
        # Clear session
        return self.session_manager.clear_session(user_id, chat_id)
    
    def set_agent(self, user_id: int, chat_id: int, agent_name: str) -> bool:
        """Set agent for session."""
        if agent_name not in self._agents:
            return False
        
        # Update router preference
        self.router.set_user_agent(user_id, agent_name)
        
        # Update session
        return self.session_manager.set_agent(user_id, chat_id, agent_name)
    
    def set_cwd(self, user_id: int, chat_id: int, path: str) -> bool:
        """Set working directory for session."""
        return self.session_manager.set_working_path(user_id, chat_id, path)
    
    def get_session(self, user_id: int, chat_id: int) -> Optional[VibeSession]:
        """Get session info."""
        return self.session_manager.get_session(user_id, chat_id)
    
    def get_status(self) -> Dict:
        """Get service status."""
        if not self._is_initialized:
            self.init()
        
        return {
            "initialized": self._is_initialized,
            "agents": self.get_available_agents(),
            "sessions": self.session_manager.get_stats(),
            "github_available": self.github_actions.is_available()
        }


# Singleton instance
vibe_remote_service = VibeRemoteService()
