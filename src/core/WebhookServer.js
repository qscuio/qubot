const express = require("express");
const Logger = require("./Logger");

const logger = new Logger("WebhookServer");

/**
 * WebhookServer - Express server for handling Telegram webhook updates.
 */
class WebhookServer {
    constructor(config, botManager) {
        this.config = config;
        this.botManager = botManager;
        this.app = express();
        this.server = null;
        this.port = config.get("BOT_PORT") || 3000;
        this.secret = config.get("BOT_SECRET") || "";

        this._setupMiddleware();
        this._setupRoutes();
    }

    _setupMiddleware() {
        this.app.use(express.json());
    }

    _setupRoutes() {
        // Health check
        this.app.get("/health", (req, res) => {
            res.json({ status: "ok", timestamp: new Date().toISOString() });
        });

        // Webhook endpoint for each bot
        // Format: /webhook/:botName
        this.app.post("/webhook/:botName", async (req, res) => {
            const { botName } = req.params;

            // Verify secret token
            const secretHeader = req.headers["x-telegram-bot-api-secret-token"];
            if (this.secret && secretHeader !== this.secret) {
                logger.warn(`Unauthorized webhook request for ${botName}`);
                return res.status(403).json({ error: "Unauthorized" });
            }

            const bot = this.botManager.getBot(botName);
            if (!bot || !bot.isEnabled()) {
                logger.warn(`Unknown bot: ${botName}`);
                return res.status(404).json({ error: "Bot not found" });
            }

            try {
                // Process update
                await bot.getTelegraf().handleUpdate(req.body);
                res.json({ ok: true });
            } catch (err) {
                logger.error(`Error handling update for ${botName}`, err);
                res.status(500).json({ error: "Internal error" });
            }
        });
    }

    async start() {
        return new Promise((resolve) => {
            this.server = this.app.listen(this.port, () => {
                logger.info(`🌐 Webhook server running on port ${this.port}`);
                logger.info(`📡 Health check: /health`);
                logger.info(`📨 Webhook format: /webhook/:botName`);
                resolve();
            });
        });
    }

    async stop() {
        if (this.server) {
            return new Promise((resolve) => {
                this.server.close(resolve);
            });
        }
    }

    getApp() {
        return this.app;
    }
}

module.exports = WebhookServer;
