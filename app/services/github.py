import os
import git
from typing import Optional
from app.core.config import settings
from app.core.logger import Logger

logger = Logger("GitHubService")

class GitHubService:
    def __init__(self):
        self.repo_url = settings.NOTES_REPO
        self.local_path = os.path.join(os.getcwd(), "data", "notes-repo")
        self.repo: Optional[git.Repo] = None
        self.is_ready = False

    def init(self):
        if not self.repo_url:
            logger.warn("NOTES_REPO not configured. GitHub export disabled.")
            return

        try:
            os.makedirs(self.local_path, exist_ok=True)
            
            # Setup SSH key if provided
            if settings.GIT_SSH_KEY_PATH:
                self._setup_ssh()

            git_dir = os.path.join(self.local_path, ".git")
            if os.path.isdir(git_dir):
                self.repo = git.Repo(self.local_path)
                logger.info("Pulling latest changes...")
                origin = self.repo.remotes.origin
                origin.pull()
            else:
                # Clean up any existing files (corrupted/incomplete clone)
                if os.path.exists(self.local_path) and os.listdir(self.local_path):
                    import shutil
                    logger.warn(f"Removing invalid repo directory: {self.local_path}")
                    shutil.rmtree(self.local_path)
                    os.makedirs(self.local_path, exist_ok=True)
                
                logger.info(f"Cloning {self.repo_url}...")
                self.repo = git.Repo.clone_from(self.repo_url, self.local_path)

            # Configure user
            with self.repo.config_writer() as git_config:
                git_config.set_value("user", "name", "QuBot")
                git_config.set_value("user", "email", "qubot@bot.com")

            self.is_ready = True
            logger.info("✅ GitHubService initialized.")
        except Exception as e:
            logger.error("Failed to initialize GitHubService", e)

    def _setup_ssh(self):
        # GitPython uses GIT_SSH_COMMAND env var
        ssh_cmd = f"ssh -i {settings.GIT_SSH_KEY_PATH} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
        os.environ["GIT_SSH_COMMAND"] = ssh_cmd

    def save_note(self, filename: str, content: str, commit_message: str) -> str:
        if not self.is_ready or not self.repo:
            raise Exception("GitHubService not initialized")

        try:
            # Fetch and reset to remote (handles force-pushed history)
            origin = self.repo.remotes.origin
            origin.fetch()
            default_branch = self.repo.active_branch.name
            self.repo.git.reset('--hard', f'origin/{default_branch}')
            
            full_path = os.path.join(self.local_path, filename)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            
            self.repo.index.add([filename])
            self.repo.index.commit(commit_message)
            
            # Reset commit history to keep the repo clean (squash to single commit)
            self._reset_history()
            
            return self._get_http_url(filename)
        except Exception as e:
            logger.error(f"Failed to push {filename}", e)
            raise e
    
    def _reset_history(self):
        """Reset commit history to a single commit and force push.
        This keeps the remote repo clean without accumulating history."""
        if not self.repo:
            return
        
        try:
            # Get the default branch name
            default_branch = self.repo.active_branch.name
            
            # Create a new orphan commit with all current files
            # This effectively squashes all history into one commit
            self.repo.git.checkout('--orphan', 'temp_branch')
            self.repo.git.add('-A')
            self.repo.git.commit('-m', 'Reset: Clean repository state')
            
            # Delete old branch and rename temp to default
            self.repo.git.branch('-D', default_branch)
            self.repo.git.branch('-m', default_branch)
            
            # Force push to overwrite remote history
            self.repo.git.push('-f', 'origin', default_branch)
            
            logger.info("🗑️ Commit history reset successfully")
        except Exception as e:
            logger.warn(f"Failed to reset commit history: {e}")
            # Fallback to normal push if reset fails
            try:
                self.repo.remotes.origin.push()
            except:
                pass

    def _get_http_url(self, filename: str) -> str:
        # Convert git@github.com:user/repo.git -> https://github.com/user/repo/blob/main/filename
        url = self.repo_url.replace("git@github.com:", "https://github.com/").replace(".git", "")
        if url.endswith(".git"):
            url = url[:-4]
        return f"{url}/blob/main/{filename}"

github_service = GitHubService()
