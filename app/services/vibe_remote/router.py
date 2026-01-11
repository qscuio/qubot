"""
Agent Router - Routes messages to the appropriate CLI agent.

Supports per-channel routing configuration via YAML/JSON.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class ChannelRoute:
    """Route configuration for a channel."""
    default: str = "gemini"
    overrides: Dict[str, str] = field(default_factory=dict)


class AgentRouter:
    """Resolve which agent should handle a message."""
    
    VALID_AGENTS = {"claude", "gemini", "codex"}
    
    def __init__(
        self,
        routes: Dict[str, ChannelRoute] = None,
        global_default: str = "gemini"
    ):
        self.routes = routes or {}
        self.global_default = global_default
        self._user_overrides: Dict[int, str] = {}  # user_id -> agent
    
    @classmethod
    def from_file(cls, file_path: Optional[str], global_default: str = "gemini") -> "AgentRouter":
        """Load router configuration from YAML/JSON file."""
        routes: Dict[str, ChannelRoute] = {}
        
        if file_path and os.path.exists(file_path):
            try:
                data = cls._load_file(file_path)
                global_default = data.get("default", global_default)
                
                for key, value in data.items():
                    if key == "default" or not isinstance(value, dict):
                        continue
                    
                    routes[key] = ChannelRoute(
                        default=value.get("default", global_default),
                        overrides=value.get("overrides", {}) or {}
                    )
                
                logger.info(f"Loaded agent routes from {file_path}")
            except Exception as e:
                logger.error(f"Failed to load agent routes: {e}")
        
        return cls(routes, global_default)
    
    @staticmethod
    def _load_file(path: str) -> Dict:
        """Load YAML or JSON file."""
        _, ext = os.path.splitext(path)
        
        if ext.lower() in {".yaml", ".yml"}:
            try:
                import yaml
            except ImportError:
                raise RuntimeError("PyYAML required for YAML config files")
            with open(path, "r") as f:
                return yaml.safe_load(f) or {}
        
        with open(path, "r") as f:
            return json.load(f)
    
    def resolve(self, chat_id: int, user_id: Optional[int] = None) -> str:
        """Resolve which agent to use for a given chat/user."""
        # Check user override first
        if user_id and user_id in self._user_overrides:
            return self._user_overrides[user_id]
        
        # Check channel route
        chat_key = str(chat_id)
        for platform_routes in self.routes.values():
            if chat_key in platform_routes.overrides:
                return platform_routes.overrides[chat_key]
        
        return self.global_default
    
    def set_user_agent(self, user_id: int, agent: str) -> bool:
        """Set agent preference for a user."""
        if agent not in self.VALID_AGENTS:
            return False
        self._user_overrides[user_id] = agent
        return True
    
    def get_user_agent(self, user_id: int) -> Optional[str]:
        """Get agent preference for a user."""
        return self._user_overrides.get(user_id)
    
    def clear_user_agent(self, user_id: int) -> None:
        """Clear user agent preference."""
        self._user_overrides.pop(user_id, None)
