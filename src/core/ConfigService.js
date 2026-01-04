require("dotenv").config();
const Logger = require("./Logger");

const logger = new Logger("ConfigService");

/**
 * ConfigService - Loads and validates environment variables.
 */
class ConfigService {
    constructor() {
        this.config = this._load();
        this._validate();
    }

    _load() {
        return {
            // Telegram API (Userbot)
            API_ID: parseInt(process.env.API_ID || "", 10),
            API_HASH: process.env.API_HASH || "",
            SESSION: process.env.TG_SESSION || "",

            // Telegram Bot Token (for commands)
            BOT_TOKEN: process.env.BOT_TOKEN || "",

            // Monitoring
            SOURCE_CHANNELS: this._parseList(process.env.SOURCE_CHANNELS),
            TARGET_CHANNEL: process.env.TARGET_CHANNEL || "me",
            KEYWORDS: this._parseList(process.env.KEYWORDS, true),
            FROM_USERS: this._parseList(process.env.FROM_USERS),

            // Database (internal docker-compose PostgreSQL)
            DATABASE_URL: process.env.DATABASE_URL || "postgresql://qubot:qubot@postgres:5432/qubot",

            // Rate Limiting
            RATE_LIMIT_MS: parseInt(process.env.RATE_LIMIT_MS || "30000", 10),

            // RSS Feature
            RSS_SOURCES: process.env.RSS_SOURCES || "", // JSON string or empty for defaults
            RSS_POLL_INTERVAL_MS: parseInt(process.env.RSS_POLL_INTERVAL_MS || "300000", 10), // 5 min default

            // Logging
            LOG_LEVEL: process.env.LOG_LEVEL || "info",
        };
    }

    _parseList(value, lowercase = false) {
        if (!value) return [];
        return value
            .split(",")
            .map((s) => (lowercase ? s.trim().toLowerCase() : s.trim()))
            .filter(Boolean);
    }

    _validate() {
        const required = ["API_ID", "API_HASH", "SESSION"];
        for (const key of required) {
            if (!this.config[key] || (key === "API_ID" && isNaN(this.config[key]))) {
                logger.error(`Missing required config: ${key}`);
                throw new Error(`Missing required config: ${key}`);
            }
        }
        logger.info("Configuration loaded and validated.");
    }

    get(key) {
        return this.config[key];
    }

    getAll() {
        return { ...this.config };
    }
}

module.exports = ConfigService;
