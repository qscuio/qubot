const { TelegramClient } = require("telegram");
const { StringSession } = require("telegram/sessions");
const { NewMessage } = require("telegram/events");
const Logger = require("./Logger");
const RateLimiter = require("./RateLimiter");

const logger = new Logger("TelegramService");

/**
 * TelegramService - Wraps TelegramClient for use by features.
 */
class TelegramService {
    constructor(configService) {
        this.config = configService;
        this.client = null;
        this.rateLimiter = new RateLimiter(configService.get("RATE_LIMIT_MS"));
    }

    async connect() {
        logger.info("Connecting to Telegram...");
        this.client = new TelegramClient(
            new StringSession(this.config.get("SESSION")),
            this.config.get("API_ID"),
            this.config.get("API_HASH"),
            { connectionRetries: 5 }
        );

        await this.client.connect();
        logger.info("✅ Connected to Telegram.");
    }

    /**
     * Send a message with rate limiting.
     * @param {string|number} peer - Target chat/channel.
     * @param {object} options - Message options.
     */
    async sendMessage(peer, options) {
        return this.rateLimiter.enqueue(async () => {
            logger.debug(`Sending message to ${peer}`);
            return this.client.sendMessage(peer, options);
        });
    }

    /**
     * Add an event handler for new messages.
     * @param {Function} handler - Async handler function.
     * @param {Array} chats - Optional list of chats to filter.
     */
    addMessageHandler(handler, chats = null) {
        const eventFilter = chats && chats.length > 0
            ? new NewMessage({ chats })
            : new NewMessage({});

        this.client.addEventHandler(handler, eventFilter);
        logger.info(`Message handler registered${chats ? ` for ${chats.length} chats` : ""}.`);
        return eventFilter;
    }

    /**
     * Remove an event handler for new messages.
     * @param {Function} handler - Handler function.
     * @param {object} eventFilter - Event filter returned from addMessageHandler.
     */
    removeMessageHandler(handler, eventFilter = null) {
        if (!this.client) return;
        this.client.removeEventHandler(handler, eventFilter);
        logger.info("Message handler removed.");
    }

    /**
     * Resolve an entity (channel, user, chat) by ID or username.
     * This pre-loads the entity into gramjs cache so NewMessage filters work properly.
     * @param {string|number} peer - Channel ID, username, or link.
     * @returns {Promise<object|null>} - The resolved entity or null.
     */
    async resolveEntity(peer) {
        if (!this.client) return null;
        try {
            const entity = await this.client.getEntity(peer);
            logger.debug(`Resolved entity: ${peer} -> ${entity?.id}`);
            return entity;
        } catch (err) {
            logger.warn(`Failed to resolve entity ${peer}: ${err.message}`);
            return null;
        }
    }

    /**
     * Resolve multiple entities (pre-load into cache).
     * @param {Array<string|number>} peers - List of channel IDs or usernames.
     * @returns {Promise<object[]>} - Array of resolved entities (nulls filtered out).
     */
    async resolveEntities(peers) {
        if (!this.client || !peers || peers.length === 0) return [];
        const results = await Promise.all(
            peers.map(peer => this.resolveEntity(peer))
        );
        return results.filter(Boolean);
    }

    /**
     * Get the underlying TelegramClient (for advanced use).
     */
    getClient() {
        return this.client;
    }
}

module.exports = TelegramService;
