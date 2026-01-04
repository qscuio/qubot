const Logger = require("./Logger");
const ConfigService = require("./ConfigService");
const TelegramService = require("./TelegramService");
const BotService = require("./BotService");
const FeatureManager = require("./FeatureManager");
const StorageService = require("./StorageService");

const logger = new Logger("App");

/**
 * App - Main application entry point.
 */
class App {
    constructor() {
        this.config = null;
        this.telegram = null;
        this.bot = null;
        this.storage = null;
        this.featureManager = null;
    }

    async start() {
        logger.info("🚀 Starting application...");

        // 1. Load Configuration
        this.config = new ConfigService();

        // 2. Initialize Storage (optional, for subscription feature)
        this.storage = new StorageService(this.config);
        await this.storage.init();

        // 3. Initialize Telegram Userbot (MTProto - for channel monitoring)
        this.telegram = new TelegramService(this.config);
        await this.telegram.connect();

        // 4. Initialize Telegram Bot (Bot API - for commands)
        this.bot = new BotService(this.config);
        await this.bot.init();

        // 5. Initialize Feature Manager
        this.featureManager = new FeatureManager({
            config: this.config,
            telegram: this.telegram,
            bot: this.bot,
            storage: this.storage,
        });

        // 6. Load and Enable Features
        await this.featureManager.loadFeatures();
        await this.featureManager.enableAll();

        // 7. Start Bot polling
        await this.bot.start();

        logger.info("🎉 Application started successfully.");
    }

    async stop() {
        logger.info("🛑 Stopping application...");
        await this.featureManager.disableAll();
        logger.info("Application stopped.");
    }
}

module.exports = App;
