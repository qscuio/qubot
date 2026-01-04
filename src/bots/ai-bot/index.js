const BotInstance = require("../../core/BotInstance");
const { getProvider, listProviders, fetchModels, callAI } = require("../../providers");
const { sendLongHtmlMessage, markdownToHtml, escapeHtml, sleep } = require("../../core/TelegramUtils");

const DEFAULT_PROVIDER = "groq";

/**
 * AiBot - Full-featured AI chat bot like ChatGPT.
 * Features: Chat history, multiple providers, long messages, GitHub export.
 */
class AiBot extends BotInstance {
    constructor(token, config, storage, githubService) {
        super("ai-bot", token);
        this.config = config;
        this.storage = storage;
        this.githubService = githubService;
        this.cachedModels = new Map();
    }

    async setup() {
        if (!this.isEnabled()) {
            this.logger.warn("AI Bot token not configured.");
            return;
        }

        // Register commands
        this.command("ai", "Ask AI a question", (ctx) => this._handleAi(ctx));
        this.command("new", "Start new chat", (ctx) => this._handleNew(ctx));
        this.command("chats", "List/switch chats", (ctx) => this._handleChats(ctx));
        this.command("rename", "Rename current chat", (ctx) => this._handleRename(ctx));
        this.command("clear", "Clear chat history", (ctx) => this._handleClear(ctx));
        this.command("export", "Export chat to markdown", (ctx) => this._handleExport(ctx));
        this.command("providers", "Select AI provider", (ctx) => this._handleProviders(ctx));
        this.command("models", "Select model", (ctx) => this._handleModels(ctx));
        this.command("help", "Show help", (ctx) => this._handleHelp(ctx));

        // Callback actions
        this.action(/^provider:(.+)$/, (ctx) => this._handleProviderSelect(ctx));
        this.action(/^model:(.+)$/, (ctx) => this._handleModelSelect(ctx));
        this.action(/^chat:(\d+)$/, (ctx) => this._handleChatSelect(ctx));
        this.action("cmd_new", (ctx) => this._handleNew(ctx));
        this.action("cmd_chats", (ctx) => this._handleChats(ctx));
        this.action("cmd_providers", (ctx) => this._handleProviders(ctx));
        this.action("cmd_export", (ctx) => this._handleExport(ctx));

        // Plain text handler
        this.onText((ctx) => this._handleText(ctx));

        this.logger.info("AiBot commands registered: /ai, /new, /chats, /providers, /models, /export");
    }

    async _getSettings(userId) {
        if (!this.storage) {
            return { provider: DEFAULT_PROVIDER, model: getProvider(DEFAULT_PROVIDER)?.defaultModel || "" };
        }
        const settings = await this.storage.getAiSettings(userId);
        return { provider: settings.provider, model: settings.model };
    }

    async _updateSettings(userId, provider, model) {
        if (this.storage) {
            await this.storage.updateAiSettings(userId, provider, model);
        }
    }

    async _handleAi(ctx) {
        const userId = ctx.from?.id;
        const prompt = (ctx.message.text || "").replace(/^\/ai\s*/i, "").trim();

        if (!prompt) {
            return ctx.reply("📌 Usage: /ai <question>\nExample: /ai What is quantum computing?");
        }

        await this._processAI(ctx, userId, prompt);
    }

    async _handleText(ctx) {
        const text = ctx.message.text || "";
        if (text.startsWith("/")) return;

        // In private chat, always respond
        // In groups, only respond to replies or mentions
        if (ctx.chat.type !== "private") {
            const botMentioned = text.includes("@" + ctx.botInfo?.username);
            const isReply = ctx.message.reply_to_message?.from?.id === ctx.botInfo?.id;
            if (!botMentioned && !isReply) return;
        }

        const userId = ctx.from?.id;
        await this._processAI(ctx, userId, text);
    }

    async _processAI(ctx, userId, prompt) {
        const settings = await this._getSettings(userId);
        const provider = getProvider(settings.provider);

        if (!provider || !provider.isConfigured(this.config)) {
            return ctx.reply(
                `❌ ${provider?.name || settings.provider} API Key not configured.\n\n` +
                `Use /providers to switch to a configured provider.`
            );
        }

        // Get/create active chat
        let activeChat = null;
        if (this.storage) {
            activeChat = await this.storage.getOrCreateActiveChat(userId);

            // Save user message
            await this.storage.saveMessage(activeChat.id, "user", prompt);

            // Auto-title on first message
            const messageCount = await this.storage.getMessageCount(activeChat.id);
            if (messageCount === 1 && activeChat.title === "New Chat") {
                const shortTitle = prompt.substring(0, 40) + (prompt.length > 40 ? "..." : "");
                await this.storage.renameChat(activeChat.id, shortTitle);
            }
        }

        await ctx.sendChatAction("typing");

        const statusMsg = await ctx.reply(
            `🤔 Thinking...\n\n📡 ${provider.name}: ${settings.model}`
        );

        const typingInterval = setInterval(() => {
            ctx.sendChatAction("typing").catch(() => { });
        }, 4000);

        try {
            // Build context from history
            let history = [];
            let contextPrefix = "";

            if (this.storage && activeChat) {
                const recentMessages = await this.storage.getChatMessages(activeChat.id, 4);
                history = recentMessages.reverse().map((m) => ({
                    role: m.role,
                    content: m.content,
                }));

                if (activeChat.summary) {
                    contextPrefix = `[Previous conversation summary: ${activeChat.summary}]\n\n`;
                }
            }

            const response = await callAI(
                settings.provider,
                this.config,
                prompt,
                settings.model,
                history,
                contextPrefix
            );

            clearInterval(typingInterval);

            // Update status
            await ctx.telegram.editMessageText(
                ctx.chat.id,
                statusMsg.message_id,
                null,
                "✅ Done!"
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

            // Send thinking process
            if (response.thinking) {
                const thinkingHtml = `<b>💭 Thinking:</b>\n<i>${escapeHtml(response.thinking.substring(0, 1000))}${response.thinking.length > 1000 ? "..." : ""}</i>`;
                await sendLongHtmlMessage(ctx, thinkingHtml);
            }

            // Send response
            if (response.content) {
                const responseHtml = `<b>💬 ${provider.name}:</b>\n${markdownToHtml(response.content)}`;
                await sendLongHtmlMessage(ctx, responseHtml);
            } else {
                await ctx.reply("⚠️ AI returned no response. Try a different model.");
            }

            // Quick action buttons
            const buttons = [
                [{ text: "✨ New", callback_data: "cmd_new" }, { text: "📂 Chats", callback_data: "cmd_chats" }],
                [{ text: "🔌 Provider", callback_data: "cmd_providers" }, { text: "📝 Export", callback_data: "cmd_export" }],
            ];
            await ctx.reply("<i>Quick actions:</i>", {
                parse_mode: "HTML",
                reply_markup: { inline_keyboard: buttons },
            });
        } catch (err) {
            clearInterval(typingInterval);
            this.logger.error("AI request failed", err);

            const errorMsg = err.name === "AbortError"
                ? "⏱️ Request timed out. Try again or switch to a faster model."
                : `❌ Error: ${err.message}\n\nUse /providers to switch providers.`;

            await ctx.reply(errorMsg);
        }
    }

    async _updateSummary(chatId, settings) {
        if (!this.storage) return;

        try {
            const messages = await this.storage.getChatMessages(chatId, 20);
            if (messages.length < 4) return;

            const messagesText = messages
                .reverse()
                .map((m) => `${m.role}: ${m.content.substring(0, 200)}`)
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

    async _handleNew(ctx) {
        const userId = ctx.from?.id;

        if (this.storage) {
            const chat = await this.storage.createNewChat(userId);
            await ctx.reply(`✨ Started new chat (ID: ${chat.id})\n\nSend any message to begin.`);
        } else {
            await ctx.reply("✨ New chat started.\n\n(Note: Chat history not available without database)");
        }

        if (ctx.callbackQuery) {
            await ctx.answerCbQuery("New chat started");
        }
    }

    async _handleChats(ctx) {
        const userId = ctx.from?.id;

        if (!this.storage) {
            return ctx.reply("❌ Chat history not available (no database).");
        }

        const chats = await this.storage.getUserChats(userId, 10);

        if (chats.length === 0) {
            return ctx.reply("📭 No chats yet. Use /ai to start one.");
        }

        const buttons = chats.map((c) => [{
            text: `${c.is_active ? "✅ " : ""}${c.title.substring(0, 30)}`,
            callback_data: `chat:${c.id}`,
        }]);

        await ctx.reply("📂 Your chats:", {
            reply_markup: { inline_keyboard: buttons },
        });

        if (ctx.callbackQuery) {
            await ctx.answerCbQuery();
        }
    }

    async _handleChatSelect(ctx) {
        const userId = ctx.from?.id;
        const chatId = parseInt(ctx.match[1], 10);

        if (this.storage) {
            await this.storage.setActiveChat(userId, chatId);
            const chat = await this.storage.getChatById(chatId);
            await ctx.answerCbQuery(`Switched to: ${chat?.title || "Chat"}`);
            await ctx.editMessageText(`✅ Switched to: <b>${escapeHtml(chat?.title || "Chat")}</b>`, { parse_mode: "HTML" });
        }
    }

    async _handleRename(ctx) {
        const userId = ctx.from?.id;
        const newTitle = (ctx.message.text || "").replace(/^\/rename\s*/i, "").trim();

        if (!newTitle) {
            return ctx.reply("📌 Usage: /rename <new title>\nExample: /rename Project Discussion");
        }

        if (!this.storage) {
            return ctx.reply("❌ Chat history not available.");
        }

        const chat = await this.storage.getOrCreateActiveChat(userId);
        await this.storage.renameChat(chat.id, newTitle);
        await ctx.reply(`✅ Chat renamed to: <b>${escapeHtml(newTitle)}</b>`, { parse_mode: "HTML" });
    }

    async _handleClear(ctx) {
        const userId = ctx.from?.id;

        if (!this.storage) {
            return ctx.reply("❌ Chat history not available.");
        }

        const chat = await this.storage.getOrCreateActiveChat(userId);
        await this.storage.clearChatMessages(chat.id);
        await ctx.reply("🗑️ Chat history cleared.");
    }

    async _handleExport(ctx) {
        const userId = ctx.from?.id;

        if (!this.storage) {
            return ctx.reply("❌ Chat history not available.");
        }

        const chat = await this.storage.getOrCreateActiveChat(userId);
        const messages = await this.storage.getChatMessages(chat.id, 100);

        if (messages.length === 0) {
            return ctx.reply("📭 No messages to export.");
        }

        await ctx.reply("📝 Exporting chat...");

        // Generate filename
        const date = new Date();
        const mmdd = `${String(date.getMonth() + 1).padStart(2, "0")}${String(date.getDate()).padStart(2, "0")}`;
        const words = (chat.title || "chat").split(/\s+/).slice(0, 3).join("-");
        const safeWords = words.replace(/[^a-zA-Z0-9\u4e00-\u9fa5-]/g, "").substring(0, 30);
        const filename = `${mmdd}-${safeWords || "chat"}.md`;

        // Build raw content
        const rawContent = messages.reverse()
            .map((m) => `**${m.role === "user" ? "User" : "Assistant"}:**\n${m.content}`)
            .join("\n\n---\n\n");

        const rawMarkdown = `# ${chat.title}\n\n> Exported: ${date.toLocaleString()} | ${messages.length} messages\n\n${rawContent}\n\n---\n*Exported from QuBot*`;

        // Generate AI Summary
        let summaryMarkdown = "";
        try {
            await ctx.reply("🧠 Generating summary...");
            const settings = await this._getSettings(userId);
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
            this.logger.error("Summary generation failed", err);
            summaryMarkdown = `# ${chat.title} - Notes\n\n> Summary generation failed\n\nSee raw file for full conversation.\n\n---\n*Exported from QuBot*`;
        }

        // Send raw file as document
        await ctx.replyWithDocument({
            source: Buffer.from(rawMarkdown, "utf-8"),
            filename: `raw-${filename}`,
        });

        // Push to GitHub
        if (this.githubService && this.githubService.isReady) {
            try {
                await ctx.reply("⏳ Pushing to GitHub...");

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

                await sendLongHtmlMessage(ctx, `✅ <b>Chat exported!</b>\n\n📄 <a href="${rawUrl}">Raw Conversation</a>\n📝 <a href="${notesUrl}">AI Notes</a>`);
            } catch (err) {
                this.logger.error("GitHub push failed", err);
                await ctx.reply(`❌ GitHub push failed: ${err.message}`);
            }
        } else if (this.config.get("NOTES_REPO")) {
            await ctx.reply("⚠️ GitHub export configured but service not ready. Check logs.");
        } else {
            await ctx.reply("ℹ️ GitHub export not configured. Set NOTES_REPO to enable.");
        }
    }

    async _handleProviders(ctx) {
        const userId = ctx.from?.id;
        const settings = await this._getSettings(userId);

        const buttons = listProviders().map((p) => [{
            text: `${p.key === settings.provider ? "✅ " : ""}${p.name}`,
            callback_data: `provider:${p.key}`,
        }]);

        await ctx.reply("🔌 Select AI Provider:", {
            reply_markup: { inline_keyboard: buttons },
        });

        if (ctx.callbackQuery) {
            await ctx.answerCbQuery();
        }
    }

    async _handleProviderSelect(ctx) {
        const userId = ctx.from?.id;
        const providerKey = ctx.match[1];
        const provider = getProvider(providerKey);

        if (!provider) {
            return ctx.answerCbQuery("❌ Unknown provider");
        }

        await this._updateSettings(userId, providerKey, provider.defaultModel);

        await ctx.answerCbQuery(`Switched to ${provider.name}`);
        await ctx.editMessageText(
            `✅ Selected: <b>${provider.name}</b>\n\n📝 Default model: <code>${provider.defaultModel}</code>\n\nUse /models to switch models`,
            { parse_mode: "HTML" }
        );
    }

    async _handleModels(ctx) {
        const userId = ctx.from?.id;
        const settings = await this._getSettings(userId);
        const provider = getProvider(settings.provider);

        await ctx.reply("⏳ Fetching model list...");

        let models;
        if (this.cachedModels.has(settings.provider)) {
            models = this.cachedModels.get(settings.provider);
        } else {
            models = await fetchModels(settings.provider, this.config);
            this.cachedModels.set(settings.provider, models);
        }

        if (models.length === 0) {
            return ctx.reply("❌ No models available for this provider");
        }

        const displayModels = models.slice(0, 10);
        const buttons = displayModels.map((m) => [{
            text: `${m.id === settings.model ? "✅ " : ""}${m.name}`,
            callback_data: `model:${m.id}`,
        }]);

        await ctx.reply(`📝 Select model (${provider?.name}):`, {
            reply_markup: { inline_keyboard: buttons },
        });
    }

    async _handleModelSelect(ctx) {
        const userId = ctx.from?.id;
        const modelId = ctx.match[1];
        const settings = await this._getSettings(userId);

        await this._updateSettings(userId, settings.provider, modelId);

        await ctx.answerCbQuery("Model switched");
        await ctx.editMessageText(`✅ Selected model: <code>${escapeHtml(modelId)}</code>`, { parse_mode: "HTML" });
    }

    async _handleHelp(ctx) {
        const helpText = `
<b>🧠 AI Bot Help</b>

<b>Chat Commands:</b>
/ai &lt;question&gt; - Ask AI a question
/new - Start new chat
/chats - List/switch chats
/rename &lt;title&gt; - Rename chat
/clear - Clear history
/export - Export to markdown

<b>Settings:</b>
/providers - Select AI provider
/models - Select model

<b>Supported Providers:</b>
• Groq (default)
• Google Gemini
• OpenAI (GPT-4)
• Anthropic Claude
• NVIDIA NIM

<i>Tip: In private chat, just send messages directly without /ai</i>
        `.trim();

        await ctx.reply(helpText, { parse_mode: "HTML" });
    }
}

module.exports = AiBot;
