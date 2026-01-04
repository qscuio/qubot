const Logger = require("./Logger");
const ConfigService = require("./ConfigService");
const TelegramService = require("./TelegramService");
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

        // 3. Initialize Telegram Service
        this.telegram = new TelegramService(this.config);
        await this.telegram.connect();

        // 4. Initialize Feature Manager
        this.featureManager = new FeatureManager({
            config: this.config,
            telegram: this.telegram,
            storage: this.storage,
        });

        // 5. Load and Enable Features
        await this.featureManager.loadFeatures();
        await this.featureManager.enableAll();

        logger.info("🎉 Application started successfully.");
    }

    async stop() {
        logger.info("🛑 Stopping application...");
        await this.featureManager.disableAll();
        logger.info("Application stopped.");
    }
}

module.exports = App;
