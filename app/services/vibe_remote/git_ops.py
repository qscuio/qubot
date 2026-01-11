"""
Git Operations - Wrapper for Git commands.

Provides clone, commit, push, pull, merge, branch operations.
"""

import os
import subprocess
from typing import Dict, List, Optional, Tuple

from app.core.logger import Logger

logger = Logger("GitOps")


class GitOperations:
    """Git operations for vibe_remote sessions."""
    
    def __init__(self, ssh_key_path: Optional[str] = None):
        self._ssh_key_path = ssh_key_path
        self._setup_ssh()
    
    def _setup_ssh(self) -> None:
        """Configure SSH for Git operations."""
        if self._ssh_key_path and os.path.exists(self._ssh_key_path):
            ssh_cmd = f"ssh -i {self._ssh_key_path} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
            os.environ["GIT_SSH_COMMAND"] = ssh_cmd
    
    def _run(self, args: List[str], cwd: str, timeout: int = 60) -> Tuple[bool, str]:
        """Run git command and return (success, output)."""
        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            output = result.stdout.strip() or result.stderr.strip()
            success = result.returncode == 0
            
            if not success:
                logger.warn(f"Git {args[0]} failed: {output}")
            
            return success, output
            
        except subprocess.TimeoutExpired:
            return False, "Command timed out"
        except Exception as e:
            logger.error(f"Git error: {e}")
            return False, str(e)
    
    def clone(self, repo_url: str, target_dir: str) -> Tuple[bool, str]:
        """Clone a repository."""
        parent = os.path.dirname(target_dir)
        os.makedirs(parent, exist_ok=True)
        
        if os.path.exists(target_dir):
            return False, f"Directory already exists: {target_dir}"
        
        return self._run(["clone", repo_url, target_dir], parent, timeout=300)
    
    def status(self, cwd: str) -> Tuple[bool, str]:
        """Get git status."""
        return self._run(["status", "-sb"], cwd)
    
    def add(self, cwd: str, files: List[str] = None) -> Tuple[bool, str]:
        """Stage files for commit."""
        args = ["add"] + (files if files else ["-A"])
        return self._run(args, cwd)
    
    def commit(self, cwd: str, message: str) -> Tuple[bool, str]:
        """Commit staged changes."""
        # Stage all first
        self.add(cwd)
        return self._run(["commit", "-m", message], cwd)
    
    def push(self, cwd: str, force: bool = False) -> Tuple[bool, str]:
        """Push to remote."""
        args = ["push"]
        if force:
            args.append("-f")
        return self._run(args, cwd, timeout=120)
    
    def pull(self, cwd: str) -> Tuple[bool, str]:
        """Pull from remote."""
        return self._run(["pull"], cwd, timeout=120)
    
    def branch(self, cwd: str, name: Optional[str] = None) -> Tuple[bool, str]:
        """List branches or create new branch."""
        if name:
            return self._run(["checkout", "-b", name], cwd)
        return self._run(["branch", "-a"], cwd)
    
    def checkout(self, cwd: str, branch: str) -> Tuple[bool, str]:
        """Checkout branch."""
        return self._run(["checkout", branch], cwd)
    
    def merge(self, cwd: str, branch: str) -> Tuple[bool, str]:
        """Merge branch into current."""
        return self._run(["merge", branch], cwd)
    
    def log(self, cwd: str, count: int = 5) -> Tuple[bool, str]:
        """Get recent commits."""
        return self._run(["log", f"-{count}", "--oneline"], cwd)
    
    def diff(self, cwd: str, staged: bool = False) -> Tuple[bool, str]:
        """Show diff."""
        args = ["diff"]
        if staged:
            args.append("--cached")
        return self._run(args, cwd)
    
    def is_repo(self, cwd: str) -> bool:
        """Check if directory is a git repository."""
        git_dir = os.path.join(cwd, ".git")
        return os.path.isdir(git_dir)
    
    def get_remote_url(self, cwd: str) -> Optional[str]:
        """Get remote origin URL."""
        success, output = self._run(["remote", "get-url", "origin"], cwd)
        return output if success else None
    
    def get_current_branch(self, cwd: str) -> Optional[str]:
        """Get current branch name."""
        success, output = self._run(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
        return output if success else None


# Singleton instance
git_ops = GitOperations()
