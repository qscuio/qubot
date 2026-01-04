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

        try {
            await this.pool.query(createSourcesTable);
            await this.pool.query(createSubscriptionsTable);
            await this.pool.query(createContentsTable);
            logger.info("Database tables initialized.");
        } catch (err) {
            logger.error("Failed to create tables", err);
            throw err;
        }
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

    async close() {
        if (this.pool) {
            await this.pool.end();
            logger.info("Database connection closed.");
        }
    }
}

module.exports = StorageService;
