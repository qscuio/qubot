const Logger = require("./Logger");
const ConfigService = require("./ConfigService");
const TelegramService = require("./TelegramService");
const BotManager = require("./BotManager");
const StorageService = require("./StorageService");
const CacheService = require("./CacheService");
const FeatureManager = require("./FeatureManager");
const WebhookServer = require("./WebhookServer");
const GitHubService = require("./GitHubService");

// Import bot classes
const RssBot = require("../bots/rss-bot");
const AiBot = require("../bots/ai-bot");

const logger = new Logger("App");

/**
 * App - Main application entry point.
 * Supports 1 Userbot + N Bot API bots via BotManager.
 */
class App {
    constructor() {
        this.config = null;
        this.storage = null;
        this.cache = null;
        this.botManager = null;
        this.featureManager = null;
        this.webhookServer = null;
    }

    async start() {
        logger.info("🚀 Starting application...");

        // 1. Load Configuration
        this.config = new ConfigService();

        // 2. Initialize Storage (PostgreSQL) - graceful degradation if unavailable
        this.storage = new StorageService(this.config);
        const storageReady = await this.storage.init();
        if (!storageReady) {
            logger.warn("⚠️ Database unavailable. Storage-dependent features will be limited.");
            this.storage = null;
        }

        // 3. Initialize Cache (Redis)
        this.cache = new CacheService(this.config);
        await this.cache.init();

        // 4. Initialize BotManager
        this.botManager = new BotManager();

        // 5. Register Userbot (MTProto) - optional, only if configured
        let userbot = null;
        if (this.config.isUserbotConfigured()) {
            userbot = new TelegramService(this.config);
            await userbot.connect();
            this.botManager.registerUserbot(userbot);
        } else {
            logger.info("📵 Userbot disabled (MTProto not configured).");
        }

        // 6. Register Bot API bots
        await this._registerBots();

        // 7. Initialize Feature Manager (only if userbot is available)
        if (userbot) {
            this.featureManager = new FeatureManager({
                config: this.config,
                storage: this.storage,
                botManager: this.botManager,
                telegram: userbot,
            });

            // 8. Load and Enable Features
            await this.featureManager.loadFeatures();
            await this.featureManager.enableAll();
        } else {
            logger.info("📵 Features requiring userbot skipped.");
        }

        // 9. Start webhook server OR polling
        const useWebhook = !!this.config.get("WEBHOOK_URL");
        if (useWebhook) {
            await this._startWebhookMode();
        } else {
            await this._startPollingMode();
        }

        logger.info("🎉 Application started successfully.");
        logger.info(`   📡 Userbot: ${userbot ? "Connected" : "Disabled"}`);
        logger.info(`   💾 Database: ${this.storage ? "Connected" : "Unavailable"}`);
        logger.info(`   🤖 Bots: ${this.botManager.getBotNames().join(", ") || "none"}`);
        logger.info(`   🔗 Mode: ${useWebhook ? "Webhook" : "Polling"}`);
    }

    async _registerBots() {
        const allowedUsers = this.config.get("ALLOWED_USERS");

        // RSS Bot
        const rssBotToken = this.config.get("RSS_BOT_TOKEN");
        if (rssBotToken) {
            const rssBot = new RssBot(rssBotToken, this.config, this.storage, allowedUsers);
            await rssBot.setup();
            this.botManager.registerBot("rss-bot", rssBot);
        }

        // GitHub Service
        const githubService = new GitHubService(this.config);
        await githubService.init();

        // AI Bot
        const aiBotToken = this.config.get("AI_BOT_TOKEN");
        if (aiBotToken) {
            const aiBot = new AiBot(aiBotToken, this.config, this.storage, githubService, allowedUsers);
            await aiBot.setup();
            this.botManager.registerBot("ai-bot", aiBot);
        }
    }

    async _startWebhookMode() {
        // Set commands menu for each bot (even though not polling)
        for (const name of this.botManager.getBotNames()) {
            const bot = this.botManager.getBot(name);
            await bot.setCommands();
        }

        // Start webhook server
        this.webhookServer = new WebhookServer(this.config, this.botManager);
        await this.webhookServer.start();

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
        if (this.featureManager) {
            await this.featureManager.disableAll();
        }
        if (this.webhookServer) {
            await this.webhookServer.stop();
        }
        if (this.storage) {
            await this.storage.close();
        }
        logger.info("Application stopped.");
    }
}

module.exports = App;
