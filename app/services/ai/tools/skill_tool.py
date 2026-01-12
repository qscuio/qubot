"""
Skill Tool - OpenCode-style on-demand skill loading.

Instead of injecting full skill content into every prompt, this tool
allows agents to see available skills and load them on-demand.
"""

from app.services.ai.tools.base import Tool, ToolResult
from app.services.ai.tools.registry import register_tool
from app.services.ai.skills import skill_registry
from app.core.logger import Logger

logger = Logger("SkillTool")


class SkillTool(Tool):
    """
    Load skill instructions on-demand.
    
    Agent sees available skills in tool description, then calls this
    tool to load full instructions when needed.
    """
    
    @property
    def name(self) -> str:
        return "skill"
    
    @property
    def description(self) -> str:
        # Build dynamic description with available skills
        skill_registry.load_skills()
        skills = skill_registry.list_all()
        
        if not skills:
            return "Load skill instructions. No skills available."
        
        # Format: <available_skills><skill><name>X</name><description>Y</description></skill>...</available_skills>
        skill_list = "\n".join(
            f'  <skill><name>{s.name}</name><description>{s.description}</description></skill>'
            for s in skills
        )
        
        return f"""Load skill instructions by name. Use when the task matches a skill.

<available_skills>
{skill_list}
</available_skills>"""
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the skill to load"
                }
            },
            "required": ["name"]
        }
    
    async def execute(self, name: str) -> ToolResult:
        """Load a skill's full instructions."""
        skill = skill_registry.get(name)
        
        if not skill:
            available = ", ".join(skill_registry.list_names())
            return ToolResult(
                success=False,
                output=f"Skill '{name}' not found. Available: {available}"
            )
        
        logger.info(f"📚 Loaded skill: {name}")
        
        return ToolResult(
            success=True,
            output=f"""# Skill: {skill.name}

{skill.instructions}"""
        )


def register_skill_tool():
    """Register the skill tool."""
    register_tool(SkillTool())
    logger.info("Registered skill tool")
