const { Telegraf } = require("telegraf");
const Logger = require("./Logger");

const logger = new Logger("BotService");

/**
 * BotService - Telegram Bot API for command handling.
 * Separate from TelegramService (Userbot/MTProto).
 */
class BotService {
    constructor(configService) {
        this.config = configService;
        this.bot = null;
        this.enabled = false;
    }

    async init() {
        const token = this.config.get("BOT_TOKEN");
        if (!token) {
            logger.warn("BOT_TOKEN not set. Bot commands disabled.");
            return false;
        }

        this.bot = new Telegraf(token);
        this.enabled = true;

        // Error handling
        this.bot.catch((err, ctx) => {
            logger.error(`Bot error for ${ctx.updateType}`, err);
        });

        logger.info("✅ BotService initialized.");
        return true;
    }

    /**
     * Register a command handler.
     * @param {string} command - Command name without slash (e.g., "sub")
     * @param {Function} handler - Handler function (ctx) => {}
     */
    command(command, handler) {
        if (!this.enabled) return;
        this.bot.command(command, handler);
        logger.debug(`Registered command: /${command}`);
    }

    /**
     * Register a text handler.
     * @param {Function} handler - Handler function (ctx) => {}
     */
    onText(handler) {
        if (!this.enabled) return;
        this.bot.on("text", handler);
    }

    /**
     * Send a message to a user/chat.
     * @param {string|number} chatId - Target chat ID
     * @param {string} text - Message text
     * @param {object} options - Extra options
     */
    async sendMessage(chatId, text, options = {}) {
        if (!this.enabled) return;
        return this.bot.telegram.sendMessage(chatId, text, options);
    }

    /**
     * Start the bot (polling).
     */
    async start() {
        if (!this.enabled) {
            logger.info("BotService not enabled, skipping start.");
            return;
        }

        // Set bot commands menu
        await this.bot.telegram.setMyCommands([
            { command: "sub", description: "订阅 RSS 源" },
            { command: "unsub", description: "取消订阅" },
            { command: "list", description: "查看订阅列表" },
            { command: "check", description: "检查订阅状态" },
            { command: "help", description: "帮助" },
        ]);

        this.bot.launch();
        logger.info("🤖 Bot started (polling mode).");

        // Graceful shutdown
        process.once("SIGINT", () => this.bot.stop("SIGINT"));
        process.once("SIGTERM", () => this.bot.stop("SIGTERM"));
    }

    async stop() {
        if (this.bot) {
            this.bot.stop();
            logger.info("Bot stopped.");
        }
    }

    isEnabled() {
        return this.enabled;
    }
}

module.exports = BotService;
