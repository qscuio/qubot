const Redis = require("ioredis");
const Logger = require("./Logger");

const logger = new Logger("CacheService");

/**
 * CacheService - Redis-based caching layer.
 */
class CacheService {
    constructor(config) {
        this.config = config;
        this.client = null;
        this.enabled = false;
    }

    async init() {
        const redisUrl = this.config.get("REDIS_URL");
        if (!redisUrl) {
            logger.warn("REDIS_URL not set. Caching disabled.");
            return false;
        }

        try {
            this.client = new Redis(redisUrl, {
                maxRetriesPerRequest: 3,
                retryDelayOnFailover: 100,
            });

            this.client.on("error", (err) => {
                logger.error("Redis error:", err.message);
            });

            await this.client.ping();
            this.enabled = true;
            logger.info("✅ Connected to Redis.");
            return true;
        } catch (err) {
            logger.warn(`Redis connection failed: ${err.message}. Caching disabled.`);
            return false;
        }
    }

    isEnabled() {
        return this.enabled;
    }

    async get(key) {
        if (!this.enabled) return null;
        try {
            const value = await this.client.get(key);
            return value ? JSON.parse(value) : null;
        } catch (err) {
            return null;
        }
    }

    async set(key, value, ttlSeconds = 3600) {
        if (!this.enabled) return;
        try {
            await this.client.set(key, JSON.stringify(value), "EX", ttlSeconds);
        } catch (err) {
            // Ignore
        }
    }

    async del(key) {
        if (!this.enabled) return;
        try {
            await this.client.del(key);
        } catch (err) {
            // Ignore
        }
    }

    async getOrSet(key, fetchFn, ttlSeconds = 3600) {
        const cached = await this.get(key);
        if (cached !== null) return cached;

        const value = await fetchFn();
        await this.set(key, value, ttlSeconds);
        return value;
    }

    async close() {
        if (this.client) {
            await this.client.quit();
            logger.info("Redis connection closed.");
        }
    }
}

module.exports = CacheService;
