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

                // Try to notify user about the error
                const chatId = req.body?.message?.chat?.id || req.body?.callback_query?.message?.chat?.id;
                if (chatId) {
                    try {
                        let errorMsg = "⚠️ An error occurred while processing your request.";

                        // Provide more specific messages for common errors
                        if (err.code === "ETIMEDOUT" || err.code === "ECONNRESET" || err.code === "ENOTFOUND") {
                            errorMsg = "⚠️ Network error: Connection to Telegram API timed out. Please try again.";
                        } else if (err.code === "ECONNREFUSED") {
                            errorMsg = "⚠️ Service temporarily unavailable. Please try again later.";
                        } else if (err.message) {
                            errorMsg = `⚠️ Error: ${err.message.substring(0, 100)}`;
                        }

                        await bot.getTelegraf().telegram.sendMessage(chatId, errorMsg);
                    } catch (notifyErr) {
                        // If we can't even notify the user, just log it
                        logger.warn(`Failed to notify user about error: ${notifyErr.message}`);
                    }
                }

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
