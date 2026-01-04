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
            NOTES_SSH_KEY_PATH: process.env.NOTES_SSH_KEY_PATH || "/home/ubuntu/.ssh/id_rsa",
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
