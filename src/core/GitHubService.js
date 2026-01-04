const simpleGit = require("simple-git");
const fs = require("fs").promises;
const path = require("path");
const Logger = require("./Logger");

const logger = new Logger("GitHubService");

class GitHubService {
    constructor(config) {
        this.config = config;
        this.repoUrl = config.get("NOTES_REPO");
        this.sshKeyPath = config.get("NOTES_SSH_KEY_PATH");
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

            // Configure git to use SSH key
            const gitSSHCommand = `ssh -o StrictHostKeyChecking=no -i ${this.sshKeyPath}`;
            this.git.env("GIT_SSH_COMMAND", gitSSHCommand);

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

            // Configure user
            await this.git.addConfig("user.name", "QuBot");
            await this.git.addConfig("user.email", "qubot@bot.com");

            this.isReady = true;
            logger.info("✅ GitHubService initialized.");
            return true;
        } catch (err) {
            logger.error("Failed to initialize GitHubService", err);
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
