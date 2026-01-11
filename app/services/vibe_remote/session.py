"""
Session Manager - Track user sessions for vibe_remote.

Manages working directories and agent state per user/chat.
"""

import os
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

from app.core.logger import Logger

logger = Logger("VibeSession")


@dataclass
class VibeSession:
    """Session state for a user/chat."""
    user_id: int
    chat_id: int
    working_path: str
    agent: str = "gemini"
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    metadata: Dict = field(default_factory=dict)
    
    @property
    def session_id(self) -> str:
        """Generate unique session ID."""
        return f"{self.user_id}:{self.chat_id}"
    
    def touch(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = time.time()


class SessionManager:
    """Manage vibe_remote sessions."""
    
    DEFAULT_CWD = os.path.expanduser("~/vibe-workspace")
    SESSION_TIMEOUT = 86400  # 24 hours
    
    def __init__(self, default_cwd: Optional[str] = None):
        self._sessions: Dict[str, VibeSession] = {}
        self._default_cwd = default_cwd or self.DEFAULT_CWD
        
        # Ensure default workspace exists
        os.makedirs(self._default_cwd, exist_ok=True)
    
    def get_session(self, user_id: int, chat_id: int) -> Optional[VibeSession]:
        """Get existing session."""
        key = f"{user_id}:{chat_id}"
        session = self._sessions.get(key)
        
        if session:
            # Check timeout
            if time.time() - session.last_activity > self.SESSION_TIMEOUT:
                self._sessions.pop(key, None)
                return None
            session.touch()
        
        return session
    
    def get_or_create_session(
        self,
        user_id: int,
        chat_id: int,
        agent: str = "gemini"
    ) -> VibeSession:
        """Get or create session for user/chat."""
        session = self.get_session(user_id, chat_id)
        if session:
            return session
        
        # Create new session with user-specific workspace
        working_path = os.path.join(self._default_cwd, f"user_{user_id}")
        os.makedirs(working_path, exist_ok=True)
        
        session = VibeSession(
            user_id=user_id,
            chat_id=chat_id,
            working_path=working_path,
            agent=agent
        )
        
        self._sessions[session.session_id] = session
        logger.info(f"Created session {session.session_id} in {working_path}")
        
        return session
    
    def set_working_path(self, user_id: int, chat_id: int, path: str) -> bool:
        """Set working directory for session."""
        session = self.get_session(user_id, chat_id)
        if not session:
            return False
        
        # Resolve and validate path
        resolved = os.path.abspath(os.path.expanduser(path))
        
        # Create if doesn't exist
        if not os.path.exists(resolved):
            try:
                os.makedirs(resolved, exist_ok=True)
            except Exception as e:
                logger.error(f"Failed to create directory: {e}")
                return False
        
        if not os.path.isdir(resolved):
            return False
        
        session.working_path = resolved
        session.touch()
        logger.info(f"Session {session.session_id} cwd -> {resolved}")
        
        return True
    
    def set_agent(self, user_id: int, chat_id: int, agent: str) -> bool:
        """Set agent for session."""
        session = self.get_session(user_id, chat_id)
        if not session:
            return False
        
        session.agent = agent
        session.touch()
        return True
    
    def clear_session(self, user_id: int, chat_id: int) -> bool:
        """Clear session state."""
        key = f"{user_id}:{chat_id}"
        if key in self._sessions:
            del self._sessions[key]
            logger.info(f"Cleared session {key}")
            return True
        return False
    
    def cleanup_expired(self) -> int:
        """Remove expired sessions."""
        now = time.time()
        expired = [
            key for key, session in self._sessions.items()
            if now - session.last_activity > self.SESSION_TIMEOUT
        ]
        
        for key in expired:
            del self._sessions[key]
        
        if expired:
            logger.info(f"Cleaned up {len(expired)} expired sessions")
        
        return len(expired)
    
    def get_stats(self) -> Dict:
        """Get session statistics."""
        return {
            "active_sessions": len(self._sessions),
            "default_cwd": self._default_cwd
        }
