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

            // Bot Tokens (each bot has its own token)
            RSS_BOT_TOKEN: process.env.RSS_BOT_TOKEN || "",
            AI_BOT_TOKEN: process.env.AI_BOT_TOKEN || "",

            // Webhook Config
            BOT_PORT: parseInt(process.env.BOT_PORT || "3000", 10),
            BOT_SECRET: process.env.BOT_SECRET || "",
            WEBHOOK_URL: process.env.WEBHOOK_URL || "",

            // Monitoring
            SOURCE_CHANNELS: this._parseList(process.env.SOURCE_CHANNELS),
            TARGET_CHANNEL: process.env.TARGET_CHANNEL || "me",
            KEYWORDS: this._parseList(process.env.KEYWORDS, true),
            FROM_USERS: this._parseList(process.env.FROM_USERS),

            // Access Control
            ALLOWED_USERS: this._parseList(process.env.ALLOWED_USERS),

            // Database & Cache
            DATABASE_URL: process.env.DATABASE_URL || "postgresql://qubot:qubot@postgres:5432/qubot",
            REDIS_URL: process.env.REDIS_URL || "",

            // Rate Limiting
            RATE_LIMIT_MS: parseInt(process.env.RATE_LIMIT_MS || "30000", 10),

            // RSS Feature
            RSS_SOURCES: process.env.RSS_SOURCES || "", // JSON string or empty for defaults
            RSS_POLL_INTERVAL_MS: parseInt(process.env.RSS_POLL_INTERVAL_MS || "300000", 10), // 5 min default

            // Logging
            LOG_LEVEL: process.env.LOG_LEVEL || "info",

            // AI Provider Keys
            GROQ_API_KEY: process.env.GROQ_API_KEY || "",
            GEMINI_API_KEY: process.env.GEMINI_API_KEY || "",
            OPENAI_API_KEY: process.env.OPENAI_API_KEY || "",
            CLAUDE_API_KEY: process.env.CLAUDE_API_KEY || "",
            NVIDIA_API_KEY: process.env.NVIDIA_API_KEY || "",

            // GitHub Export
            NOTES_REPO: process.env.NOTES_REPO || "",

            // REST API Configuration
            API_ENABLED: process.env.API_ENABLED !== "false", // true by default
            API_PORT: parseInt(process.env.API_PORT || "3001", 10),
            API_KEYS: process.env.API_KEYS || "",
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
        // No hard requirements - all features gracefully degrade
        // Userbot features require API_ID, API_HASH, SESSION
        // Bot API features require their respective tokens
        // AI features require provider API keys

        if (this.isUserbotConfigured()) {
            logger.info("Userbot (MTProto) configured.");
        } else {
            logger.warn("Userbot not configured (missing API_ID/API_HASH/SESSION). MTProto features disabled.");
        }

        if (!this.config.RSS_BOT_TOKEN && !this.config.AI_BOT_TOKEN) {
            logger.warn("No bot tokens configured. Bot API features disabled.");
        }

        logger.info("Configuration loaded.");
    }

    /**
     * Check if MTProto userbot is configured.
     */
    isUserbotConfigured() {
        return !!(
            this.config.API_ID &&
            !isNaN(this.config.API_ID) &&
            this.config.API_HASH &&
            this.config.SESSION
        );
    }

    get(key) {
        return this.config[key];
    }

    getAll() {
        return { ...this.config };
    }
}

module.exports = ConfigService;
