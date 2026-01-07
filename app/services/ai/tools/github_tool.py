"""
GitHub tools for repository, issues, PRs, and file operations.
"""

import httpx
from typing import List, Optional, Dict, Any
from app.services.ai.tools.base import Tool, ToolParameter, ToolResult
from app.services.ai.tools.registry import register_tool
from app.core.config import settings
from app.core.logger import Logger

logger = Logger("GitHubTools")

GITHUB_API = "https://api.github.com"


def get_headers() -> Dict[str, str]:
    """Get GitHub API headers with token."""
    token = getattr(settings, "GITHUB_TOKEN", None)
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "QuBot/1.0"
    }
    if token:
        headers["Authorization"] = f"token {token}"
    return headers


class GitHubRepoTool(Tool):
    """Get repository information."""
    
    @property
    def name(self) -> str:
        return "github_repo"
    
    @property
    def description(self) -> str:
        return "Get information about a GitHub repository including description, stars, forks, and recent activity."
    
    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="owner",
                type="string",
                description="Repository owner (username or org)",
                required=True
            ),
            ToolParameter(
                name="repo",
                type="string",
                description="Repository name",
                required=True
            )
        ]
    
    async def execute(self, **kwargs) -> ToolResult:
        owner = kwargs.get("owner", "")
        repo = kwargs.get("repo", "")
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{GITHUB_API}/repos/{owner}/{repo}",
                    headers=get_headers(),
                    timeout=15.0
                )
                
                if response.status_code == 404:
                    return ToolResult(success=False, output=None, error="Repository not found")
                
                response.raise_for_status()
                data = response.json()
                
                info = {
                    "name": data.get("full_name"),
                    "description": data.get("description"),
                    "url": data.get("html_url"),
                    "stars": data.get("stargazers_count"),
                    "forks": data.get("forks_count"),
                    "open_issues": data.get("open_issues_count"),
                    "language": data.get("language"),
                    "topics": data.get("topics", []),
                    "created_at": data.get("created_at"),
                    "updated_at": data.get("updated_at"),
                    "default_branch": data.get("default_branch")
                }
                
                return ToolResult(success=True, output=info)
        except Exception as e:
            logger.error(f"GitHub repo failed: {e}")
            return ToolResult(success=False, output=None, error=str(e))


class GitHubIssuesTool(Tool):
    """List, get, or create GitHub issues."""
    
    @property
    def name(self) -> str:
        return "github_issues"
    
    @property
    def description(self) -> str:
        return "List, get details, or create issues in a GitHub repository."
    
    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="action",
                type="string",
                description="Action: 'list', 'get', or 'create'",
                required=True,
                enum=["list", "get", "create"]
            ),
            ToolParameter(
                name="owner",
                type="string",
                description="Repository owner",
                required=True
            ),
            ToolParameter(
                name="repo",
                type="string",
                description="Repository name",
                required=True
            ),
            ToolParameter(
                name="issue_number",
                type="integer",
                description="Issue number (for 'get' action)",
                required=False
            ),
            ToolParameter(
                name="title",
                type="string",
                description="Issue title (for 'create' action)",
                required=False
            ),
            ToolParameter(
                name="body",
                type="string",
                description="Issue body (for 'create' action)",
                required=False
            ),
            ToolParameter(
                name="state",
                type="string",
                description="Filter by state (for 'list'): 'open', 'closed', 'all'",
                required=False,
                default="open"
            )
        ]
    
    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "list")
        owner = kwargs.get("owner", "")
        repo = kwargs.get("repo", "")
        
        try:
            async with httpx.AsyncClient() as client:
                if action == "list":
                    state = kwargs.get("state", "open")
                    response = await client.get(
                        f"{GITHUB_API}/repos/{owner}/{repo}/issues",
                        headers=get_headers(),
                        params={"state": state, "per_page": 20},
                        timeout=15.0
                    )
                    response.raise_for_status()
                    
                    issues = []
                    for issue in response.json():
                        issues.append({
                            "number": issue.get("number"),
                            "title": issue.get("title"),
                            "state": issue.get("state"),
                            "user": issue.get("user", {}).get("login"),
                            "created_at": issue.get("created_at"),
                            "comments": issue.get("comments")
                        })
                    
                    return ToolResult(success=True, output=issues)
                
                elif action == "get":
                    issue_number = kwargs.get("issue_number")
                    if not issue_number:
                        return ToolResult(success=False, output=None, error="issue_number required")
                    
                    response = await client.get(
                        f"{GITHUB_API}/repos/{owner}/{repo}/issues/{issue_number}",
                        headers=get_headers(),
                        timeout=15.0
                    )
                    response.raise_for_status()
                    data = response.json()
                    
                    issue = {
                        "number": data.get("number"),
                        "title": data.get("title"),
                        "body": data.get("body", "")[:2000],
                        "state": data.get("state"),
                        "user": data.get("user", {}).get("login"),
                        "labels": [l.get("name") for l in data.get("labels", [])],
                        "created_at": data.get("created_at"),
                        "comments": data.get("comments")
                    }
                    
                    return ToolResult(success=True, output=issue)
                
                elif action == "create":
                    title = kwargs.get("title")
                    body = kwargs.get("body", "")
                    
                    if not title:
                        return ToolResult(success=False, output=None, error="title required")
                    if not getattr(settings, "GITHUB_TOKEN", None):
                        return ToolResult(success=False, output=None, error="GITHUB_TOKEN required for create")
                    
                    response = await client.post(
                        f"{GITHUB_API}/repos/{owner}/{repo}/issues",
                        headers=get_headers(),
                        json={"title": title, "body": body},
                        timeout=15.0
                    )
                    response.raise_for_status()
                    data = response.json()
                    
                    return ToolResult(
                        success=True,
                        output={
                            "number": data.get("number"),
                            "url": data.get("html_url"),
                            "title": data.get("title")
                        }
                    )
                
                return ToolResult(success=False, output=None, error="Unknown action")
        except Exception as e:
            logger.error(f"GitHub issues failed: {e}")
            return ToolResult(success=False, output=None, error=str(e))


class GitHubPRTool(Tool):
    """List or get pull request information."""
    
    @property
    def name(self) -> str:
        return "github_pr"
    
    @property
    def description(self) -> str:
        return "List or get details of pull requests in a GitHub repository."
    
    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="action",
                type="string",
                description="Action: 'list' or 'get'",
                required=True,
                enum=["list", "get"]
            ),
            ToolParameter(
                name="owner",
                type="string",
                description="Repository owner",
                required=True
            ),
            ToolParameter(
                name="repo",
                type="string",
                description="Repository name",
                required=True
            ),
            ToolParameter(
                name="pr_number",
                type="integer",
                description="PR number (for 'get' action)",
                required=False
            ),
            ToolParameter(
                name="state",
                type="string",
                description="Filter by state: 'open', 'closed', 'all'",
                required=False,
                default="open"
            )
        ]
    
    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "list")
        owner = kwargs.get("owner", "")
        repo = kwargs.get("repo", "")
        
        try:
            async with httpx.AsyncClient() as client:
                if action == "list":
                    state = kwargs.get("state", "open")
                    response = await client.get(
                        f"{GITHUB_API}/repos/{owner}/{repo}/pulls",
                        headers=get_headers(),
                        params={"state": state, "per_page": 20},
                        timeout=15.0
                    )
                    response.raise_for_status()
                    
                    prs = []
                    for pr in response.json():
                        prs.append({
                            "number": pr.get("number"),
                            "title": pr.get("title"),
                            "state": pr.get("state"),
                            "user": pr.get("user", {}).get("login"),
                            "created_at": pr.get("created_at"),
                            "head": pr.get("head", {}).get("ref"),
                            "base": pr.get("base", {}).get("ref")
                        })
                    
                    return ToolResult(success=True, output=prs)
                
                elif action == "get":
                    pr_number = kwargs.get("pr_number")
                    if not pr_number:
                        return ToolResult(success=False, output=None, error="pr_number required")
                    
                    response = await client.get(
                        f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}",
                        headers=get_headers(),
                        timeout=15.0
                    )
                    response.raise_for_status()
                    data = response.json()
                    
                    pr = {
                        "number": data.get("number"),
                        "title": data.get("title"),
                        "body": data.get("body", "")[:2000],
                        "state": data.get("state"),
                        "user": data.get("user", {}).get("login"),
                        "head": data.get("head", {}).get("ref"),
                        "base": data.get("base", {}).get("ref"),
                        "mergeable": data.get("mergeable"),
                        "additions": data.get("additions"),
                        "deletions": data.get("deletions"),
                        "changed_files": data.get("changed_files")
                    }
                    
                    return ToolResult(success=True, output=pr)
                
                return ToolResult(success=False, output=None, error="Unknown action")
        except Exception as e:
            logger.error(f"GitHub PR failed: {e}")
            return ToolResult(success=False, output=None, error=str(e))


class GitHubFileTool(Tool):
    """Read or write files in a GitHub repository."""
    
    @property
    def name(self) -> str:
        return "github_file"
    
    @property
    def description(self) -> str:
        return "Read file contents from a GitHub repository."
    
    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="owner",
                type="string",
                description="Repository owner",
                required=True
            ),
            ToolParameter(
                name="repo",
                type="string",
                description="Repository name",
                required=True
            ),
            ToolParameter(
                name="path",
                type="string",
                description="File path in repository",
                required=True
            ),
            ToolParameter(
                name="ref",
                type="string",
                description="Branch, tag, or commit SHA",
                required=False,
                default="main"
            )
        ]
    
    async def execute(self, **kwargs) -> ToolResult:
        owner = kwargs.get("owner", "")
        repo = kwargs.get("repo", "")
        path = kwargs.get("path", "")
        ref = kwargs.get("ref", "main")
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
                    headers=get_headers(),
                    params={"ref": ref},
                    timeout=15.0
                )
                
                if response.status_code == 404:
                    return ToolResult(success=False, output=None, error="File not found")
                
                response.raise_for_status()
                data = response.json()
                
                if data.get("type") == "dir":
                    # Directory listing
                    files = [{"name": f.get("name"), "type": f.get("type")} for f in data]
                    return ToolResult(success=True, output=files)
                
                # File content (base64 decoded)
                import base64
                content = base64.b64decode(data.get("content", "")).decode("utf-8", errors="replace")
                
                return ToolResult(
                    success=True,
                    output=content[:10000],  # Limit content size
                    metadata={"path": path, "sha": data.get("sha"), "size": data.get("size")}
                )
        except Exception as e:
            logger.error(f"GitHub file failed: {e}")
            return ToolResult(success=False, output=None, error=str(e))


def register_github_tools():
    """Register all GitHub tools."""
    register_tool(GitHubRepoTool())
    register_tool(GitHubIssuesTool())
    register_tool(GitHubPRTool())
    register_tool(GitHubFileTool())
    logger.info("Registered GitHub tools")
