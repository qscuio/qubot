"""
GitHub Actions Client - Interact with GitHub Actions API.

Provides workflow listing, triggering, and log retrieval.
"""

from typing import Dict, List, Optional

from app.core.config import settings
from app.core.logger import Logger

# Try to import PyGithub (optional dependency)
try:
    from github import Github, Auth
    GITHUB_AVAILABLE = True
except ImportError:
    GITHUB_AVAILABLE = False

logger = Logger("GitHubActions")


class GitHubActionsClient:
    """Client for GitHub Actions API."""
    
    def __init__(self, token: Optional[str] = None):
        self._token = token or settings.GITHUB_TOKEN
        self._client: Optional["Github"] = None
    
    def _get_client(self) -> Optional["Github"]:
        """Get or create GitHub client."""
        if not GITHUB_AVAILABLE:
            return None
        if not self._token:
            return None
        if not self._client:
            auth = Auth.Token(self._token)
            self._client = Github(auth=auth)
        return self._client
    
    def is_available(self) -> bool:
        """Check if GitHub API is available."""
        return bool(self._get_client())
    
    def list_workflows(self, repo: str) -> List[Dict]:
        """List workflows for a repository."""
        client = self._get_client()
        if not client:
            return []
        
        try:
            repository = client.get_repo(repo)
            workflows = repository.get_workflows()
            
            return [
                {
                    "id": w.id,
                    "name": w.name,
                    "path": w.path,
                    "state": w.state
                }
                for w in workflows
            ]
        except Exception as e:
            logger.error(f"Failed to list workflows: {e}")
            return []
    
    def list_runs(self, repo: str, limit: int = 10) -> List[Dict]:
        """List recent workflow runs."""
        client = self._get_client()
        if not client:
            return []
        
        try:
            repository = client.get_repo(repo)
            runs = repository.get_workflow_runs()
            
            result = []
            for run in runs[:limit]:
                result.append({
                    "id": run.id,
                    "name": run.name,
                    "status": run.status,
                    "conclusion": run.conclusion,
                    "branch": run.head_branch,
                    "created_at": run.created_at.isoformat() if run.created_at else None,
                    "url": run.html_url
                })
            
            return result
        except Exception as e:
            logger.error(f"Failed to list runs: {e}")
            return []
    
    def trigger_workflow(
        self,
        repo: str,
        workflow_id: str,
        ref: str = "main",
        inputs: Optional[Dict] = None
    ) -> Optional[Dict]:
        """Trigger a workflow dispatch."""
        client = self._get_client()
        if not client:
            return None
        
        try:
            repository = client.get_repo(repo)
            workflow = repository.get_workflow(workflow_id)
            
            success = workflow.create_dispatch(ref, inputs or {})
            
            if success:
                return {
                    "triggered": True,
                    "workflow": workflow.name,
                    "ref": ref
                }
            return None
        except Exception as e:
            logger.error(f"Failed to trigger workflow: {e}")
            return None
    
    def get_run_logs(self, repo: str, run_id: int) -> Optional[str]:
        """Get logs for a workflow run."""
        client = self._get_client()
        if not client:
            return None
        
        try:
            repository = client.get_repo(repo)
            run = repository.get_workflow_run(run_id)
            
            # Get jobs for this run
            jobs = run.jobs()
            
            logs = []
            for job in jobs:
                logs.append(f"## {job.name} ({job.conclusion})")
                
                for step in job.steps:
                    status_emoji = "✅" if step.conclusion == "success" else "❌"
                    logs.append(f"  {status_emoji} {step.name}")
            
            return "\n".join(logs) if logs else "No jobs found"
        except Exception as e:
            logger.error(f"Failed to get run logs: {e}")
            return None
    
    def cancel_run(self, repo: str, run_id: int) -> bool:
        """Cancel a workflow run."""
        client = self._get_client()
        if not client:
            return False
        
        try:
            repository = client.get_repo(repo)
            run = repository.get_workflow_run(run_id)
            run.cancel()
            return True
        except Exception as e:
            logger.error(f"Failed to cancel run: {e}")
            return False
    
    def rerun_workflow(self, repo: str, run_id: int) -> bool:
        """Re-run a workflow."""
        client = self._get_client()
        if not client:
            return False
        
        try:
            repository = client.get_repo(repo)
            run = repository.get_workflow_run(run_id)
            run.rerun()
            return True
        except Exception as e:
            logger.error(f"Failed to rerun: {e}")
            return False


# Singleton instance
github_actions = GitHubActionsClient()
