const Logger = require("./Logger");
const ConfigService = require("./ConfigService");
const TelegramService = require("./TelegramService");
const BotManager = require("./BotManager");
const StorageService = require("./StorageService");
const CacheService = require("./CacheService");
const WebhookServer = require("./WebhookServer");
const GitHubService = require("./GitHubService");

// Import services
const { AiService, RssService, MonitorService } = require("../services");

// Import API server
const { ApiServer } = require("../api");

// Import bot classes
const RssBot = require("../bots/rss-bot");
const AiBot = require("../bots/ai-bot");

const logger = new Logger("App");

/**
 * App - Main application entry point.
 * Supports 1 Userbot + N Bot API bots via BotManager.
 * Also runs REST API server for alternative frontends.
 */
class App {
    constructor() {
        this.config = null;
        this.storage = null;
        this.cache = null;
        this.botManager = null;
        this.webhookServer = null;
        this.apiServer = null;

        // Services
        this.services = {
            ai: null,
            rss: null,
            monitor: null
        };

        // GitHub service
        this.githubService = null;

        // Userbot reference
        this.userbot = null;
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

        // 4. Initialize GitHub Service
        this.githubService = new GitHubService(this.config);
        await this.githubService.init();

        // 5. Initialize BotManager
        this.botManager = new BotManager();

        // 6. Register Userbot (MTProto) - optional, only if configured
        if (this.config.isUserbotConfigured()) {
            this.userbot = new TelegramService(this.config);
            await this.userbot.connect();
            this.botManager.registerUserbot(this.userbot);
        } else {
            logger.info("📵 Userbot disabled (MTProto not configured).");
        }

        // 7. Initialize Services (decoupled business logic)
        await this._initializeServices();

        // 8. Register Bot API bots
        await this._registerBots();

        // 9. Start API server (if enabled)
        await this._startApiServer();

        // 10. Start MonitorService (if userbot available)
        if (this.services.monitor && this.userbot) {
            await this.services.monitor.init();
            await this.services.monitor.start().catch(err => {
                logger.warn(`Monitor auto-start failed: ${err.message}`);
            });
        }

        // 11. Start webhook server OR polling for Telegram bots
        const useWebhook = !!this.config.get("WEBHOOK_URL");
        if (useWebhook) {
            await this._startWebhookMode();
        } else {
            await this._startPollingMode();
        }

        logger.info("🎉 Application started successfully.");
        logger.info(`   📡 Userbot: ${this.userbot ? "Connected" : "Disabled"}`);
        logger.info(`   💾 Database: ${this.storage ? "Connected" : "Unavailable"}`);
        logger.info(`   🤖 Bots: ${this.botManager.getBotNames().join(", ") || "none"}`);
        logger.info(`   🔗 Mode: ${useWebhook ? "Webhook" : "Polling"}`);
        logger.info(`   🌐 API: ${this.apiServer ? `Running on port ${this.config.get("API_PORT") || 3001}` : "Disabled"}`);
    }

    async _initializeServices() {
        // AI Service
        this.services.ai = new AiService(this.config, this.storage, this.githubService);
        logger.info("✅ AiService initialized");

        // RSS Service
        this.services.rss = new RssService(this.config, this.storage);
        logger.info("✅ RssService initialized");

        // Monitor Service (requires userbot)
        if (this.userbot) {
            this.services.monitor = new MonitorService(this.config, this.storage, this.userbot);
            logger.info("✅ MonitorService initialized");
        }
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

        // AI Bot
        const aiBotToken = this.config.get("AI_BOT_TOKEN");
        if (aiBotToken) {
            const aiBot = new AiBot(aiBotToken, this.config, this.storage, this.githubService, allowedUsers);
            await aiBot.setup();
            this.botManager.registerBot("ai-bot", aiBot);
        }
    }

    async _startApiServer() {
        const apiEnabled = this.config.get("API_ENABLED") !== "false";

        if (!apiEnabled) {
            logger.info("📵 API server disabled (API_ENABLED=false).");
            return;
        }

        this.apiServer = new ApiServer(this.config, this.services);
        await this.apiServer.start();
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
        if (this.services.monitor) {
            await this.services.monitor.stop();
        }
        if (this.webhookServer) {
            await this.webhookServer.stop();
        }
        if (this.apiServer) {
            await this.apiServer.stop();
        }
        if (this.storage) {
            await this.storage.close();
        }
        logger.info("Application stopped.");
    }
}

module.exports = App;

