const Logger = require("./Logger");
const ConfigService = require("./ConfigService");
const TelegramService = require("./TelegramService");
const BotManager = require("./BotManager");
const StorageService = require("./StorageService");
const FeatureManager = require("./FeatureManager");
const WebhookServer = require("./WebhookServer");

// Import bot classes
const RssBot = require("../bots/rss-bot");

const logger = new Logger("App");

/**
 * App - Main application entry point.
 * Supports 1 Userbot + N Bot API bots via BotManager.
 */
class App {
    constructor() {
        this.config = null;
        this.storage = null;
        this.botManager = null;
        this.featureManager = null;
        this.webhookServer = null;
    }

    async start() {
        logger.info("🚀 Starting application...");

        // 1. Load Configuration
        this.config = new ConfigService();

        // 2. Initialize Storage
        this.storage = new StorageService(this.config);
        await this.storage.init();

        // 3. Initialize BotManager
        this.botManager = new BotManager();

        // 4. Register Userbot (MTProto)
        const userbot = new TelegramService(this.config);
        await userbot.connect();
        this.botManager.registerUserbot(userbot);

        // 5. Register Bot API bots
        await this._registerBots();

        // 6. Initialize Feature Manager
        this.featureManager = new FeatureManager({
            config: this.config,
            storage: this.storage,
            botManager: this.botManager,
            telegram: userbot,
        });

        // 7. Load and Enable Features
        await this.featureManager.loadFeatures();
        await this.featureManager.enableAll();

        // 8. Start webhook server OR polling
        const useWebhook = !!this.config.get("WEBHOOK_URL");
        if (useWebhook) {
            await this._startWebhookMode();
        } else {
            await this._startPollingMode();
        }

        logger.info("🎉 Application started successfully.");
        logger.info(`   📡 Userbot: Connected`);
        logger.info(`   🤖 Bots: ${this.botManager.getBotNames().join(", ") || "none"}`);
        logger.info(`   🔗 Mode: ${useWebhook ? "Webhook" : "Polling"}`);
    }

    async _registerBots() {
        // RSS Bot
        const rssBotToken = this.config.get("RSS_BOT_TOKEN");
        if (rssBotToken) {
            const rssBot = new RssBot(rssBotToken, this.storage);
            await rssBot.setup();
            this.botManager.registerBot("rss-bot", rssBot);
        }

        // AI Bot (placeholder for future)
        const aiBotToken = this.config.get("AI_BOT_TOKEN");
        if (aiBotToken) {
            logger.info("AI Bot token found, will be enabled in future update.");
        }
    }

    async _startWebhookMode() {
        // Start webhook server
        this.webhookServer = new WebhookServer(this.config, this.botManager);
        await this.webhookServer.start();

        // Note: Webhooks are registered via npm run setup-webhook
        logger.info("📡 Webhook mode enabled. Run 'npm run setup-webhook' to register webhooks.");
    }

    async _startPollingMode() {
        // Start all bots in polling mode
        await this.botManager.startAll();
        logger.info("📡 Polling mode enabled.");
    }

    async stop() {
        logger.info("🛑 Stopping application...");
        await this.botManager.stopAll();
        await this.featureManager.disableAll();
        if (this.webhookServer) {
            await this.webhookServer.stop();
        }
        logger.info("Application stopped.");
    }
}

module.exports = App;
