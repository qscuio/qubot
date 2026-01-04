const Logger = require("../core/Logger");

/**
 * BaseProvider - Abstract base class for AI providers.
 * Extend this to add new providers.
 */
class BaseProvider {
    constructor(name, apiKeyEnvName) {
        this.name = name;
        this.apiKeyEnvName = apiKeyEnvName;
        this.logger = new Logger(`Provider:${name}`);
        this.defaultModel = "";
        this.fallbackModels = {}; // { shortName: fullName }
    }

    /**
     * Get API key from config.
     */
    getApiKey(config) {
        return config.get(this.apiKeyEnvName) || "";
    }

    /**
     * Check if provider is configured.
     */
    isConfigured(config) {
        return !!this.getApiKey(config);
    }

    /**
     * Fetch available models from API.
     * Override in subclass for dynamic fetching.
     * @returns {Promise<Array<{id: string, name: string}>>}
     */
    async fetchModels(config) {
        // Default: return fallback models
        return this.getFallbackModels();
    }

    /**
     * Get fallback models (when API unavailable).
     */
    getFallbackModels() {
        return Object.entries(this.fallbackModels).map(([shortName, fullName]) => ({
            id: fullName,
            name: shortName,
        }));
    }

    /**
     * Call the AI provider.
     * @param {string} apiKey - API key
     * @param {string} prompt - User prompt
     * @param {string} model - Model ID
     * @param {Array} history - Chat history [{role, content}]
     * @param {string} contextPrefix - System/context prefix
     * @returns {Promise<{thinking: string, content: string}>}
     */
    async call(apiKey, prompt, model, history = [], contextPrefix = "") {
        throw new Error("call() must be implemented in subclass");
    }
}

module.exports = BaseProvider;
