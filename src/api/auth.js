const Logger = require("../core/Logger");

const logger = new Logger("Auth");

/**
 * API Key Authentication Middleware.
 * 
 * Validates requests using the Authorization header.
 * Format: Authorization: Bearer <API_KEY>
 * 
 * API keys are mapped to user IDs for multi-user support.
 */

/**
 * Parse API_KEYS config into a map of key -> userId.
 * Format: "key1:userId1,key2:userId2" or just "key1,key2" (userId = index)
 */
function parseApiKeys(config) {
    const apiKeysStr = config.get("API_KEYS") || "";
    const keyMap = new Map();

    if (!apiKeysStr) {
        return keyMap;
    }

    const keys = apiKeysStr.split(",").map(k => k.trim()).filter(k => k);

    keys.forEach((keyEntry, index) => {
        if (keyEntry.includes(":")) {
            const [key, userId] = keyEntry.split(":");
            keyMap.set(key.trim(), parseInt(userId.trim(), 10) || index + 1);
        } else {
            // If no userId specified, use the key itself as identifier
            keyMap.set(keyEntry, index + 1);
        }
    });

    return keyMap;
}

/**
 * Create authentication middleware.
 */
function createAuthMiddleware(config) {
    const apiKeys = parseApiKeys(config);

    if (apiKeys.size === 0) {
        logger.warn("No API_KEYS configured. API will reject all authenticated requests.");
    } else {
        logger.info(`Loaded ${apiKeys.size} API key(s)`);
    }

    return (req, res, next) => {
        const authHeader = req.headers.authorization;

        if (!authHeader || !authHeader.startsWith("Bearer ")) {
            return res.status(401).json({
                error: "Unauthorized",
                message: "Missing or invalid Authorization header. Use: Bearer <API_KEY>"
            });
        }

        const token = authHeader.substring(7); // Remove "Bearer "

        if (!apiKeys.has(token)) {
            logger.warn(`Invalid API key attempt: ${token.substring(0, 8)}...`);
            return res.status(401).json({
                error: "Unauthorized",
                message: "Invalid API key"
            });
        }

        // Attach user context to request
        req.userId = apiKeys.get(token);
        req.apiKey = token;

        next();
    };
}

/**
 * Validate API key (for WebSocket auth).
 * Returns userId if valid, null otherwise.
 */
function validateApiKey(config, token) {
    const apiKeys = parseApiKeys(config);
    return apiKeys.get(token) || null;
}

module.exports = {
    createAuthMiddleware,
    validateApiKey,
    parseApiKeys
};
