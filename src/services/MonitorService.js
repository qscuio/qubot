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
        this.isForwardingEnabled = true; // Can pause forwarding without stopping monitoring
        this.sourceChannels = [];
        this.disabledSources = new Set(); // Track disabled source channels
        this.targetChannelOverride = null; // Runtime override for target channel
        this._messageHandler = this._handleMessage.bind(this);
        this._messageEvent = null;
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

        // Pre-resolve channel entities so gramjs can properly filter messages.
        // This is critical for channels the user hasn't directly interacted with.
        this.logger.info(`Resolving ${this.sourceChannels.length} source channel entities...`);
        this.logger.info(`Source channels from config: ${JSON.stringify(this.sourceChannels)}`);
        const resolvedEntities = await this.telegram.resolveEntities(this.sourceChannels);
        this.logger.info(`Resolved ${resolvedEntities.length} of ${this.sourceChannels.length} channels`);

        // Log each resolved entity
        resolvedEntities.forEach(e => {
            this.logger.info(`  ✓ Resolved: ${e.title || e.username || e.id} (ID: ${e.id}, Type: ${e.className})`);
        });

        if (resolvedEntities.length === 0) {
            throw new Error("Failed to resolve any source channels. Check channel IDs and ensure the userbot has access.");
        }

        // Store resolved IDs for reference (not used for filtering anymore)
        this._resolvedChannelIds = resolvedEntities.map(e => e.id.toString());
        this.logger.info(`Will monitor channel IDs: ${this._resolvedChannelIds.join(', ')}`);

        // Use receiveAll=true to bypass gramjs chat filter (which doesn't work reliably for channels)
        // The handler will filter messages manually based on sourceChannels
        this._messageEvent = this.telegram.addMessageHandler(
            this._messageHandler,
            null,  // No chat filter
            true   // receiveAll = true
        );

        this.isRunning = true;
        this.logger.info("✅ Channel monitoring started successfully (receiving all incoming messages)");
        return { status: "started", channels: resolvedEntities.length };
    }

    /**
     * Stop monitoring channels.
     */
    async stop() {
        if (this.telegram && this._messageEvent) {
            this.telegram.removeMessageHandler(this._messageHandler, this._messageEvent);
            this._messageEvent = null;
        }
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
            forwarding: this.isForwardingEnabled,
            sourceChannels: this.sourceChannels.length,
            enabledSources: this.sourceChannels.filter(c => !this.disabledSources.has(c)).length,
            disabledSources: Array.from(this.disabledSources),
            targetChannel: this._getTargetChannel()
        };
    }

    /**
     * Get the effective target channel (override or config).
     */
    _getTargetChannel() {
        return this.targetChannelOverride || this.config.get("TARGET_CHANNEL");
    }

    /**
     * Set target channel at runtime.
     */
    async setTargetChannel(channelId) {
        this.targetChannelOverride = channelId;
        this.logger.info(`Target channel set to: ${channelId}`);
        return { targetChannel: channelId };
    }

    /**
     * Reset target channel to config default.
     */
    async resetTargetChannel() {
        this.targetChannelOverride = null;
        const target = this.config.get("TARGET_CHANNEL");
        this.logger.info(`Target channel reset to config: ${target}`);
        return { targetChannel: target };
    }

    /**
     * Enable/disable forwarding without stopping monitoring.
     */
    async setForwarding(enabled) {
        this.isForwardingEnabled = enabled;
        this.logger.info(`Forwarding ${enabled ? "enabled" : "disabled"}`);
        return { forwarding: enabled };
    }

    /**
     * Enable a source channel.
     */
    async enableSource(channelId) {
        if (this.disabledSources.has(channelId)) {
            this.disabledSources.delete(channelId);
            this.logger.info(`Enabled source channel: ${channelId}`);
        }
        return { enabled: true, channel: channelId };
    }

    /**
     * Disable a source channel (still monitored but not forwarded).
     */
    async disableSource(channelId) {
        if (this.sourceChannels.includes(channelId)) {
            this.disabledSources.add(channelId);
            this.logger.info(`Disabled source channel: ${channelId}`);
        }
        return { enabled: false, channel: channelId };
    }

    /**
     * Check if a source channel is enabled.
     */
    isSourceEnabled(channelId) {
        return !this.disabledSources.has(channelId);
    }

    /**
     * Get all monitored sources.
     */
    async getSources() {
        return {
            channels: this.sourceChannels.map(c => ({
                id: c,
                enabled: !this.disabledSources.has(c)
            })),
            keywords: this.config.get("KEYWORDS") || [],
            users: this.config.get("FROM_USERS") || [],
            targetChannel: this._getTargetChannel()
        };
    }

    /**
     * Add a new source channel.
     */
    async addSource(channelId) {
        if (!this.sourceChannels.includes(channelId)) {
            // Resolve the entity first to ensure gramjs can receive updates from it
            if (this.telegram) {
                const entity = await this.telegram.resolveEntity(channelId);
                if (entity) {
                    this.logger.info(`Resolved new source: ${entity.title || entity.username || channelId}`);
                } else {
                    this.logger.warn(`Could not resolve channel: ${channelId}`);
                }
            }
            this.sourceChannels.push(channelId);
            this.logger.info(`Added source channel: ${channelId}`);
            await this._refreshHandlers();
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
            await this._refreshHandlers();
        }
        return { channels: this.sourceChannels };
    }

    async _refreshHandlers() {
        if (!this.isRunning || !this.telegram) return;

        if (this._messageEvent) {
            this.telegram.removeMessageHandler(this._messageHandler, this._messageEvent);
            this._messageEvent = null;
        }

        if (this.sourceChannels.length === 0) {
            this.isRunning = false;
            this.logger.info("Channel monitoring stopped (no source channels).");
            return;
        }

        // Re-resolve entities when refreshing handlers
        const resolvedEntities = await this.telegram.resolveEntities(this.sourceChannels);
        if (resolvedEntities.length === 0) {
            this.logger.warn("Failed to resolve any source channels during refresh.");
            return;
        }

        this._resolvedChannelIds = resolvedEntities.map(e => e.id.toString());

        // Use receiveAll mode - handler filters manually
        this._messageEvent = this.telegram.addMessageHandler(
            this._messageHandler,
            null,
            true
        );
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

        await this.storage.ensureMonitorTables();

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
        if (!userId) {
            return [];
        }

        try {
            await this.storage.ensureMonitorTables();
            const result = await this.storage.pool.query(
                `SELECT * FROM monitor_history 
                 WHERE user_id = $1
                 ORDER BY created_at DESC 
                 LIMIT $2`,
                [userId, limit]
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
            if (!this.isRunning) {
                this.logger.debug("Message received but monitoring not running");
                return;
            }
            const msg = event.message;
            if (!msg || !msg.message) {
                this.logger.debug("Empty message received, skipping");
                return;
            }

            const chat = await msg.getChat().catch(() => null);
            const chatUsername = chat?.username;
            const chatTitle = chat?.title || "Unknown";
            const rawChatId = chat?.id?.toString() || "";

            // Log every incoming message for debugging
            this.logger.info(`📨 Message received from: ${chatTitle} (@${chatUsername || 'N/A'}) [${rawChatId}]`);
            this.logger.debug(`Message preview: ${msg.message.substring(0, 100)}...`);

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

            if (!isMonitored) {
                this.logger.debug(`Message not from monitored source. Sources: ${JSON.stringify(this.sourceChannels)}`);
                return;
            }

            this.logger.info(`✅ Message matches monitored source: ${chatTitle}`);

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
                    this.logger.debug(`Message filtered by FROM_USERS. Sender: ${senderUsername || senderId}`);
                    return;
                }
            }

            // Keyword filter (global config)
            // Skip filtering if keywords is empty or set to "none"
            const keywords = this.config.get("KEYWORDS") || [];
            const skipKeywordFilter = keywords.length === 0 ||
                (keywords.length === 1 && keywords[0].toLowerCase() === "none");

            if (!skipKeywordFilter) {
                const lowerText = msg.message.toLowerCase();
                const hasKeyword = keywords.some(k => lowerText.includes(k));
                if (!hasKeyword) {
                    this.logger.debug(`Message filtered by KEYWORDS. Keywords: ${JSON.stringify(keywords)}`);
                    return;
                }
                this.logger.info(`✅ Message matches keyword filter`);
            } else {
                this.logger.debug(`Keyword filter skipped (no keywords configured)`);
            }

            // Create message object
            const messageObj = {
                id: msg.id,
                text: msg.message,
                source: sourceName,
                sourceId: rawChatId,
                timestamp: new Date().toISOString()
            };

            // Check if source is disabled or forwarding is paused
            const matchingSource = this.sourceChannels.find(source => {
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

            const shouldForward = this.isForwardingEnabled &&
                matchingSource &&
                !this.disabledSources.has(matchingSource);

            // Forward to Telegram TARGET_CHANNEL
            if (shouldForward) {
                const targetChannel = this._getTargetChannel();
                if (targetChannel && this.telegram) {
                    const formattedMessage = this._formatMessage(msg.message, sourceName);
                    await this.telegram.sendMessage(targetChannel, {
                        message: formattedMessage
                    });
                    this.logger.info(`Forwarded message from ${sourceName} to ${targetChannel}`);
                }
            } else {
                this.logger.debug(`Skipped forwarding from ${sourceName} (forwarding=${this.isForwardingEnabled}, source enabled=${!this.disabledSources.has(matchingSource)})`);
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
            await this.storage.ensureMonitorTables();
            const userIds = this._getHistoryUserIds();
            if (userIds.length === 0) return;

            for (const userId of userIds) {
                const filters = await this.getFilters(userId);
                if (!this._matchesFilters(messageObj, filters)) {
                    continue;
                }

                await this.storage.pool.query(
                    `INSERT INTO monitor_history (user_id, source, source_id, message, created_at)
                     VALUES ($1, $2, $3, $4, NOW())`,
                    [userId, messageObj.source, messageObj.sourceId, messageObj.text]
                );
            }
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

    _matchesFilters(messageObj, filters) {
        if (!filters?.enabled) return false;

        if (filters.channels?.length > 0) {
            const matchesChannel = filters.channels.some(ch =>
                ch === messageObj.source ||
                ch === messageObj.sourceId ||
                ch === `@${messageObj.source}`
            );
            if (!matchesChannel) return false;
        }

        if (filters.keywords?.length > 0) {
            const lowerText = (messageObj.text || "").toLowerCase();
            const hasKeyword = filters.keywords.some(k =>
                lowerText.includes(String(k).toLowerCase())
            );
            if (!hasKeyword) return false;
        }

        return true;
    }

    _getHistoryUserIds() {
        const ids = new Set();
        const apiKeysStr = this.config.get("API_KEYS") || "";

        if (apiKeysStr) {
            const keys = apiKeysStr.split(",").map(k => k.trim()).filter(Boolean);
            keys.forEach((keyEntry, index) => {
                if (keyEntry.includes(":")) {
                    const [, userId] = keyEntry.split(":");
                    const parsed = parseInt(userId.trim(), 10);
                    if (!isNaN(parsed)) {
                        ids.add(parsed);
                    }
                } else {
                    ids.add(index + 1);
                }
            });
        }

        const allowedUsers = this.config.get("ALLOWED_USERS") || [];
        for (const user of allowedUsers) {
            const parsed = parseInt(user, 10);
            if (!isNaN(parsed)) {
                ids.add(parsed);
            }
        }

        return Array.from(ids);
    }

    // Table creation is centralized in StorageService.

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
        try {
            return await this.aiService.matchFilter(text, criteria);
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
        try {
            return await this.aiService.getSentiment(text);
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
        try {
            return await this.aiService.createDigest(messages);
        } catch (err) {
            this.logger.warn("Digest creation failed", err.message);
            return "Failed to create digest.";
        }
    }
}

module.exports = MonitorService;
