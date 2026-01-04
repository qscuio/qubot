const { Telegraf } = require("telegraf");
const Logger = require("./Logger");

/**
 * BotInstance - Base class for Bot API bots.
 * Each bot has its own token and can register commands independently.
 */
class BotInstance {
    /**
     * @param {string} name - Bot identifier (e.g., "rss-bot")
     * @param {string} token - Telegram Bot Token
     */
    constructor(name, token) {
        this.name = name;
        this.token = token;
        this.bot = null;
        this.logger = new Logger(`Bot:${name}`);
        this.commands = [];

        if (token) {
            this.bot = new Telegraf(token);
            this._setupErrorHandling();
        }
    }

    _setupErrorHandling() {
        this.bot.catch((err, ctx) => {
            this.logger.error(`Error for ${ctx.updateType}`, err);
        });
    }

    /**
     * Check if bot is enabled (has valid token).
     */
    isEnabled() {
        return !!this.bot;
    }

    /**
     * Register a command.
     * @param {string} command - Command name without slash
     * @param {string} description - Command description
     * @param {Function} handler - Handler function (ctx) => {}
     */
    command(command, description, handler) {
        if (!this.bot) return;
        this.bot.command(command, handler);
        this.commands.push({ command, description });
        this.logger.debug(`Registered command: /${command}`);
    }

    /**
     * Register a callback query handler.
     * @param {string|RegExp} trigger - Callback trigger
     * @param {Function} handler - Handler function
     */
    action(trigger, handler) {
        if (!this.bot) return;
        this.bot.action(trigger, handler);
    }

    /**
     * Register a text handler.
     * @param {Function} handler - Handler function
     */
    onText(handler) {
        if (!this.bot) return;
        this.bot.on("text", handler);
    }

    /**
     * Send a message.
     * @param {string|number} chatId - Target chat ID
     * @param {string} text - Message text
     * @param {object} options - Extra options
     */
    async sendMessage(chatId, text, options = {}) {
        if (!this.bot) return;
        return this.bot.telegram.sendMessage(chatId, text, options);
    }

    /**
     * Get the underlying Telegraf instance.
     */
    getTelegraf() {
        return this.bot;
    }

    /**
     * Set commands menu (call this in webhook mode).
     */
    async setCommands() {
        if (!this.bot || this.commands.length === 0) return;
        try {
            await this.bot.telegram.setMyCommands(this.commands);
            this.logger.info(`Set ${this.commands.length} commands in menu.`);
        } catch (err) {
            this.logger.warn(`Failed to set commands: ${err.message}`);
        }
    }

    /**
     * Start the bot.
     */
    async start() {
        if (!this.bot) {
            this.logger.warn("Bot not configured, skipping start.");
            return;
        }

        // Set commands menu
        if (this.commands.length > 0) {
            await this.bot.telegram.setMyCommands(this.commands);
        }

        // Start polling
        this.bot.launch();
        this.logger.info(`🤖 Bot started (polling mode)`);

        // Graceful shutdown handlers
        const shutdown = (signal) => {
            this.logger.info(`Received ${signal}, stopping...`);
            this.bot.stop(signal);
        };
        process.once("SIGINT", () => shutdown("SIGINT"));
        process.once("SIGTERM", () => shutdown("SIGTERM"));
    }

    /**
     * Stop the bot.
     */
    async stop() {
        if (this.bot) {
            this.bot.stop();
            this.logger.info("Bot stopped.");
        }
    }
}

module.exports = BotInstance;
