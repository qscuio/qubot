const { EventEmitter } = require("events");
const Logger = require("../core/Logger");

/**
 * MonitorService - Business logic for channel monitoring.
 * Supports real-time streaming via EventEmitter.
 * Decoupled from Telegram, can be used by REST API or any frontend.
 */
class MonitorService extends EventEmitter {
    constructor(config, storage, telegramService) {
        super();
        this.config = config;
        this.storage = storage;
        this.telegram = telegramService;
        this.logger = new Logger("MonitorService");
        this.isRunning = false;
        this.sourceChannels = [];
    }

    /**
     * Initialize the monitor service.
     */
    async init() {
        this.sourceChannels = this.config.get("SOURCE_CHANNELS") || [];
        this.logger.info(`MonitorService initialized with ${this.sourceChannels.length} source channels`);
    }

    /**
     * Start monitoring channels.
     */
    async start() {
        if (this.isRunning) {
            return { status: "already_running" };
        }

        if (!this.telegram) {
            throw new Error("Telegram userbot not available");
        }

        if (this.sourceChannels.length === 0) {
            throw new Error("No source channels configured");
        }

        this.telegram.addMessageHandler(
            this._handleMessage.bind(this),
            this.sourceChannels
        );

        this.isRunning = true;
        this.logger.info("Channel monitoring started");
        return { status: "started", channels: this.sourceChannels.length };
    }

    /**
     * Stop monitoring channels.
     */
    async stop() {
        this.isRunning = false;
        this.logger.info("Channel monitoring stopped");
        return { status: "stopped" };
    }

    /**
     * Get monitoring status.
     */
    getStatus() {
        return {
            running: this.isRunning,
            sourceChannels: this.sourceChannels.length,
            targetChannel: this.config.get("TARGET_CHANNEL")
        };
    }

    /**
     * Get all monitored sources.
     */
    async getSources() {
        return {
            channels: this.sourceChannels,
            keywords: this.config.get("KEYWORDS") || [],
            users: this.config.get("FROM_USERS") || [],
            targetChannel: this.config.get("TARGET_CHANNEL")
        };
    }

    /**
     * Add a new source channel.
     */
    async addSource(channelId) {
        if (!this.sourceChannels.includes(channelId)) {
            this.sourceChannels.push(channelId);
            this.logger.info(`Added source channel: ${channelId}`);
        }
        return { channels: this.sourceChannels };
    }

    /**
     * Remove a source channel.
     */
    async deleteSource(channelId) {
        const index = this.sourceChannels.indexOf(channelId);
        if (index > -1) {
            this.sourceChannels.splice(index, 1);
            this.logger.info(`Removed source channel: ${channelId}`);
        }
        return { channels: this.sourceChannels };
    }

    /**
     * Get user's filter policies.
     */
    async getFilters(userId) {
        if (!this.storage) {
            return this._getDefaultFilters();
        }

        try {
            const result = await this.storage.pool.query(
                "SELECT filters FROM monitor_filters WHERE user_id = $1",
                [userId]
            );
            return result.rows[0]?.filters || this._getDefaultFilters();
        } catch (err) {
            // Table might not exist yet
            return this._getDefaultFilters();
        }
    }

    /**
     * Update user's filter policies.
     */
    async updateFilters(userId, filters) {
        if (!this.storage) {
            throw new Error("Storage not available");
        }

        // Ensure table exists
        await this._ensureFiltersTable();

        const mergedFilters = {
            ...this._getDefaultFilters(),
            ...filters
        };

        await this.storage.pool.query(
            `INSERT INTO monitor_filters (user_id, filters)
             VALUES ($1, $2)
             ON CONFLICT (user_id) DO UPDATE SET filters = $2, updated_at = NOW()`,
            [userId, JSON.stringify(mergedFilters)]
        );

        return mergedFilters;
    }

    /**
     * Get message history.
     */
    async getHistory(userId, limit = 50) {
        if (!this.storage) {
            return [];
        }

        try {
            const result = await this.storage.pool.query(
                `SELECT * FROM monitor_history 
                 ORDER BY created_at DESC 
                 LIMIT $1`,
                [limit]
            );
            return result.rows;
        } catch (err) {
            // Table might not exist yet
            return [];
        }
    }

    /**
     * Handle incoming message from monitored channel.
     */
    async _handleMessage(event) {
        try {
            const msg = event.message;
            if (!msg || !msg.message) return;

            const chat = await msg.getChat().catch(() => null);
            const chatUsername = chat?.username;
            const chatTitle = chat?.title || "Unknown";
            const rawChatId = chat?.id?.toString() || "";

            // Normalize chatId
            const normalizedChatId = rawChatId.startsWith("-100")
                ? rawChatId.slice(4)
                : rawChatId;

            // Check if from monitored source
            const isMonitored = this.sourceChannels.some(source => {
                const normalizedSource = source.startsWith("-100")
                    ? source.slice(4)
                    : source.replace(/^@/, "");

                return (
                    source === chatUsername ||
                    source === "@" + chatUsername ||
                    normalizedSource === normalizedChatId ||
                    source === rawChatId
                );
            });

            if (!isMonitored) return;

            const sourceName = chatUsername || chatTitle || rawChatId || "unknown";

            // User filter (global config)
            const fromUsers = this.config.get("FROM_USERS") || [];
            if (fromUsers.length > 0) {
                const sender = await msg.getSender().catch(() => null);
                const senderUsername = sender?.username;
                const senderId = sender?.id?.toString();

                const isAllowedUser = fromUsers.some(
                    u =>
                        u === senderUsername ||
                        u === "@" + senderUsername ||
                        u === senderId
                );

                if (!isAllowedUser) {
                    return;
                }
            }

            // Keyword filter (global config)
            const keywords = this.config.get("KEYWORDS") || [];
            if (keywords.length > 0) {
                const lowerText = msg.message.toLowerCase();
                const hasKeyword = keywords.some(k => lowerText.includes(k));
                if (!hasKeyword) {
                    return;
                }
            }

            // Create message object
            const messageObj = {
                id: msg.id,
                text: msg.message,
                source: sourceName,
                sourceId: rawChatId,
                timestamp: new Date().toISOString()
            };

            // Forward to Telegram TARGET_CHANNEL
            const targetChannel = this.config.get("TARGET_CHANNEL");
            if (targetChannel && this.telegram) {
                const formattedMessage = this._formatMessage(msg.message, sourceName);
                await this.telegram.sendMessage(targetChannel, {
                    message: formattedMessage
                });
                this.logger.info(`Forwarded message from ${sourceName} to ${targetChannel}`);
            }

            // Save to history
            await this._saveToHistory(messageObj);

            // Emit for WebSocket clients
            this.emit("message", messageObj);

        } catch (err) {
            this.logger.error("Error handling monitored message", err);
        }
    }

    /**
     * Save message to history.
     */
    async _saveToHistory(messageObj) {
        if (!this.storage) return;

        try {
            await this._ensureHistoryTable();
            await this.storage.pool.query(
                `INSERT INTO monitor_history (source, source_id, message, created_at)
                 VALUES ($1, $2, $3, NOW())`,
                [messageObj.source, messageObj.sourceId, messageObj.text]
            );
        } catch (err) {
            this.logger.warn("Failed to save to history", err.message);
        }
    }

    /**
     * Format message for Telegram forwarding.
     */
    _formatMessage(text, sourceName) {
        const cleanText = text.replace(/\s+/g, " ").trim();
        return `🔔【New Alert】\n\n${cleanText}\n\n— Source: ${sourceName}`;
    }

    /**
     * Default filter policies.
     */
    _getDefaultFilters() {
        return {
            channels: [],
            keywords: [],
            users: [],
            enabled: true
        };
    }

    /**
     * Ensure filters table exists.
     */
    async _ensureFiltersTable() {
        if (!this.storage) return;

        await this.storage.pool.query(`
            CREATE TABLE IF NOT EXISTS monitor_filters (
                user_id BIGINT PRIMARY KEY,
                filters JSONB NOT NULL DEFAULT '{}',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        `);
    }

    /**
     * Ensure history table exists.
     */
    async _ensureHistoryTable() {
        if (!this.storage) return;

        await this.storage.pool.query(`
            CREATE TABLE IF NOT EXISTS monitor_history (
                id SERIAL PRIMARY KEY,
                source VARCHAR(255) NOT NULL,
                source_id VARCHAR(255),
                message TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        `);
    }
}

module.exports = MonitorService;
