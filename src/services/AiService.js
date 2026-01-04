const Logger = require("../core/Logger");
const { getProvider, listProviders, fetchModels, callAI } = require("../providers");

const DEFAULT_PROVIDER = "groq";

/**
 * AiService - Business logic for AI chat functionality.
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
        if (this.storage) {
            await this.storage.updateAiSettings(userId, provider, model);
        }
        return { provider, model };
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
        let contextPrefix = "";

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
                contextPrefix = `[Previous conversation summary: ${activeChat.summary}]\n\n`;
            }
        }

        // Call AI
        const response = await this._callAIWithRetry(
            settings.provider,
            message,
            settings.model,
            history,
            contextPrefix
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
            const summaryPrompt = `Analyze this conversation and create a structured knowledge summary.
Extract key points, insights, code examples, and actionable information.
Use headers (##), bullet points, and code blocks.
Be concise but comprehensive.

Conversation:
${rawContent.substring(0, 15000)}`;

            const response = await callAI(
                settings.provider,
                this.config,
                summaryPrompt,
                settings.model,
                [],
                ""
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

            const summaryPrompt = `Summarize this conversation in 2-3 sentences:\n\n${messagesText}`;

            const response = await callAI(
                settings.provider,
                this.config,
                summaryPrompt,
                settings.model,
                [],
                ""
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
