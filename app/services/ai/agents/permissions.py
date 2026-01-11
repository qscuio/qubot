"""
Agent permission system for tool access control.

Ported from opencode's permission system. Controls which tools each agent can use.
"""

from typing import Dict, List, Set, Any
import fnmatch


# Permission values: "allow", "deny", "ask"
# Pattern matching uses fnmatch glob patterns

AGENT_PERMISSIONS: Dict[str, Dict[str, Any]] = {
    # Build agent - full development access
    "build": {
        "*": "allow",
        "read": {
            "*": "allow",
            "*.env": "deny",        # No reading env files
            "*.env.*": "deny",      # No reading env.local etc
            "*.env.example": "allow",  # Examples are ok
        },
    },
    
    # Plan agent - read-only analysis
    "plan": {
        "*": "allow",
        "file_write": {
            "*": "deny",
            ".ai/plans/*.md": "allow",  # Can only write to plans dir
        },
        "file_edit": {
            "*": "deny",
        },
        "bash": {
            "*": "deny",  # No shell commands that could modify
            "git status": "allow",
            "git log*": "allow",
            "git diff*": "allow",
            "ls*": "allow",
        },
    },
    
    # Explore agent - search only
    "explore": {
        "*": "deny",
        "file_read": "allow",
        "file_list": "allow",
        "file_search": "allow",
        "web_search": "allow",
        "fetch_url": "allow",
    },
    
    # Chat agent - all tools allowed
    "chat": {
        "*": "allow",
    },
    
    # Research agent - web and read access
    "research": {
        "*": "allow",
    },
    
    # Code agent - file operations
    "code": {
        "*": "allow",
        "read": {
            "*": "allow",
            "*.env": "deny",
            "*.env.*": "deny",
        },
    },
    
    # DevOps agent - github and cloudflare
    "devops": {
        "*": "allow",
    },
    
    # Writer agent - research and write
    "writer": {
        "*": "allow",
    },
    
    # Summary agent - no tools
    "summary": {
        "*": "deny",
    },
}


def check_permission(
    agent_name: str,
    tool_name: str,
    resource: str = None
) -> str:
    """
    Check if an agent has permission to use a tool.
    
    Args:
        agent_name: Name of the agent
        tool_name: Name of the tool
        resource: Optional resource path (for file operations)
        
    Returns:
        "allow", "deny", or "ask"
    """
    permissions = AGENT_PERMISSIONS.get(agent_name, {"*": "allow"})
    
    # Check specific tool permission
    tool_perm = permissions.get(tool_name, permissions.get("*", "allow"))
    
    # If tool permission is a dict (has resource patterns)
    if isinstance(tool_perm, dict) and resource:
        for pattern, action in tool_perm.items():
            if pattern == "*":
                continue
            if fnmatch.fnmatch(resource, pattern):
                return action
        return tool_perm.get("*", "allow")
    
    # Simple allow/deny string
    if isinstance(tool_perm, str):
        return tool_perm
    
    return "allow"


def get_allowed_tools(agent_name: str, all_tools: List[str]) -> List[str]:
    """
    Filter tools to only those allowed for an agent.
    
    Args:
        agent_name: Name of the agent
        all_tools: List of all available tool names
        
    Returns:
        List of tool names the agent can use
    """
    allowed = []
    for tool_name in all_tools:
        if check_permission(agent_name, tool_name) != "deny":
            allowed.append(tool_name)
    return allowed


def get_denied_tools(agent_name: str, all_tools: List[str]) -> List[str]:
    """
    Get list of tools denied for an agent.
    
    Args:
        agent_name: Name of the agent
        all_tools: List of all available tool names
        
    Returns:
        List of tool names the agent cannot use
    """
    denied = []
    for tool_name in all_tools:
        if check_permission(agent_name, tool_name) == "deny":
            denied.append(tool_name)
    return denied
