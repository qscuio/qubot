const Logger = require("./Logger");

const logger = new Logger("BotManager");

/**
 * BotManager - Manages all bot instances (Userbot + multiple Bot API bots).
 */
class BotManager {
    constructor() {
        this.userbot = null;
        this.bots = new Map(); // name -> BotInstance
    }

    /**
     * Register the Userbot (MTProto).
     * @param {object} userbotInstance - TelegramService instance
     */
    registerUserbot(userbotInstance) {
        this.userbot = userbotInstance;
        logger.info("✅ Registered Userbot (MTProto)");
    }

    /**
     * Register a Bot API bot.
     * @param {string} name - Bot identifier (e.g., "rss-bot", "ai-bot")
     * @param {object} botInstance - BotInstance (Telegraf wrapper)
     */
    registerBot(name, botInstance) {
        this.bots.set(name, botInstance);
        logger.info(`✅ Registered Bot: ${name}`);
    }

    /**
     * Get Userbot instance.
     */
    getUserbot() {
        return this.userbot;
    }

    /**
     * Get a Bot by name.
     * @param {string} name - Bot identifier
     */
    getBot(name) {
        return this.bots.get(name);
    }

    /**
     * Get all registered bots.
     */
    getAllBots() {
        return Array.from(this.bots.values());
    }

    /**
     * Get all bot names.
     */
    getBotNames() {
        return Array.from(this.bots.keys());
    }

    /**
     * Start all registered bots.
     */
    async startAll() {
        logger.info("Starting all bots...");

        // Start each Bot API bot
        for (const [name, bot] of this.bots) {
            try {
                await bot.start();
                logger.info(`▶️ Started: ${name}`);
            } catch (err) {
                logger.error(`Failed to start ${name}`, err);
            }
        }

        logger.info(`🚀 Started ${this.bots.size} bot(s)`);
    }

    /**
     * Stop all registered bots.
     */
    async stopAll() {
        logger.info("Stopping all bots...");

        for (const [name, bot] of this.bots) {
            try {
                await bot.stop();
                logger.info(`⏹️ Stopped: ${name}`);
            } catch (err) {
                logger.error(`Failed to stop ${name}`, err);
            }
        }
    }
}

module.exports = BotManager;
