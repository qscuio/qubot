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
            // Telegram API
            API_ID: parseInt(process.env.API_ID || "", 10),
            API_HASH: process.env.API_HASH || "",
            SESSION: process.env.TG_SESSION || "",

            // Monitoring
            SOURCE_CHANNELS: this._parseList(process.env.SOURCE_CHANNELS),
            TARGET_CHANNEL: process.env.TARGET_CHANNEL || "me",
            KEYWORDS: this._parseList(process.env.KEYWORDS, true),
            FROM_USERS: this._parseList(process.env.FROM_USERS),

            // Rate Limiting
            RATE_LIMIT_MS: parseInt(process.env.RATE_LIMIT_MS || "30000", 10),

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
