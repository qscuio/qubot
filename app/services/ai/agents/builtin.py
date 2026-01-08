"""
Built-in agents: Chat, Research, Code, and DevOps agents.
"""

import json
from typing import List, Dict, Any, Optional
from app.services.ai.agents.base import Agent, AgentResponse
from app.services.ai.agents.registry import register_agent
from app.services.ai.tools.base import ToolResult
from app.services.ai.skills import skill_registry
from app.core.config import settings
from app.core.logger import Logger

logger = Logger("BuiltinAgents")


class BaseToolAgent(Agent):
    """Base class for agents that use tools with provider integration."""
    
    async def run(
        self,
        message: str,
        history: List[Dict[str, str]] = None,
        max_tool_calls: int = 10,
        provider=None,
        model: str = None,
        skill_names: List[str] = None
    ) -> AgentResponse:
        """
        Run the agent with tool calling loop.
        
        Args:
            message: User message
            history: Conversation history
            max_tool_calls: Maximum tool call iterations
            provider: AI provider to use
            model: Model override
            skill_names: Specific skills to activate (optional)
        """
        if not provider:
            return AgentResponse(
                content="No AI provider configured",
                metadata={"error": "no_provider"}
            )
        
        messages = self.build_messages(message, history)
        tool_schemas = self.get_tool_schemas() if self._tools else None
        
        # Build system prompt with skills
        system_prompt = self._build_system_prompt_with_skills(message, skill_names)
        
        # Debug logging - show full request (no truncation)
        logger.debug(f"📋 SYSTEM PROMPT ({len(system_prompt)} chars):\n{system_prompt}")
        logger.debug(f"📨 MESSAGES ({len(messages)} msgs):\n{json.dumps(messages, indent=2, ensure_ascii=False)}")
        logger.debug(f"🔧 TOOLS ({len(tool_schemas) if tool_schemas else 0}): {[t['function']['name'] for t in tool_schemas] if tool_schemas else []}")
        
        all_tool_calls = []
        all_tool_results = []
        thinking = ""
        active_skills = []
        
        loop_count = 0
        while loop_count < max_tool_calls:
            loop_count += 1
            
            try:
                # Call provider with tools
                if tool_schemas and hasattr(provider, 'call_with_tools'):
                    result = await provider.call_with_tools(
                        messages=messages,
                        model=model or getattr(provider, 'default_model', None),
                        system_prompt=system_prompt,  # Use computed prompt with skills
                        tools=tool_schemas
                    )
                else:
                    # Fallback to regular call
                    prompt = message if not history else messages[-1]["content"]
                    result = await provider.call(
                        prompt=prompt,
                        model=model or getattr(provider, 'default_model', None),
                        history=history or [],
                        context_prefix=system_prompt
                    )
                    logger.debug(f"📩 RESPONSE (no tools):\n{result.get('content', '')}")
                    return AgentResponse(
                        content=result.get("content", ""),
                        thinking=result.get("thinking", ""),
                        metadata={"provider": provider.name, "model": model}
                    )
                
                thinking += result.get("thinking", "")
                content = result.get("content", "")
                tool_calls = result.get("tool_calls", [])
                
                # Debug logging - show full response (no truncation)
                logger.debug(f"📩 RESPONSE (loop {loop_count}):\n{content}")
                logger.debug(f"🔧 TOOL CALLS:\n{json.dumps(tool_calls, indent=2, ensure_ascii=False)}")
                
                if not tool_calls:
                    # No more tool calls, return final response
                    return AgentResponse(
                        content=content,
                        thinking=thinking,
                        tool_calls=all_tool_calls,
                        tool_results=all_tool_results,
                        metadata={"provider": provider.name, "model": model, "loops": loop_count}
                    )
                
                # Execute tool calls
                for tool_call in tool_calls:
                    tool_name = tool_call.get("name", "")
                    tool_args = tool_call.get("arguments", {})
                    
                    if isinstance(tool_args, str):
                        try:
                            tool_args = json.loads(tool_args)
                        except:
                            tool_args = {}
                    
                    all_tool_calls.append({"name": tool_name, "arguments": tool_args})
                    
                    # Execute the tool
                    tool_result = await self.execute_tool(tool_name, **tool_args)
                    all_tool_results.append(tool_result)
                    
                    # Add tool result to messages
                    messages.append({
                        "role": "assistant",
                        "content": content,
                        "tool_calls": [tool_call]
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.get("id", tool_name),
                        "content": self.format_tool_result(tool_result)
                    })
                
            except Exception as e:
                logger.error(f"Agent run error: {e}")
                return AgentResponse(
                    content=f"Error during agent execution: {e}",
                    thinking=thinking,
                    tool_calls=all_tool_calls,
                    tool_results=all_tool_results,
                    metadata={"error": str(e)}
                )
        
        return AgentResponse(
            content="Maximum tool calls reached. Please refine your request.",
            thinking=thinking,
            tool_calls=all_tool_calls,
            tool_results=all_tool_results,
            metadata={"max_calls_reached": True}
        )
    
    def _build_system_prompt_with_skills(
        self,
        message: str,
        skill_names: List[str] = None
    ) -> str:
        """Build system prompt with matching skills injected."""
        base_prompt = self.system_prompt
        
        # Get skill context based on message or explicit skill names
        skill_context = skill_registry.build_skill_context(
            query=message if not skill_names else None,
            skill_names=skill_names
        )
        
        if skill_context:
            return f"{base_prompt}\n\n{skill_context}"
        return base_prompt


class ChatAgent(BaseToolAgent):
    """General conversational assistant with all available tools and smart skill matching."""
    
    def __init__(self):
        super().__init__()
        # Add all registered tools for maximum capability
        self.add_all_tools()
    
    @property
    def name(self) -> str:
        return "chat"
    
    @property
    def description(self) -> str:
        return "General-purpose AI assistant for conversations, questions, and tasks."
    
    @property
    def system_prompt(self) -> str:
        return """You are QuBot's professional AI assistant.

Mission:
- Deliver accurate, efficient help across questions, writing, analysis, and tasks.
- Use available tools when they improve accuracy or speed.

Operating principles:
- Be clear, concise, and correct; avoid speculation.
- Ask focused questions when key details are missing.
- State assumptions explicitly.
- Do not invent sources, tool results, or credentials.
- Match the user's tone without being overly casual.

Response style:
- Lead with the shortest complete answer.
- Use lists or steps when it improves clarity."""
    
    def _build_system_prompt_with_skills(
        self,
        message: str,
        skill_names: List[str] = None
    ) -> str:
        """Build system prompt with smart skill matching (up to 5 most relevant)."""
        base_prompt = self.system_prompt
        
        # Use score-based matching with higher limit for chat agent
        skill_context = skill_registry.build_skill_context(
            query=message if not skill_names else None,
            skill_names=skill_names,
            max_skills=5  # Allow more skills for general chat
        )
        
        if skill_context:
            return f"{base_prompt}\n\n{skill_context}"
        return base_prompt


class ResearchAgent(BaseToolAgent):
    """Agent specialized for web research and information synthesis."""
    
    def __init__(self):
        super().__init__()
        self.add_tools_by_name(["web_search", "fetch_url", "memory"])
    
    @property
    def name(self) -> str:
        return "research"
    
    @property
    def description(self) -> str:
        return "Research agent that searches the web and synthesizes information."
    
    @property
    def system_prompt(self) -> str:
        return """You are a research assistant with web search capabilities.

Workflow:
1. Clarify the research goal and constraints.
2. Use web_search to find sources, then fetch_url for details.
3. Cross-check key claims across multiple sources.
4. Synthesize findings and provide citations.

Guidelines:
- Always cite sources with URLs.
- Note dates and potential staleness.
- Separate facts from interpretation.
- Call out uncertainty or gaps explicitly."""


class CodeAgent(BaseToolAgent):
    """Agent specialized for programming assistance."""
    
    def __init__(self):
        super().__init__()
        self.add_tools_by_name(["file_read", "file_write", "file_list", "file_search", "calculator"])
    
    @property
    def name(self) -> str:
        return "code"
    
    @property
    def description(self) -> str:
        return "Programming assistant that can read, write, and analyze code files."
    
    @property
    def system_prompt(self) -> str:
        return """You are an expert programming assistant.

Capabilities:
- Read and analyze code files.
- Write and modify code.
- Search for files and patterns.
- Explain code and suggest improvements.
- Help debug issues.

Guidelines:
- Understand the existing behavior before changing it.
- Follow project conventions and keep diffs small.
- Prefer clear, tested code; suggest tests when relevant.
- Explain tradeoffs and risks for significant changes."""


class DevOpsAgent(BaseToolAgent):
    """Agent specialized for DevOps operations with GitHub and Cloudflare."""
    
    def __init__(self):
        super().__init__()
        self.add_tools_by_name([
            "github_repo", "github_issues", "github_pr", "github_file",
            "cloudflare_dns", "cloudflare_workers", "cloudflare_pages", "cloudflare_kv"
        ])
    
    @property
    def name(self) -> str:
        return "devops"
    
    @property
    def description(self) -> str:
        return "DevOps agent for GitHub and Cloudflare operations."
    
    @property
    def system_prompt(self) -> str:
        return """You are a DevOps assistant with access to GitHub and Cloudflare.

Capabilities:
- GitHub: view repos, issues, PRs, and files.
- Cloudflare: manage DNS, view Workers, Pages, and KV.

Guidelines:
- Default to read-only actions.
- Confirm before making changes.
- Summarize findings and risks clearly.
- Verify configurations before modifying them."""


class WriterAgent(BaseToolAgent):
    """Agent specialized for writing and content creation."""
    
    def __init__(self):
        super().__init__()
        self.add_tools_by_name(["web_search", "fetch_url", "memory"])
    
    @property
    def name(self) -> str:
        return "writer"
    
    @property
    def description(self) -> str:
        return "Writing assistant for creating articles, documentation, and content."
    
    @property
    def system_prompt(self) -> str:
        return """You are a professional writer and content creator.

Workflow:
- Identify audience, purpose, and constraints.
- Draft structured content with clear headings.
- Revise for clarity, tone, and factual accuracy.

Guidelines:
- Be direct and avoid fluff.
- Adapt tone and depth to the audience.
- Research facts before including them.
- Deliver clean, publish-ready prose."""


def register_builtin_agents():
    """Register all builtin agents with the registry."""
    register_agent(ChatAgent())
    register_agent(ResearchAgent())
    register_agent(CodeAgent())
    register_agent(DevOpsAgent())
    register_agent(WriterAgent())
    logger.info("Registered builtin agents")
