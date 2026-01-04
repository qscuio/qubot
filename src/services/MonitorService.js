const { EventEmitter } = require("events");
const Logger = require("../core/Logger");

/**
 * MonitorService - Business logic for channel monitoring.
 * Supports real-time streaming via EventEmitter.
 * Can use AiService for intelligent message analysis.
 * Decoupled from Telegram, can be used by REST API or any frontend.
 */
class MonitorService extends EventEmitter {
    constructor(config, storage, telegramService, aiService = null) {
        super();
        this.config = config;
        this.storage = storage;
        this.telegram = telegramService;
        this.aiService = aiService;
        this.logger = new Logger("MonitorService");
        this.isRunning = false;
        this.sourceChannels = [];
    }

    /**
     * Set the AI service (allows injection after construction).
     */
    setAiService(aiService) {
        this.aiService = aiService;
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
                ai_summary TEXT,
                ai_sentiment VARCHAR(50),
                ai_topics JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            )
        `);
    }

    // ============================================================
    // AI-POWERED ANALYSIS METHODS
    // ============================================================

    /**
     * Analyze a message with AI.
     * Returns summary, sentiment, and key topics.
     */
    async analyzeMessage(text) {
        if (!this.aiService?.isAnalysisAvailable()) {
            return { summary: null, sentiment: null, topics: null };
        }

        try {
            const result = await this.aiService.extract(text, [
                "summary",
                "sentiment",
                "topics"
            ]);
            return result;
        } catch (err) {
            this.logger.warn("Message analysis failed", err.message);
            return { summary: null, sentiment: null, topics: null };
        }
    }

    /**
     * Check if a message matches smart filter criteria.
     * Uses AI to understand semantic meaning, not just keywords.
     * @param {string} text - Message text
     * @param {object} criteria - Filter criteria (e.g., {topic: "crypto", sentiment: "bullish"})
     */
    async matchesSmartFilter(text, criteria) {
        if (!this.aiService?.isAnalysisAvailable()) {
            return true; // Pass through if AI not available
        }

        if (!criteria || Object.keys(criteria).length === 0) {
            return true;
        }

        const prompt = `Analyze if this message matches the filter criteria.

Message: ${text.substring(0, 1000)}

Criteria:
${Object.entries(criteria).map(([k, v]) => `- ${k}: ${v}`).join("\n")}

Respond with JSON: {"matches": true/false, "confidence": "high/medium/low", "reasoning": "brief explanation"}`;

        try {
            const response = await this.aiService.analyze(prompt);
            const result = JSON.parse(response.content);
            return result.matches === true;
        } catch (err) {
            this.logger.warn("Smart filter failed", err.message);
            return true; // Pass through on error
        }
    }

    /**
     * Get sentiment analysis for a message.
     * @param {string} text - Message text
     * @returns {Promise<{sentiment: string, score: number}>}
     */
    async getSentiment(text) {
        if (!this.aiService?.isAnalysisAvailable()) {
            return { sentiment: "neutral", score: 0 };
        }

        const prompt = `Analyze the sentiment of this text.

Text: ${text.substring(0, 500)}

Respond with JSON: {"sentiment": "positive/negative/neutral", "score": -1 to 1}`;

        try {
            const response = await this.aiService.analyze(prompt);
            return JSON.parse(response.content);
        } catch (err) {
            return { sentiment: "neutral", score: 0 };
        }
    }

    /**
     * Summarize multiple messages into a digest.
     * @param {object[]} messages - Array of message objects
     * @returns {Promise<string>} - Digest summary
     */
    async createDigest(messages) {
        if (!this.aiService?.isAnalysisAvailable() || messages.length === 0) {
            return "No messages to summarize.";
        }

        const messageTexts = messages.slice(0, 20).map((m, i) =>
            `${i + 1}. [${m.source}] ${m.text?.substring(0, 100)}`
        ).join("\n");

        const prompt = `Create a brief digest of these channel messages. Group by topic and highlight key information.

Messages:
${messageTexts}

Create a concise 2-3 paragraph summary.`;

        try {
            const response = await this.aiService.analyze(prompt);
            return response.content;
        } catch (err) {
            this.logger.warn("Digest creation failed", err.message);
            return "Failed to create digest.";
        }
    }
}

module.exports = MonitorService;
