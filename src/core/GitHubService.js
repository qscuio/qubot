const simpleGit = require("simple-git");
const fs = require("fs").promises;
const path = require("path");
const Logger = require("./Logger");

const logger = new Logger("GitHubService");

class GitHubService {
    constructor(config) {
        this.config = config;
        this.repoUrl = config.get("NOTES_REPO");
        this.localPath = path.join(process.cwd(), "data", "notes-repo");
        this.git = simpleGit();
        this.isReady = false;
    }

    async init() {
        if (!this.repoUrl) {
            logger.warn("NOTES_REPO not configured. GitHub export disabled.");
            return false;
        }

        try {
            await fs.mkdir(this.localPath, { recursive: true });

            // Configure SSH with specific key and skip host verification
            const sshCommand = "ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i /root/.ssh/github_actions";
            this.git = simpleGit().env("GIT_SSH_COMMAND", sshCommand);

            // Check if repo exists locally
            const isRepo = await fs.access(path.join(this.localPath, ".git"))
                .then(() => true)
                .catch(() => false);

            if (!isRepo) {
                logger.info(`Cloning ${this.repoUrl} to ${this.localPath}...`);
                await this.git.clone(this.repoUrl, this.localPath);
            } else {
                this.git.cwd(this.localPath);
                logger.info("Pulling latest changes...");
                await this.git.pull();
            }

            this.git.cwd(this.localPath);

            // Configure user
            await this.git.addConfig("user.name", "QuBot");
            await this.git.addConfig("user.email", "qubot@bot.com");

            this.isReady = true;
            this.initError = null;
            logger.info("✅ GitHubService initialized.");
            return true;
        } catch (err) {
            logger.error("Failed to initialize GitHubService", err);
            this.initError = err.message;
            return false;
        }
    }

    async saveNote(filename, content, commitMessage) {
        if (!this.isReady) {
            throw new Error("GitHubService not initialized or configured.");
        }

        try {
            this.git.cwd(this.localPath);
            await this.git.pull(); // Always pull first

            // Ensure directory exists
            const filePath = path.join(this.localPath, filename);
            const dir = path.dirname(filePath);
            await fs.mkdir(dir, { recursive: true });

            await fs.writeFile(filePath, content, "utf8");

            await this.git.add(filename);
            await this.git.commit(commitMessage);
            await this.git.push();

            const httpUrl = this._getHttpUrl(filename);
            logger.info(`Pushed ${filename} to GitHub: ${httpUrl}`);
            return httpUrl;
        } catch (err) {
            logger.error(`Failed to push ${filename}`, err);
            throw err;
        }
    }

    _getHttpUrl(filename) {
        // Convert git@github.com:user/repo.git to https://github.com/user/repo/blob/main/filename
        let url = this.repoUrl
            .replace("git@github.com:", "https://github.com/")
            .replace(".git", "");

        if (url.endsWith(".git")) url = url.slice(0, -4);

        // Assuming main branch
        return `${url}/blob/main/${filename}`;
    }
}

module.exports = GitHubService;
