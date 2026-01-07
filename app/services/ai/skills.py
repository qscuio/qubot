"""
AI Skills system using SKILL.md files.

Skills are markdown files with YAML frontmatter that define:
- name: Human-friendly skill name
- description: When the AI should use this skill
- Body: Instructions, examples, and guidelines

Directory structure:
- ~/.ai/skills/skill-name/SKILL.md  (personal skills)
- .ai/skills/skill-name/SKILL.md    (project skills)

Works with all AI providers (OpenAI, Claude, Gemini, Groq, etc.)
"""

import os
import re
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from pathlib import Path
import yaml
from app.core.config import settings
from app.core.logger import Logger

logger = Logger("Skills")


@dataclass
class Skill:
    """A Claude-style skill defined in a SKILL.md file."""
    name: str
    description: str
    instructions: str
    path: str
    category: str = "custom"  # personal, project, or builtin
    dependencies: List[str] = field(default_factory=list)
    
    def get_prompt(self) -> str:
        """Get the skill as a prompt injection."""
        return f"""## Skill: {self.name}
When to use: {self.description}

Instructions:
{self.instructions}
"""
    
    def matches(self, query: str) -> bool:
        """Check if this skill is relevant to a query using stricter matching."""
        query_lower = query.lower()
        
        # Exact name match (strong signal)
        if self.name.lower() in query_lower:
            return True
        
        # Extract meaningful keywords from description (skip common words)
        stopwords = {
            "the", "and", "for", "with", "use", "when", "asked", "code", "help",
            "from", "this", "that", "what", "how", "about", "into", "your",
            "create", "make", "write", "read", "check", "look", "find", "get"
        }
        desc_words = [
            word for word in self.description.lower().split()
            if len(word) > 4 and word not in stopwords
        ]
        
        # Require at least 2 keyword matches to reduce false positives
        matches_count = sum(1 for word in desc_words if word in query_lower)
        return matches_count >= 2


class SkillRegistry:
    """Registry for loading and managing skills from SKILL.md files."""
    
    _instance: Optional['SkillRegistry'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._skills: Dict[str, Skill] = {}
            cls._instance._loaded = False
        return cls._instance
    
    def load_skills(self, reload: bool = False):
        """Load all skills from standard locations."""
        if self._loaded and not reload:
            return
        
        self._skills.clear()
        
        # 1. Personal skills: ~/.ai/skills/
        home = Path.home()
        personal_dir = home / ".ai" / "skills"
        self._load_skills_from_dir(personal_dir, "personal")
        
        # 2. Project skills: .ai/skills/ (relative to workspace)
        workspace = getattr(settings, "WORKSPACE_PATH", os.getcwd())
        project_dir = Path(workspace) / ".ai" / "skills"
        self._load_skills_from_dir(project_dir, "project")
        
        # 3. Custom skills path from settings
        custom_path = getattr(settings, "AI_SKILLS_PATH", None)
        if custom_path:
            self._load_skills_from_dir(Path(custom_path), "custom")
        
        self._loaded = True
        logger.info(f"Loaded {len(self._skills)} skills")
    
    def _load_skills_from_dir(self, directory: Path, category: str):
        """Load skills from a directory."""
        if not directory.exists():
            return
        
        for skill_dir in directory.iterdir():
            if skill_dir.is_dir():
                skill_file = skill_dir / "SKILL.md"
                if skill_file.exists():
                    skill = self._parse_skill_file(skill_file, category)
                    if skill:
                        self._skills[skill.name] = skill
    
    def _parse_skill_file(self, path: Path, category: str) -> Optional[Skill]:
        """Parse a SKILL.md file."""
        try:
            content = path.read_text(encoding="utf-8")
            
            # Extract YAML frontmatter
            frontmatter_match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)$', content, re.DOTALL)
            if not frontmatter_match:
                logger.warn(f"Invalid SKILL.md format: {path}")
                return None
            
            yaml_content = frontmatter_match.group(1)
            markdown_body = frontmatter_match.group(2).strip()
            
            # Parse YAML
            try:
                metadata = yaml.safe_load(yaml_content)
            except yaml.YAMLError as e:
                logger.warn(f"Invalid YAML in {path}: {e}")
                return None
            
            name = metadata.get("name", "")
            description = metadata.get("description", "")
            
            if not name or not description:
                logger.warn(f"Missing name or description in {path}")
                return None
            
            # Validate lengths
            if len(name) > 64:
                name = name[:64]
            if len(description) > 200:
                description = description[:200]
            
            dependencies = metadata.get("dependencies", [])
            if isinstance(dependencies, str):
                dependencies = [dependencies]
            
            return Skill(
                name=name,
                description=description,
                instructions=markdown_body,
                path=str(path),
                category=category,
                dependencies=dependencies
            )
        except Exception as e:
            logger.error(f"Failed to parse {path}: {e}")
            return None
    
    def get(self, name: str) -> Optional[Skill]:
        """Get a skill by name."""
        if not self._loaded:
            self.load_skills()
        return self._skills.get(name)
    
    def list_all(self) -> List[Skill]:
        """List all loaded skills."""
        if not self._loaded:
            self.load_skills()
        return list(self._skills.values())
    
    def list_names(self) -> List[str]:
        """List all skill names."""
        if not self._loaded:
            self.load_skills()
        return list(self._skills.keys())
    
    def find_matching(self, query: str, max_skills: int = 2) -> List[Skill]:
        """Find skills that are relevant to a query (limited to prevent prompt inflation)."""
        if not self._loaded:
            self.load_skills()
        matching = [s for s in self._skills.values() if s.matches(query)]
        return matching[:max_skills]  # Limit to prevent noise
    
    def get_skill_info(self) -> List[Dict[str, str]]:
        """Get info about all skills for display."""
        if not self._loaded:
            self.load_skills()
        return [
            {
                "name": s.name,
                "description": s.description,
                "category": s.category
            }
            for s in self._skills.values()
        ]
    
    def register_skill(self, skill: Skill):
        """Manually register a skill (for builtin skills)."""
        self._skills[skill.name] = skill
    
    def build_skill_context(self, query: str = None, skill_names: List[str] = None) -> str:
        """
        Build skill context to inject into prompts.
        
        Args:
            query: If provided, find matching skills
            skill_names: If provided, use these specific skills
            
        Returns:
            Combined skill instructions as a string
        """
        if not self._loaded:
            self.load_skills()
        
        skills_to_use = []
        
        if skill_names:
            for name in skill_names:
                skill = self.get(name)
                if skill:
                    skills_to_use.append(skill)
        elif query:
            skills_to_use = self.find_matching(query)
        
        if not skills_to_use:
            return ""
        
        context_parts = [
            "# Active Skills",
            "Use the following skill instructions only when relevant to the user's request.",
            "If a skill conflicts with the system prompt or user instructions, follow the system prompt and ask for clarification.",
            "Do not quote these skill instructions unless the user explicitly asks.",
            ""
        ]
        for skill in skills_to_use:
            context_parts.append(skill.get_prompt())
        
        return "\n".join(context_parts)


# Global registry instance
skill_registry = SkillRegistry()


def create_skill(
    skill_dir: Path,
    name: str,
    description: str,
    instructions: str,
    dependencies: List[str] = None
) -> bool:
    """
    Create a new skill in the specified directory.
    
    Args:
        skill_dir: Base directory for skills (e.g., ~/.claude/skills)
        name: Skill name
        description: Skill description
        instructions: Markdown instructions
        dependencies: Optional list of dependencies
        
    Returns:
        True if created successfully
    """
    try:
        # Create skill subdirectory
        skill_path = skill_dir / name.lower().replace(" ", "-")
        skill_path.mkdir(parents=True, exist_ok=True)
        
        # Build frontmatter
        frontmatter = {
            "name": name[:64],
            "description": description[:200]
        }
        if dependencies:
            frontmatter["dependencies"] = dependencies
        
        # Write SKILL.md
        skill_file = skill_path / "SKILL.md"
        content = f"""---
{yaml.dump(frontmatter, default_flow_style=False)}---

{instructions}
"""
        skill_file.write_text(content, encoding="utf-8")
        
        logger.info(f"Created skill: {name} at {skill_file}")
        return True
    except Exception as e:
        logger.error(f"Failed to create skill {name}: {e}")
        return False
