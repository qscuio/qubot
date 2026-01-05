const { Pool } = require("pg");
const Logger = require("./Logger");

const logger = new Logger("StorageService");

/**
 * StorageService - PostgreSQL storage for RSS subscriptions.
 */
class StorageService {
    constructor(configService) {
        this.config = configService;
        this.pool = null;
    }

    async init() {
        const databaseUrl = this.config.get("DATABASE_URL");
        if (!databaseUrl) {
            logger.warn("DATABASE_URL not set. Storage features disabled.");
            return false;
        }

        this.pool = new Pool({
            connectionString: databaseUrl,
        });

        // Test connection
        try {
            await this.pool.query("SELECT NOW()");
            logger.info("✅ Connected to PostgreSQL.");
        } catch (err) {
            logger.error("Failed to connect to PostgreSQL", err);
            return false;
        }

        // Create tables
        await this._createTables();
        return true;
    }

    async _createTables() {
        const createSourcesTable = `
            CREATE TABLE IF NOT EXISTS sources (
                id SERIAL PRIMARY KEY,
                link TEXT UNIQUE NOT NULL,
                title TEXT,
                error_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        `;

        const createSubscriptionsTable = `
            CREATE TABLE IF NOT EXISTS subscriptions (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                enable_notification BOOLEAN DEFAULT TRUE,
                tag TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, source_id)
            );
        `;

        const createContentsTable = `
            CREATE TABLE IF NOT EXISTS contents (
                hash_id TEXT PRIMARY KEY,
                source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                raw_id TEXT,
                raw_link TEXT,
                title TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        `;

        // AI Chat tables
        const createAiChatsTable = `
            CREATE TABLE IF NOT EXISTS ai_chats (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                title TEXT DEFAULT 'New Chat',
                summary TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        `;

        const createAiMessagesTable = `
            CREATE TABLE IF NOT EXISTS ai_messages (
                id SERIAL PRIMARY KEY,
                chat_id INTEGER NOT NULL REFERENCES ai_chats(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        `;

        const createAiSettingsTable = `
            CREATE TABLE IF NOT EXISTS ai_settings (
                user_id BIGINT PRIMARY KEY,
                provider TEXT DEFAULT 'groq',
                model TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        `;

        try {
            await this.pool.query(createSourcesTable);
            await this.pool.query(createSubscriptionsTable);
            await this.pool.query(createContentsTable);
            await this.pool.query(createAiChatsTable);
            await this.pool.query(createAiMessagesTable);
            await this.pool.query(createAiSettingsTable);
            await this.ensureMonitorTables();
            logger.info("Database tables initialized.");
        } catch (err) {
            logger.error("Failed to create tables", err);
            throw err;
        }
    }

    async ensureMonitorTables() {
        const createMonitorFiltersTable = `
            CREATE TABLE IF NOT EXISTS monitor_filters (
                user_id BIGINT PRIMARY KEY,
                filters JSONB NOT NULL DEFAULT '{}',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );
        `;

        const createMonitorHistoryTable = `
            CREATE TABLE IF NOT EXISTS monitor_history (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                source VARCHAR(255) NOT NULL,
                source_id VARCHAR(255),
                message TEXT,
                ai_summary TEXT,
                ai_sentiment VARCHAR(50),
                ai_topics JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            );
        `;

        await this.pool.query(createMonitorFiltersTable);
        await this.pool.query(createMonitorHistoryTable);
        await this.pool.query(`
            ALTER TABLE monitor_history
            ADD COLUMN IF NOT EXISTS user_id BIGINT
        `);
        await this.pool.query(`
            CREATE INDEX IF NOT EXISTS monitor_history_user_id_idx
            ON monitor_history (user_id)
        `);
    }

    // ============= Source Methods =============

    async createSource(link, title) {
        const result = await this.pool.query(
            `INSERT INTO sources (link, title) VALUES ($1, $2)
             ON CONFLICT (link) DO UPDATE SET title = EXCLUDED.title
             RETURNING *`,
            [link, title]
        );
        return result.rows[0];
    }

    async getSourceByLink(link) {
        const result = await this.pool.query(
            "SELECT * FROM sources WHERE link = $1",
            [link]
        );
        return result.rows[0] || null;
    }

    async getSourceById(id) {
        const result = await this.pool.query(
            "SELECT * FROM sources WHERE id = $1",
            [id]
        );
        return result.rows[0] || null;
    }

    async getAllSources() {
        const result = await this.pool.query(
            "SELECT * FROM sources WHERE error_count < 5"
        );
        return result.rows;
    }

    async incrementSourceErrorCount(sourceId) {
        await this.pool.query(
            "UPDATE sources SET error_count = error_count + 1 WHERE id = $1",
            [sourceId]
        );
    }

    async clearSourceErrorCount(sourceId) {
        await this.pool.query(
            "UPDATE sources SET error_count = 0 WHERE id = $1",
            [sourceId]
        );
    }

    async deleteSource(sourceId) {
        await this.pool.query("DELETE FROM sources WHERE id = $1", [sourceId]);
    }

    // ============= Subscription Methods =============

    async addSubscription(userId, sourceId) {
        try {
            await this.pool.query(
                `INSERT INTO subscriptions (user_id, source_id) VALUES ($1, $2)`,
                [userId, sourceId]
            );
            return true;
        } catch (err) {
            if (err.code === "23505") {
                // Unique violation
                return false; // Already subscribed
            }
            throw err;
        }
    }

    async removeSubscription(userId, sourceId) {
        const result = await this.pool.query(
            "DELETE FROM subscriptions WHERE user_id = $1 AND source_id = $2",
            [userId, sourceId]
        );
        return result.rowCount > 0;
    }

    async getSubscriptionsByUser(userId) {
        const result = await this.pool.query(
            `SELECT s.*, src.link, src.title 
             FROM subscriptions s 
             JOIN sources src ON s.source_id = src.id 
             WHERE s.user_id = $1 
             ORDER BY s.created_at DESC`,
            [userId]
        );
        return result.rows;
    }

    async getSubscribersBySource(sourceId) {
        const result = await this.pool.query(
            "SELECT * FROM subscriptions WHERE source_id = $1",
            [sourceId]
        );
        return result.rows;
    }

    async subscriptionExists(userId, sourceId) {
        const result = await this.pool.query(
            "SELECT 1 FROM subscriptions WHERE user_id = $1 AND source_id = $2",
            [userId, sourceId]
        );
        return result.rows.length > 0;
    }

    // ============= Content Methods (Deduplication) =============

    async contentExists(hashId) {
        const result = await this.pool.query(
            "SELECT 1 FROM contents WHERE hash_id = $1",
            [hashId]
        );
        return result.rows.length > 0;
    }

    async addContent(hashId, sourceId, rawId, rawLink, title) {
        try {
            await this.pool.query(
                `INSERT INTO contents (hash_id, source_id, raw_id, raw_link, title)
                 VALUES ($1, $2, $3, $4, $5)
                 ON CONFLICT (hash_id) DO NOTHING`,
                [hashId, sourceId, rawId, rawLink, title]
            );
            return true;
        } catch (err) {
            logger.error("Failed to add content", err);
            return false;
        }
    }

    // ============= AI Chat Methods =============

    async getOrCreateActiveChat(userId) {
        // Find active chat
        let result = await this.pool.query(
            "SELECT * FROM ai_chats WHERE user_id = $1 AND is_active = TRUE ORDER BY updated_at DESC LIMIT 1",
            [userId]
        );

        if (result.rows.length > 0) {
            return result.rows[0];
        }

        // Create new chat
        result = await this.pool.query(
            "INSERT INTO ai_chats (user_id) VALUES ($1) RETURNING *",
            [userId]
        );
        return result.rows[0];
    }

    async createNewChat(userId) {
        // Deactivate all existing chats
        await this.pool.query(
            "UPDATE ai_chats SET is_active = FALSE WHERE user_id = $1",
            [userId]
        );

        // Create new active chat
        const result = await this.pool.query(
            "INSERT INTO ai_chats (user_id) VALUES ($1) RETURNING *",
            [userId]
        );
        return result.rows[0];
    }

    async getChatById(chatId) {
        const result = await this.pool.query(
            "SELECT * FROM ai_chats WHERE id = $1",
            [chatId]
        );
        return result.rows[0] || null;
    }

    async getUserChats(userId, limit = 10) {
        const result = await this.pool.query(
            "SELECT * FROM ai_chats WHERE user_id = $1 ORDER BY updated_at DESC LIMIT $2",
            [userId, limit]
        );
        return result.rows;
    }

    async setActiveChat(userId, chatId) {
        await this.pool.query(
            "UPDATE ai_chats SET is_active = FALSE WHERE user_id = $1",
            [userId]
        );
        await this.pool.query(
            "UPDATE ai_chats SET is_active = TRUE, updated_at = CURRENT_TIMESTAMP WHERE id = $1",
            [chatId]
        );
    }

    async renameChat(chatId, title) {
        await this.pool.query(
            "UPDATE ai_chats SET title = $1, updated_at = CURRENT_TIMESTAMP WHERE id = $2",
            [title, chatId]
        );
    }

    async updateChatSummary(chatId, summary) {
        await this.pool.query(
            "UPDATE ai_chats SET summary = $1, updated_at = CURRENT_TIMESTAMP WHERE id = $2",
            [summary, chatId]
        );
    }

    async deleteChat(chatId) {
        await this.pool.query("DELETE FROM ai_chats WHERE id = $1", [chatId]);
    }

    // ============= AI Message Methods =============

    async saveMessage(chatId, role, content) {
        const result = await this.pool.query(
            "INSERT INTO ai_messages (chat_id, role, content) VALUES ($1, $2, $3) RETURNING *",
            [chatId, role, content]
        );

        // Update chat timestamp
        await this.pool.query(
            "UPDATE ai_chats SET updated_at = CURRENT_TIMESTAMP WHERE id = $1",
            [chatId]
        );

        return result.rows[0];
    }

    async getChatMessages(chatId, limit = 10) {
        const result = await this.pool.query(
            "SELECT * FROM ai_messages WHERE chat_id = $1 ORDER BY created_at DESC LIMIT $2",
            [chatId, limit]
        );
        return result.rows;
    }

    async getMessageCount(chatId) {
        const result = await this.pool.query(
            "SELECT COUNT(*) FROM ai_messages WHERE chat_id = $1",
            [chatId]
        );
        return parseInt(result.rows[0].count, 10);
    }

    async clearChatMessages(chatId) {
        await this.pool.query("DELETE FROM ai_messages WHERE chat_id = $1", [chatId]);
    }

    // ============= AI Settings Methods =============

    async getAiSettings(userId) {
        const result = await this.pool.query(
            "SELECT * FROM ai_settings WHERE user_id = $1",
            [userId]
        );

        if (result.rows.length === 0) {
            // Create default settings
            await this.pool.query(
                "INSERT INTO ai_settings (user_id, provider, model) VALUES ($1, 'groq', 'llama-3.3-70b-versatile')",
                [userId]
            );
            return { user_id: userId, provider: "groq", model: "llama-3.3-70b-versatile" };
        }

        return result.rows[0];
    }

    async updateAiSettings(userId, provider, model) {
        await this.pool.query(
            `INSERT INTO ai_settings (user_id, provider, model) VALUES ($1, $2, $3)
             ON CONFLICT (user_id) DO UPDATE SET provider = $2, model = $3, updated_at = CURRENT_TIMESTAMP`,
            [userId, provider, model]
        );
    }

    // ============= RSS Bot Convenience Methods =============

    /**
     * Add an RSS subscription by URL (creates source if needed).
     * @param {number} userId - Telegram user ID
     * @param {number} chatId - Telegram chat ID (unused but kept for API compatibility)
     * @param {string} url - RSS feed URL
     * @param {string} title - Feed title
     * @returns {boolean} - true if added, false if already subscribed
     */
    async addRssSubscription(userId, chatId, url, title) {
        // Create or get the source
        const source = await this.createSource(url, title);
        // Add subscription
        return await this.addSubscription(userId, source.id);
    }

    /**
     * Get all RSS subscriptions for a user.
     * @param {number} userId - Telegram user ID
     * @returns {Array} - Array of subscriptions with url and title
     */
    async getRssSubscriptions(userId) {
        const subs = await this.getSubscriptionsByUser(userId);
        return subs.map(s => ({
            id: s.source_id,
            url: s.link,
            title: s.title,
            created_at: s.created_at
        }));
    }

    /**
     * Remove an RSS subscription by URL.
     * @param {number} userId - Telegram user ID
     * @param {string} url - RSS feed URL
     * @returns {boolean} - true if removed, false if not found
     */
    async removeRssSubscription(userId, url) {
        const source = await this.getSourceByLink(url);
        if (!source) {
            return false;
        }
        return await this.removeSubscription(userId, source.id);
    }

    async close() {
        if (this.pool) {
            await this.pool.end();
            logger.info("Database connection closed.");
        }
    }
}

module.exports = StorageService;
