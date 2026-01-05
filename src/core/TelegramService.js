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

        // Sync dialogs to ensure gramjs knows about all channels
        // This is required for receiving updates from channels
        await this._syncDialogs();

        const me = await this.client.getMe().catch(() => null);
        if (me) {
            const name = me.username || me.firstName || me.id;
            logger.info(`Logged in as ${name} (bot=${!!me.bot})`);
            if (me.bot) {
                logger.warn("MTProto session is a bot. Bots only receive channel/group updates if added (channels require admin).");
            }
        }
    }

    /**
     * Sync dialogs to ensure gramjs receives updates from all subscribed channels.
     * Without this, gramjs may not receive updates for channels the user hasn't
     * recently interacted with.
     */
    async _syncDialogs() {
        try {
            logger.info("Syncing dialogs to receive channel updates...");
            const dialogs = await this.client.getDialogs({});
            const channels = dialogs.filter(d => d.isChannel || d.isGroup);
            logger.info(`✅ Synced ${dialogs.length} dialogs (${channels.length} channels/groups).`);
        } catch (err) {
            logger.warn(`Failed to sync dialogs: ${err.message}`);
        }
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
     * @param {Array} chats - Optional list of chats to filter (may not work reliably for channels).
     * @param {boolean} receiveAll - If true, receive ALL messages and filter in handler.
     */
    addMessageHandler(handler, chats = null, receiveAll = false) {
        // For monitoring, receiveAll=true is more reliable as gramjs chat filter
        // may not work correctly for channels the user hasn't directly messaged
        const eventFilter = (chats && chats.length > 0 && !receiveAll)
            ? new NewMessage({ chats })
            : new NewMessage({});

        this.client.addEventHandler(handler, eventFilter);
        if (receiveAll || !chats) {
            logger.info(`Message handler registered (receiving ALL incoming messages).`);
        } else {
            logger.info(`Message handler registered for ${chats.length} chats.`);
        }
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
