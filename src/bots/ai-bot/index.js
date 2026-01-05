const BotInstance = require("../../core/BotInstance");
const { getProvider, listProviders } = require("../../providers");
const { sendLongHtmlMessage, markdownToHtml, escapeHtml } = require("../../core/TelegramUtils");

/**
 * AiBot - Telegram interface for AI chat.
 * Delegates all business logic to AiService.
 * Handles only Telegram-specific formatting and interactions.
 */
class AiBot extends BotInstance {
    constructor(token, config, storage, githubService, allowedUsers, aiService = null) {
        super("ai-bot", token, allowedUsers);
        this.config = config;
        this.storage = storage;
        this.githubService = githubService;
        this.aiService = aiService;
    }

    /**
     * Set the AI service (allows injection after construction).
     */
    setService(aiService) {
        this.aiService = aiService;
    }

    async setup() {
        if (!this.isEnabled()) {
            this.logger.warn("AI Bot token not configured.");
            return;
        }

        // Register commands
        this.command("start", "Welcome and quick actions", (ctx) => this._handleStart(ctx));
        this.command("ai", "Ask AI a question", (ctx) => this._handleAi(ctx));
        this.command("new", "Start new chat", (ctx) => this._handleNew(ctx));
        this.command("chats", "List/switch chats", (ctx) => this._handleChats(ctx));
        this.command("rename", "Rename current chat", (ctx) => this._handleRename(ctx));
        this.command("clear", "Clear chat history", (ctx) => this._handleClear(ctx));
        this.command("export", "Export chat to markdown", (ctx) => this._handleExport(ctx));
        this.command("providers", "Select AI provider", (ctx) => this._handleProviders(ctx));
        this.command("models", "Select model", (ctx) => this._handleModels(ctx));
        this.command("status", "Check bot status", (ctx) => this._handleStatus(ctx));
        this.command("help", "Show help", (ctx) => this._handleHelp(ctx));

        // Callback actions
        this.action(/^provider:(.+)$/, (ctx) => this._handleProviderSelect(ctx));
        this.action(/^model:(.+)$/, (ctx) => this._handleModelSelect(ctx));
        this.action(/^chat:(\d+)$/, (ctx) => this._handleChatSelect(ctx));
        this.action("cmd_new", (ctx) => this._handleNew(ctx));
        this.action("cmd_chats", (ctx) => this._handleChats(ctx));
        this.action("cmd_providers", (ctx) => this._handleProviders(ctx));
        this.action("cmd_export", (ctx) => this._handleExport(ctx));
        this.action("cmd_tryai", (ctx) => ctx.reply("💬 Just send me any message to start chatting!"));

        // Plain text handler
        this.onText((ctx) => this._handleText(ctx));

        this.logger.info("AiBot commands registered.");
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
        if (!this.aiService) {
            return ctx.reply("❌ AI service not available.");
        }

        const settings = await this.aiService.getSettings(userId);
        const provider = getProvider(settings.provider);

        if (!provider || !provider.isConfigured(this.config)) {
            return ctx.reply(
                `❌ ${provider?.name || settings.provider} API Key not configured.\n\n` +
                `Use /providers to switch to a configured provider.`
            );
        }

        await ctx.sendChatAction("typing");

        const statusMsg = await ctx.reply(
            `🤔 Thinking...\n\n📡 ${provider.name}: ${settings.model}`
        );

        const typingInterval = setInterval(() => {
            ctx.sendChatAction("typing").catch(() => { });
        }, 4000);

        try {
            // Call AI service
            const response = await this.aiService.chat(userId, prompt);

            clearInterval(typingInterval);

            // Update status
            await ctx.telegram.editMessageText(
                ctx.chat.id,
                statusMsg.message_id,
                null,
                "✅ Done!"
            );

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

    async _handleNew(ctx) {
        const userId = ctx.from?.id;

        try {
            const chat = await this.aiService.createChat(userId);
            await ctx.reply(`✨ Started new chat${chat.id ? ` (ID: ${chat.id})` : ""}\n\nSend any message to begin.`);
        } catch (err) {
            await ctx.reply("✨ New chat started.\n\n(Note: Chat history not available without database)");
        }

        if (ctx.callbackQuery) {
            await ctx.answerCbQuery("New chat started");
        }
    }

    async _handleChats(ctx) {
        const userId = ctx.from?.id;

        try {
            const chats = await this.aiService.getChats(userId, 10);

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
        } catch (err) {
            await ctx.reply("❌ Chat history not available (no database).");
        }

        if (ctx.callbackQuery) {
            await ctx.answerCbQuery();
        }
    }

    async _handleChatSelect(ctx) {
        const userId = ctx.from?.id;
        const chatId = parseInt(ctx.match[1], 10);

        try {
            const chat = await this.aiService.switchChat(userId, chatId);
            await ctx.answerCbQuery(`Switched to: ${chat?.title || "Chat"}`);
            await ctx.editMessageText(`✅ Switched to: <b>${escapeHtml(chat?.title || "Chat")}</b>`, { parse_mode: "HTML" });

            // Display recent chat history
            const fullChat = await this.aiService.getChat(userId, chatId, 10);
            if (fullChat?.messages?.length > 0) {
                const historyLines = fullChat.messages.map((m) => {
                    const icon = m.role === "user" ? "👤" : "🤖";
                    const content = m.content.length > 150
                        ? m.content.substring(0, 150) + "..."
                        : m.content;
                    return `${icon} <b>${m.role === "user" ? "You" : "AI"}:</b>\n${escapeHtml(content)}`;
                });

                const historyHtml = `📜 <b>Recent History (${fullChat.messages.length} messages):</b>\n\n${historyLines.join("\n\n───────────\n\n")}`;
                await sendLongHtmlMessage(ctx, historyHtml);
            } else {
                await ctx.reply("📭 This chat has no messages yet. Send a message to start.");
            }
        } catch (err) {
            await ctx.answerCbQuery("Error switching chat");
        }
    }

    async _handleRename(ctx) {
        const userId = ctx.from?.id;
        const newTitle = (ctx.message.text || "").replace(/^\/rename\s*/i, "").trim();

        if (!newTitle) {
            return ctx.reply("📌 Usage: /rename <new title>\nExample: /rename Project Discussion");
        }

        try {
            const chats = await this.aiService.getChats(userId, 1);
            if (chats.length === 0) {
                return ctx.reply("❌ No active chat to rename.");
            }
            const activeChat = chats.find(c => c.is_active) || chats[0];
            await this.aiService.renameChat(activeChat.id, newTitle);
            await ctx.reply(`✅ Chat renamed to: <b>${escapeHtml(newTitle)}</b>`, { parse_mode: "HTML" });
        } catch (err) {
            await ctx.reply("❌ Chat history not available.");
        }
    }

    async _handleClear(ctx) {
        const userId = ctx.from?.id;

        try {
            const chats = await this.aiService.getChats(userId, 1);
            if (chats.length === 0) {
                return ctx.reply("❌ No active chat to clear.");
            }
            const activeChat = chats.find(c => c.is_active) || chats[0];
            await this.aiService.clearChat(activeChat.id);
            await ctx.reply("🗑️ Chat history cleared.");
        } catch (err) {
            await ctx.reply("❌ Chat history not available.");
        }
    }

    async _handleExport(ctx) {
        const userId = ctx.from?.id;

        try {
            const chats = await this.aiService.getChats(userId, 1);
            if (chats.length === 0) {
                return ctx.reply("❌ No active chat to export.");
            }
            const activeChat = chats.find(c => c.is_active) || chats[0];

            await ctx.reply("📝 Exporting chat...");

            const result = await this.aiService.exportChat(userId, activeChat.id);

            if (result.urls) {
                await sendLongHtmlMessage(ctx,
                    `✅ <b>Chat exported!</b>\n\n` +
                    `📄 <a href="${result.urls.raw}">Raw Conversation</a>\n` +
                    `📝 <a href="${result.urls.notes}">AI Notes</a>`
                );
            } else {
                // Fallback: send as file
                await ctx.replyWithDocument({
                    source: Buffer.from(result.rawMarkdown, "utf-8"),
                    filename: result.filename,
                });
                await ctx.reply("ℹ️ GitHub export not configured. Set NOTES_REPO to enable.");
            }
        } catch (err) {
            await ctx.reply(`❌ Export failed: ${err.message}`);
        }

        if (ctx.callbackQuery) {
            await ctx.answerCbQuery();
        }
    }

    async _handleProviders(ctx) {
        const userId = ctx.from?.id;
        const settings = await this.aiService.getSettings(userId);
        const providers = this.aiService.listProviders();

        const buttons = providers.map((p) => [{
            text: `${p.key === settings.provider ? "✅ " : ""}${p.name}${p.configured ? "" : " ⚠️"}`,
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

        await this.aiService.updateSettings(userId, providerKey, provider.defaultModel);

        await ctx.answerCbQuery(`Switched to ${provider.name}`);
        await ctx.editMessageText(
            `✅ Selected: <b>${provider.name}</b>\n\n📝 Default model: <code>${provider.defaultModel}</code>\n\nUse /models to switch models`,
            { parse_mode: "HTML" }
        );
    }

    async _handleModels(ctx) {
        const userId = ctx.from?.id;
        const settings = await this.aiService.getSettings(userId);
        const provider = getProvider(settings.provider);

        await ctx.reply("⏳ Fetching model list...");

        const models = await this.aiService.getModels(settings.provider);

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
        const settings = await this.aiService.getSettings(userId);

        await this.aiService.updateSettings(userId, settings.provider, modelId);

        await ctx.answerCbQuery("Model switched");
        await ctx.editMessageText(`✅ Selected model: <code>${escapeHtml(modelId)}</code>`, { parse_mode: "HTML" });
    }

    async _handleStart(ctx) {
        const userId = ctx.from?.id;
        const settings = await this.aiService.getSettings(userId);
        const provider = getProvider(settings.provider);

        const buttons = [
            [{ text: "🧠 Try AI", callback_data: "cmd_tryai" }, { text: "📂 My Chats", callback_data: "cmd_chats" }],
            [{ text: "🔌 Providers", callback_data: "cmd_providers" }, { text: "📝 Export", callback_data: "cmd_export" }],
        ];

        await ctx.reply(
            `🧠 <b>Welcome to AI Bot!</b>\n\n` +
            `Chat with AI powered by multiple providers.\n\n` +
            `<b>Current:</b> ${provider?.name || settings.provider} / <code>${settings.model}</code>\n\n` +
            `<i>Just send me a message to start chatting!</i>`,
            { parse_mode: "HTML", reply_markup: { inline_keyboard: buttons } }
        );
    }

    async _handleStatus(ctx) {
        const userId = ctx.from?.id;
        const settings = await this.aiService.getSettings(userId);
        const provider = getProvider(settings.provider);

        const dbStatus = this.storage ? "✅ Connected" : "❌ Unavailable";
        const githubStatus = this.githubService?.isReady ? "✅ Ready" : "⚠️ Not configured";

        let chatCount = 0;
        try {
            const chats = await this.aiService.getChats(userId, 100);
            chatCount = chats.length;
        } catch (err) {
            // Ignore
        }

        // Check which providers are configured
        const configuredProviders = this.aiService.listProviders()
            .filter(p => p.configured)
            .map(p => p.name);

        await ctx.reply(
            `📊 <b>AI Bot Status</b>\n\n` +
            `<b>Database:</b> ${dbStatus}\n` +
            `<b>GitHub Export:</b> ${githubStatus}\n` +
            `<b>Your Chats:</b> ${chatCount}\n\n` +
            `<b>Current Provider:</b> ${provider?.name || settings.provider}\n` +
            `<b>Model:</b> <code>${settings.model}</code>\n\n` +
            `<b>Available Providers:</b>\n${configuredProviders.length > 0 ? configuredProviders.join(", ") : "None configured"}`,
            { parse_mode: "HTML" }
        );
    }

    async _handleHelp(ctx) {
        const helpText = `
<b>🧠 AI Bot Help</b>

<b>Getting Started:</b>
/start - Welcome & quick actions
/status - Check bot status

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

<i>Tip: In private chat, just send messages directly!</i>
        `.trim();

        await ctx.reply(helpText, { parse_mode: "HTML" });
    }
}

module.exports = AiBot;
