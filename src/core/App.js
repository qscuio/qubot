const Logger = require("./Logger");
const ConfigService = require("./ConfigService");
const TelegramService = require("./TelegramService");
const FeatureManager = require("./FeatureManager");

const logger = new Logger("App");

/**
 * App - Main application entry point.
 */
class App {
    constructor() {
        this.config = null;
        this.telegram = null;
        this.featureManager = null;
    }

    async start() {
        logger.info("🚀 Starting application...");

        // 1. Load Configuration
        this.config = new ConfigService();

        // 2. Initialize Telegram Service
        this.telegram = new TelegramService(this.config);
        await this.telegram.connect();

        // 3. Initialize Feature Manager
        this.featureManager = new FeatureManager({
            config: this.config,
            telegram: this.telegram,
        });

        // 4. Load and Enable Features
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
