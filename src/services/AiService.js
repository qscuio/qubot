const Logger = require("../core/Logger");
const { getProvider, listProviders, fetchModels, callAI } = require("../providers");
const { buildJobPrompt, getJobDefinition, listJobs } = require("./ai/PromptCatalog");

const DEFAULT_PROVIDER = "groq";

/**
 * AiService - Business logic for AI chat and task execution.
 * Decoupled from Telegram, can be used by REST API or any frontend.
 */
class AiService {
    constructor(config, storage, githubService) {
        this.config = config;
        this.storage = storage;
        this.githubService = githubService;
        this.logger = new Logger("AiService");
        this.cachedModels = new Map();
    }

    /**
     * Get user's AI settings (provider/model).
     */
    async getSettings(userId) {
        if (!this.storage) {
            const provider = getProvider(DEFAULT_PROVIDER);
            return { provider: DEFAULT_PROVIDER, model: provider?.defaultModel || "" };
        }
        return await this.storage.getAiSettings(userId);
    }

    /**
     * Update user's AI settings.
     */
    async updateSettings(userId, provider, model) {
        let resolvedProvider = provider;
        let resolvedModel = model;

        if (!resolvedProvider) {
            const current = await this.getSettings(userId);
            resolvedProvider = current.provider;
            resolvedModel = resolvedModel || current.model;
        }

        const providerInstance = getProvider(resolvedProvider);
        if (!resolvedModel) {
            resolvedModel = providerInstance?.defaultModel || "";
        }

        if (this.storage) {
            await this.storage.updateAiSettings(userId, resolvedProvider, resolvedModel);
        }
        return { provider: resolvedProvider, model: resolvedModel };
    }

    /**
     * List available AI providers.
     */
    listProviders() {
        return listProviders().map(p => ({
            key: p.key,
            name: p.name,
            configured: getProvider(p.key)?.isConfigured?.(this.config) || false
        }));
    }

    /**
     * List supported AI job types.
     */
    listJobs() {
        return listJobs();
    }

    /**
     * Get a job definition by id.
     */
    getJob(jobId) {
        return getJobDefinition(jobId);
    }

    /**
     * Get available models for a provider.
     */
    async getModels(providerKey) {
        if (this.cachedModels.has(providerKey)) {
            return this.cachedModels.get(providerKey);
        }
        const models = await fetchModels(providerKey, this.config);
        this.cachedModels.set(providerKey, models);
        return models;
    }

    /**
     * Run a well-defined AI job by id.
     */
    async runJob(jobId, payload = {}, options = {}) {
        const { system, prompt } = buildJobPrompt(jobId, payload);
        const provider = options.provider || this._getDefaultProvider();
        const model = options.model || getProvider(provider)?.defaultModel;

        if (!provider || !getProvider(provider)?.isConfigured?.(this.config)) {
            throw new Error(`No AI provider configured for ${jobId}`);
        }

        const history = options.history || [];
        const contextPrefix = this._joinContext(system, options.contextPrefix);
        const retries = Number.isInteger(options.retries) ? options.retries : 1;

        return await this._callAIWithRetry(provider, prompt, model, history, contextPrefix, retries);
    }

    async _runJsonJob(jobId, payload, options, fallback) {
        try {
            const response = await this.runJob(jobId, payload, options);
            return this._parseJson(response.content, fallback, jobId);
        } catch (err) {
            this.logger.warn(`${jobId} failed`, err.message);
            return fallback;
        }
    }

    _parseJson(content, fallback, label) {
        if (!content) return fallback;
        try {
            return JSON.parse(content);
        } catch (err) {
            this.logger.warn(`${label} JSON parse failed`, err.message);
            return fallback;
        }
    }

    _joinContext(system, extra) {
        const parts = [];
        if (system) parts.push(system);
        if (extra) parts.push(extra);
        return parts.join("\n\n");
    }

    // ============================================================
    // PUBLIC AI TASK METHODS (for use by other services)
    // ============================================================

    /**
     * Analyze content with AI (general-purpose, no user context needed).
     * This is the main method for other services to call.
     * @param {string} prompt - The analysis prompt
     * @param {object} options - Optional settings
     * @returns {Promise<{content: string, thinking?: string}>}
     */
    async analyze(prompt, options = {}) {
        return await this.runJob("analysis", { prompt }, options);
    }

    /**
     * Summarize text content.
     * @param {string} text - Text to summarize
     * @param {number} maxLength - Max summary length (default 200)
     */
    async summarize(text, maxLength = 200, options = {}) {
        if (!text || text.length < 50) {
            return text; // Too short to summarize
        }

        const response = await this.runJob("summarize", { text, maxLength }, options);
        return response.content || text.substring(0, maxLength);
    }

    /**
     * Translate text between languages.
     */
    async translate(text, targetLanguage, sourceLanguage = "", options = {}) {
        if (!text) return "";
        const response = await this.runJob(
            "translate",
            { text, targetLanguage, sourceLanguage },
            options
        );
        return response.content || "";
    }

    /**
     * Language tutoring with corrections and practice.
     */
    async languageLearning(text, targetLanguage, level = "intermediate", goal = "", options = {}) {
        if (!text) return "";
        const response = await this.runJob(
            "language_learning",
            { text, targetLanguage, level, goal },
            options
        );
        return response.content || "";
    }

    /**
     * Research brief with cautious sourcing.
     */
    async research(question, sources = [], options = {}) {
        if (!question) return "";
        const response = await this.runJob(
            "research",
            { question, sources },
            options
        );
        return response.content || "";
    }

    /**
     * Categorize content into predefined categories.
     * @param {string} text - Text to categorize
     * @param {string[]} categories - List of possible categories
     * @returns {Promise<{category: string, confidence: string, reasoning: string}>}
     */
    async categorize(text, categories, options = {}) {
        if (!categories || categories.length === 0) {
            return { category: "uncategorized", confidence: "low", reasoning: "No categories provided" };
        }

        const fallback = { category: categories[0], confidence: "low", reasoning: "AI parsing failed" };
        return await this._runJsonJob("categorize", { text, categories }, options, fallback);
    }

    /**
     * Extract key information from text.
     * @param {string} text - Text to analyze
     * @param {string[]} fields - Fields to extract (e.g., ["topic", "sentiment", "entities"])
     */
    async extract(text, fields, options = {}) {
        const fallback = (fields || []).reduce((acc, f) => ({ ...acc, [f]: null }), {});
        return await this._runJsonJob("extract", { text, fields }, options, fallback);
    }

    /**
     * Plan tool usage for coding tasks.
     */
    async planToolUse(task, tools = [], constraints = "", options = {}) {
        const fallback = { plan: [], tool_calls: [], final_note: "AI not available." };
        return await this._runJsonJob(
            "coding_tool_use",
            { task, tools, constraints },
            options,
            fallback
        );
    }

    /**
     * Choose a function and return arguments.
     */
    async functionCall(task, functions = [], options = {}) {
        const fallback = { name: "none", arguments: {} };
        return await this._runJsonJob(
            "function_call",
            { task, functions },
            options,
            fallback
        );
    }

    /**
     * Choose a Claude skill and return structured input.
     */
    async callSkill(task, skills = [], options = {}) {
        const fallback = { skill: "none", input: {} };
        return await this._runJsonJob(
            "claude_skill",
            { task, skills },
            options,
            fallback
        );
    }

    /**
     * Get sentiment analysis for a message.
     * @param {string} text - Message text
     * @returns {Promise<{sentiment: string, score: number}>}
     */
    async getSentiment(text, options = {}) {
        const fallback = { sentiment: "neutral", score: 0 };
        if (!this.isAnalysisAvailable()) return fallback;
        return await this._runJsonJob("sentiment", { text }, options, fallback);
    }

    /**
     * Check if a message matches smart filter criteria.
     * @param {string} text - Message text
     * @param {object} criteria - Filter criteria
     * @returns {Promise<boolean>}
     */
    async matchFilter(text, criteria, options = {}) {
        if (!this.isAnalysisAvailable()) {
            return true;
        }

        if (!criteria || Object.keys(criteria).length === 0) {
            return true;
        }

        const fallback = { matches: true, confidence: "low", reasoning: "AI not available" };
        const result = await this._runJsonJob(
            "smart_filter_match",
            { text, criteria },
            options,
            fallback
        );
        return result.matches === true;
    }

    /**
     * Summarize multiple messages into a digest.
     * @param {object[]} messages - Array of message objects
     * @returns {Promise<string>} - Digest summary
     */
    async createDigest(messages, options = {}) {
        if (!this.isAnalysisAvailable() || !messages || messages.length === 0) {
            return "No messages to summarize.";
        }

        const response = await this.runJob("digest", { messages }, options);
        return response.content || "Failed to create digest.";
    }

    /**
     * Rank items by relevance to a query.
     * @param {object[]} items - Items to rank
     * @param {string} query - User's interest query
     */
    async rankByRelevance(items, query, options = {}) {
        if (!this.isAnalysisAvailable() || !items || items.length === 0) {
            return (items || []).map((item, idx) => ({ ...item, relevance: 1 - idx * 0.1 }));
        }

        const rankings = await this._runJsonJob(
            "rank_relevance",
            { items, query },
            options,
            []
        );

        if (!Array.isArray(rankings)) {
            return items;
        }

        return items.map((item, idx) => {
            const ranking = rankings.find(r => r.index === idx + 1);
            return { ...item, relevance: ranking?.relevance || 5 };
        }).sort((a, b) => b.relevance - a.relevance);
    }

    /**
     * Check if AI analysis is available (at least one provider configured).
     */
    isAnalysisAvailable() {
        return this._getDefaultProvider() !== null;
    }

    /**
     * Check if AI is available.
     */
    isAvailable() {
        return this._getDefaultProvider() !== null;
    }

    /**
     * Get the first configured provider for analysis.
     */
    _getDefaultProvider() {
        const providers = ["groq", "gemini", "openai", "claude", "nvidia"];
        for (const key of providers) {
            const provider = getProvider(key);
            if (provider?.isConfigured?.(this.config)) {
                return key;
            }
        }
        return null;
    }

    // ============================================================
    // USER CHAT METHODS
    // ============================================================

    /**
     * Send a message and get AI response.
     * Returns { content, thinking, chatId, messageCount }
     */
    async chat(userId, message) {
        const settings = await this.getSettings(userId);
        const provider = getProvider(settings.provider);

        if (!provider || !provider.isConfigured(this.config)) {
            throw new Error(`Provider ${settings.provider} not configured`);
        }

        // Get/create active chat
        let activeChat = null;
        let history = [];
        let summaryPrefix = "";

        if (this.storage) {
            activeChat = await this.storage.getOrCreateActiveChat(userId);
            await this.storage.saveMessage(activeChat.id, "user", message);

            // Auto-title on first message
            const messageCount = await this.storage.getMessageCount(activeChat.id);
            if (messageCount === 1 && activeChat.title === "New Chat") {
                const shortTitle = message.substring(0, 40) + (message.length > 40 ? "..." : "");
                await this.storage.renameChat(activeChat.id, shortTitle);
            }

            // Build context from history
            const recentMessages = await this.storage.getChatMessages(activeChat.id, 4);
            history = recentMessages.reverse().map(m => ({
                role: m.role,
                content: m.content
            }));

            if (activeChat.summary) {
                summaryPrefix = `[Previous conversation summary: ${activeChat.summary}]`;
            }
        }

        const response = await this.runJob(
            "chat",
            { message },
            {
                provider: settings.provider,
                model: settings.model,
                history,
                contextPrefix: summaryPrefix
            }
        );

        // Save assistant message
        if (this.storage && activeChat && response.content) {
            await this.storage.saveMessage(activeChat.id, "assistant", response.content);

            // Update summary every 6 messages
            const newCount = await this.storage.getMessageCount(activeChat.id);
            if (newCount % 6 === 0) {
                this._updateSummary(activeChat.id, settings).catch(() => { });
            }
        }

        return {
            content: response.content,
            thinking: response.thinking,
            chatId: activeChat?.id,
            provider: settings.provider,
            model: settings.model
        };
    }

    /**
     * Create a new chat session.
     */
    async createChat(userId) {
        if (!this.storage) {
            return { id: null, title: "New Chat" };
        }
        return await this.storage.createNewChat(userId);
    }

    /**
     * Get user's chat sessions.
     */
    async getChats(userId, limit = 10) {
        if (!this.storage) {
            return [];
        }
        return await this.storage.getUserChats(userId, limit);
    }

    /**
     * Get a chat with its messages.
     */
    async getChat(userId, chatId, messageLimit = 50) {
        if (!this.storage) {
            return null;
        }
        const chat = await this.storage.getChatById(chatId);
        if (!chat) return null;

        const messages = await this.storage.getChatMessages(chatId, messageLimit);
        return {
            ...chat,
            messages: messages.reverse()
        };
    }

    /**
     * Switch to a chat and optionally rename it.
     */
    async switchChat(userId, chatId, newTitle = null) {
        if (!this.storage) {
            throw new Error("Storage not available");
        }
        await this.storage.setActiveChat(userId, chatId);
        if (newTitle) {
            await this.storage.renameChat(chatId, newTitle);
        }
        return await this.storage.getChatById(chatId);
    }

    /**
     * Rename a chat.
     */
    async renameChat(chatId, title) {
        if (!this.storage) {
            throw new Error("Storage not available");
        }
        await this.storage.renameChat(chatId, title);
        return { id: chatId, title };
    }

    /**
     * Clear chat messages.
     */
    async clearChat(chatId) {
        if (!this.storage) {
            throw new Error("Storage not available");
        }
        await this.storage.clearChatMessages(chatId);
        return { cleared: true };
    }

    /**
     * Export chat to markdown.
     * Returns { rawMarkdown, summaryMarkdown, urls } if GitHub is configured.
     */
    async exportChat(userId, chatId) {
        if (!this.storage) {
            throw new Error("Storage not available");
        }

        const chat = await this.storage.getChatById(chatId);
        const messages = await this.storage.getChatMessages(chatId, 100);

        if (!chat || messages.length === 0) {
            throw new Error("No messages to export");
        }

        // Generate filename
        const date = new Date();
        const mmdd = `${String(date.getMonth() + 1).padStart(2, "0")}${String(date.getDate()).padStart(2, "0")}`;
        const words = (chat.title || "chat").split(/\s+/).slice(0, 3).join("-");
        const safeWords = words.replace(/[^a-zA-Z0-9\u4e00-\u9fa5-]/g, "").substring(0, 30);
        const filename = `${mmdd}-${safeWords || "chat"}.md`;

        // Build raw content
        const rawContent = messages.reverse()
            .map(m => `**${m.role === "user" ? "User" : "Assistant"}:**\n${m.content}`)
            .join("\n\n---\n\n");

        const rawMarkdown = `# ${chat.title}\n\n> Exported: ${date.toLocaleString()} | ${messages.length} messages\n\n${rawContent}\n\n---\n*Exported from QuBot*`;

        // Generate AI Summary
        let summaryMarkdown = "";
        try {
            const settings = await this.getSettings(userId);
            const response = await this.runJob(
                "chat_notes",
                { conversation: rawContent },
                { provider: settings.provider, model: settings.model }
            );

            const summary = response.content || "Summary generation failed.";
            summaryMarkdown = `# ${chat.title} - Notes\n\n> Summary of ${messages.length} messages | ${date.toLocaleString()}\n\n${summary}\n\n---\n*AI-generated summary from QuBot*`;
        } catch (err) {
            this.logger.warn("Summary generation failed", err.message);
            summaryMarkdown = `# ${chat.title} - Notes\n\n> Summary generation failed\n\nSee raw file for full conversation.\n\n---\n*Exported from QuBot*`;
        }

        // Push to GitHub if configured
        let urls = null;
        if (this.githubService?.isReady) {
            try {
                const rawUrl = await this.githubService.saveNote(
                    `raw/${filename}`,
                    rawMarkdown,
                    `Export raw: ${chat.title} (QuBot)`
                );

                const notesUrl = await this.githubService.saveNote(
                    `notes/${filename}`,
                    summaryMarkdown,
                    `Export notes: ${chat.title} (QuBot)`
                );

                urls = { raw: rawUrl, notes: notesUrl };
            } catch (err) {
                this.logger.error("GitHub push failed", err);
            }
        }

        return {
            filename,
            rawMarkdown,
            summaryMarkdown,
            urls,
            messageCount: messages.length
        };
    }

    /**
     * Call AI with retry logic.
     */
    async _callAIWithRetry(provider, prompt, model, history, contextPrefix, retries = 1) {
        let lastError;

        for (let attempt = 0; attempt <= retries; attempt++) {
            try {
                return await callAI(provider, this.config, prompt, model, history, contextPrefix);
            } catch (err) {
                lastError = err;
                this.logger.warn(`AI call attempt ${attempt + 1} failed: ${err.message}`);
                if (attempt < retries) {
                    await this._sleep((attempt + 1) * 1000);
                }
            }
        }

        throw lastError;
    }

    /**
     * Update chat summary.
     */
    async _updateSummary(chatId, settings) {
        if (!this.storage) return;

        try {
            const messages = await this.storage.getChatMessages(chatId, 20);
            if (messages.length < 4) return;

            const messagesText = messages
                .reverse()
                .map(m => `${m.role}: ${m.content.substring(0, 200)}`)
                .join("\n");

            const response = await this.runJob(
                "chat_summary",
                { messagesText },
                { provider: settings.provider, model: settings.model }
            );

            if (response.content) {
                await this.storage.updateChatSummary(chatId, response.content);
            }
        } catch (err) {
            this.logger.warn("Failed to update summary", err.message);
        }
    }

    _sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
}

module.exports = AiService;
