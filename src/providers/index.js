/**
 * AI Provider Registry
 * Central place to register and access all AI providers.
 */

const GroqProvider = require("./groq");
const GeminiProvider = require("./gemini");
const OpenAIProvider = require("./openai");
const ClaudeProvider = require("./claude");
const NvidiaProvider = require("./nvidia");

// Provider instances
const providers = {
    groq: new GroqProvider(),
    gemini: new GeminiProvider(),
    openai: new OpenAIProvider(),
    claude: new ClaudeProvider(),
    nvidia: new NvidiaProvider(),
};

const DEFAULT_PROVIDER = "groq";

/**
 * Get provider by key.
 */
function getProvider(key) {
    return providers[key] || null;
}

/**
 * List all providers.
 */
function listProviders() {
    return Object.entries(providers).map(([key, p]) => ({
        key,
        name: p.name,
        defaultModel: p.defaultModel,
    }));
}

/**
 * Get available providers for a given config (those with API keys set).
 */
function getAvailableProviders(config) {
    return Object.entries(providers)
        .filter(([, p]) => p.isConfigured(config))
        .map(([key, p]) => ({
            key,
            name: p.name,
            defaultModel: p.defaultModel,
        }));
}

/**
 * Fetch models for a provider.
 */
async function fetchModels(providerKey, config) {
    const provider = providers[providerKey];
    if (!provider) return [];
    return provider.fetchModels(config);
}

/**
 * Call AI provider.
 */
async function callAI(providerKey, config, prompt, model, history = [], contextPrefix = "") {
    const provider = providers[providerKey];
    if (!provider) throw new Error(`Unknown provider: ${providerKey}`);

    const apiKey = provider.getApiKey(config);
    return provider.call(apiKey, prompt, model, history, contextPrefix);
}

/**
 * Register a new provider (for extensibility).
 */
function registerProvider(key, provider) {
    providers[key] = provider;
}

module.exports = {
    DEFAULT_PROVIDER,
    getProvider,
    listProviders,
    getAvailableProviders,
    fetchModels,
    callAI,
    registerProvider,
};
