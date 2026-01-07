"""
File access tools for reading, writing, listing, and searching files.
"""

import os
import glob
from pathlib import Path
from typing import List
from app.services.ai.tools.base import Tool, ToolParameter, ToolResult
from app.services.ai.tools.registry import register_tool
from app.core.config import settings
from app.core.logger import Logger

logger = Logger("FileTools")


def is_path_allowed(path: str) -> bool:
    """Check if path is within allowed directories."""
    allowed_paths_str = getattr(settings, "AI_ALLOWED_PATHS", None)
    if not allowed_paths_str:
        # Default: allow /tmp, ~/.qubot, and current working directory
        allowed_paths = [
            "/tmp",
            os.path.expanduser("~/.qubot"),
            os.getcwd(),  # Include workspace/cwd
        ]
    else:
        allowed_paths = [p.strip() for p in allowed_paths_str.split(",")]
    
    abs_path = os.path.abspath(path)
    return any(abs_path.startswith(os.path.abspath(p)) for p in allowed_paths)


class FileReadTool(Tool):
    """Read file contents."""
    
    @property
    def name(self) -> str:
        return "file_read"
    
    @property
    def description(self) -> str:
        return "Read the contents of a file. Only works on allowed paths."
    
    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="path",
                type="string",
                description="Path to the file to read",
                required=True
            ),
            ToolParameter(
                name="max_lines",
                type="integer",
                description="Maximum lines to return (0 = all)",
                required=False,
                default=500
            )
        ]
    
    async def execute(self, **kwargs) -> ToolResult:
        path = kwargs.get("path", "")
        max_lines = kwargs.get("max_lines", 500)
        
        if not is_path_allowed(path):
            return ToolResult(success=False, output=None, error=f"Access denied: {path}")
        
        try:
            if not os.path.exists(path):
                return ToolResult(success=False, output=None, error="File not found")
            
            if not os.path.isfile(path):
                return ToolResult(success=False, output=None, error="Not a file")
            
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                if max_lines > 0:
                    lines = []
                    for i, line in enumerate(f):
                        if i >= max_lines:
                            break
                        lines.append(line)
                    content = "".join(lines)
                else:
                    content = f.read()
            
            return ToolResult(
                success=True,
                output=content,
                metadata={"path": path, "size": len(content)}
            )
        except Exception as e:
            logger.error(f"File read failed: {e}")
            return ToolResult(success=False, output=None, error=str(e))


class FileWriteTool(Tool):
    """Write content to a file."""
    
    @property
    def name(self) -> str:
        return "file_write"
    
    @property
    def description(self) -> str:
        return "Write content to a file. Creates parent directories if needed. Only works on allowed paths."
    
    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="path",
                type="string",
                description="Path to write to",
                required=True
            ),
            ToolParameter(
                name="content",
                type="string",
                description="Content to write",
                required=True
            ),
            ToolParameter(
                name="append",
                type="boolean",
                description="Append to file instead of overwriting",
                required=False,
                default=False
            )
        ]
    
    async def execute(self, **kwargs) -> ToolResult:
        path = kwargs.get("path", "")
        content = kwargs.get("content", "")
        append = kwargs.get("append", False)
        
        if not is_path_allowed(path):
            return ToolResult(success=False, output=None, error=f"Access denied: {path}")
        
        try:
            # Create parent directories
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            
            mode = "a" if append else "w"
            with open(path, mode, encoding="utf-8") as f:
                f.write(content)
            
            return ToolResult(
                success=True,
                output=f"Written {len(content)} bytes to {path}",
                metadata={"path": path, "size": len(content), "append": append}
            )
        except Exception as e:
            logger.error(f"File write failed: {e}")
            return ToolResult(success=False, output=None, error=str(e))


class FileListTool(Tool):
    """List directory contents."""
    
    @property
    def name(self) -> str:
        return "file_list"
    
    @property
    def description(self) -> str:
        return "List files and directories in a path. Only works on allowed paths."
    
    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="path",
                type="string",
                description="Directory path to list",
                required=True
            ),
            ToolParameter(
                name="recursive",
                type="boolean",
                description="List recursively",
                required=False,
                default=False
            ),
            ToolParameter(
                name="max_items",
                type="integer",
                description="Maximum items to return",
                required=False,
                default=100
            )
        ]
    
    async def execute(self, **kwargs) -> ToolResult:
        path = kwargs.get("path", "")
        recursive = kwargs.get("recursive", False)
        max_items = kwargs.get("max_items", 100)
        
        if not is_path_allowed(path):
            return ToolResult(success=False, output=None, error=f"Access denied: {path}")
        
        try:
            if not os.path.exists(path):
                return ToolResult(success=False, output=None, error="Path not found")
            
            if not os.path.isdir(path):
                return ToolResult(success=False, output=None, error="Not a directory")
            
            items = []
            if recursive:
                for root, dirs, files in os.walk(path):
                    for name in dirs + files:
                        if len(items) >= max_items:
                            break
                        full_path = os.path.join(root, name)
                        rel_path = os.path.relpath(full_path, path)
                        is_dir = os.path.isdir(full_path)
                        items.append({
                            "path": rel_path,
                            "type": "dir" if is_dir else "file",
                            "size": os.path.getsize(full_path) if not is_dir else None
                        })
                    if len(items) >= max_items:
                        break
            else:
                for name in os.listdir(path)[:max_items]:
                    full_path = os.path.join(path, name)
                    is_dir = os.path.isdir(full_path)
                    items.append({
                        "path": name,
                        "type": "dir" if is_dir else "file",
                        "size": os.path.getsize(full_path) if not is_dir else None
                    })
            
            return ToolResult(
                success=True,
                output=items,
                metadata={"path": path, "count": len(items)}
            )
        except Exception as e:
            logger.error(f"File list failed: {e}")
            return ToolResult(success=False, output=None, error=str(e))


class FileSearchTool(Tool):
    """Search for files by pattern."""
    
    @property
    def name(self) -> str:
        return "file_search"
    
    @property
    def description(self) -> str:
        return "Search for files matching a glob pattern. Only works on allowed paths."
    
    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="path",
                type="string",
                description="Base directory to search in",
                required=True
            ),
            ToolParameter(
                name="pattern",
                type="string",
                description="Glob pattern (e.g., '*.py', '**/*.json')",
                required=True
            ),
            ToolParameter(
                name="max_results",
                type="integer",
                description="Maximum results to return",
                required=False,
                default=50
            )
        ]
    
    async def execute(self, **kwargs) -> ToolResult:
        path = kwargs.get("path", "")
        pattern = kwargs.get("pattern", "*")
        max_results = kwargs.get("max_results", 50)
        
        if not is_path_allowed(path):
            return ToolResult(success=False, output=None, error=f"Access denied: {path}")
        
        try:
            if not os.path.exists(path):
                return ToolResult(success=False, output=None, error="Path not found")
            
            search_pattern = os.path.join(path, pattern)
            matches = glob.glob(search_pattern, recursive=True)[:max_results]
            
            results = []
            for match in matches:
                rel_path = os.path.relpath(match, path)
                is_dir = os.path.isdir(match)
                results.append({
                    "path": rel_path,
                    "type": "dir" if is_dir else "file",
                    "size": os.path.getsize(match) if not is_dir else None
                })
            
            return ToolResult(
                success=True,
                output=results,
                metadata={"pattern": pattern, "count": len(results)}
            )
        except Exception as e:
            logger.error(f"File search failed: {e}")
            return ToolResult(success=False, output=None, error=str(e))


def register_file_tools():
    """Register all file tools."""
    register_tool(FileReadTool())
    register_tool(FileWriteTool())
    register_tool(FileListTool())
    register_tool(FileSearchTool())
    logger.info("Registered file tools")
