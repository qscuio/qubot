const BotInstance = require("../../core/BotInstance");
const { DEFAULT_PROVIDER, getProvider, listProviders, fetchModels, callAI } = require("../../providers");

/**
 * AiBot - Multi-provider AI chat bot.
 * Supports: Groq, Gemini, OpenAI, Claude, NVIDIA
 */
class AiBot extends BotInstance {
    constructor(token, config) {
        super("ai-bot", token);
        this.config = config;

        // User settings: { [userId]: { provider, model } }
        this.userSettings = new Map();
        // Cached models: { [provider]: models[] }
        this.cachedModels = new Map();
    }

    async setup() {
        if (!this.isEnabled()) {
            this.logger.warn("AI Bot token not configured.");
            return;
        }

        // Register commands
        this.command("ai", "Ask AI a question", (ctx) => this._handleAi(ctx));
        this.command("providers", "Select AI provider", (ctx) => this._handleProviders(ctx));
        this.command("models", "Select model", (ctx) => this._handleModels(ctx));
        this.command("help", "Show help", (ctx) => this._handleHelp(ctx));

        // Handle callback queries
        this.action(/^provider:(.+)$/, (ctx) => this._handleProviderSelect(ctx));
        this.action(/^model:(.+)$/, (ctx) => this._handleModelSelect(ctx));

        // Handle plain text messages
        this.onText((ctx) => this._handleText(ctx));

        this.logger.info("AiBot commands registered: /ai, /providers, /models");
    }

    _getSettings(userId) {
        if (!this.userSettings.has(userId)) {
            this.userSettings.set(userId, {
                provider: DEFAULT_PROVIDER,
                model: getProvider(DEFAULT_PROVIDER)?.defaultModel || "",
            });
        }
        return this.userSettings.get(userId);
    }

    async _handleAi(ctx) {
        const userId = ctx.from?.id;
        const prompt = (ctx.message.text || "").replace("/ai", "").trim();

        if (!prompt) {
            return ctx.reply("📌 Usage: /ai <question>\nExample: /ai What is quantum computing?");
        }

        await this._processAI(ctx, userId, prompt);
    }

    async _handleText(ctx) {
        const text = ctx.message.text || "";
        if (text.startsWith("/")) return;

        // In group chats, require bot mention or reply
        if (ctx.chat.type !== "private") {
            const botMentioned = text.includes("@" + ctx.botInfo?.username);
            const isReply = ctx.message.reply_to_message?.from?.id === ctx.botInfo?.id;
            if (!botMentioned && !isReply) return;
        }

        const userId = ctx.from?.id;
        await this._processAI(ctx, userId, text);
    }

    async _processAI(ctx, userId, prompt) {
        const settings = this._getSettings(userId);
        const provider = getProvider(settings.provider);

        if (!provider.isConfigured(this.config)) {
            return ctx.reply(
                `❌ ${provider.name} API Key not configured.\n\n` +
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
            const response = await callAI(
                settings.provider,
                this.config,
                prompt,
                settings.model,
                [],
                ""
            );

            clearInterval(typingInterval);

            await ctx.telegram.editMessageText(
                ctx.chat.id,
                statusMsg.message_id,
                null,
                `✅ Done!`
            );

            if (response.thinking) {
                const thinking = response.thinking.substring(0, 800);
                await ctx.reply(
                    `💭 *Reasoning:*\n\n_${this._escapeMarkdown(thinking)}${response.thinking.length > 800 ? "..." : ""}_`,
                    { parse_mode: "Markdown" }
                );
            }

            if (response.content) {
                await this._sendLongMessage(ctx, `💬 *${provider.name}:*\n\n${response.content}`);
            } else {
                await ctx.reply("⚠️ AI returned no response. Try a different model.");
            }
        } catch (err) {
            clearInterval(typingInterval);
            this.logger.error("AI request failed", err);
            await ctx.reply(`❌ Request failed: ${err.message}\n\nUse /providers to switch providers.`);
        }
    }

    async _handleProviders(ctx) {
        const userId = ctx.from?.id;
        const settings = this._getSettings(userId);

        const buttons = listProviders().map((p) => [{
            text: `${p.key === settings.provider ? "✅ " : ""}${p.name}`,
            callback_data: `provider:${p.key}`,
        }]);

        await ctx.reply("🔌 Select AI Provider:", {
            reply_markup: { inline_keyboard: buttons },
        });
    }

    async _handleProviderSelect(ctx) {
        const userId = ctx.from?.id;
        const providerKey = ctx.match[1];
        const provider = getProvider(providerKey);

        if (!provider) {
            return ctx.answerCbQuery("❌ Unknown provider");
        }

        const settings = this._getSettings(userId);
        settings.provider = providerKey;
        settings.model = provider.defaultModel;

        await ctx.answerCbQuery(`✅ Switched to ${provider.name}`);
        await ctx.editMessageText(
            `✅ Selected: *${provider.name}*\n\n📝 Default model: \`${provider.defaultModel}\`\n\nUse /models to switch models`,
            { parse_mode: "Markdown" }
        );
    }

    async _handleModels(ctx) {
        const userId = ctx.from?.id;
        const settings = this._getSettings(userId);
        const provider = getProvider(settings.provider);

        await ctx.reply("⏳ Fetching model list...");

        // Fetch models (with caching)
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

        // Limit to 10 models for UI
        const displayModels = models.slice(0, 10);

        const buttons = displayModels.map((m) => [{
            text: `${m.id === settings.model ? "✅ " : ""}${m.name}`,
            callback_data: `model:${m.id}`,
        }]);

        await ctx.reply(`📝 Select model (${provider.name}):`, {
            reply_markup: { inline_keyboard: buttons },
        });
    }

    async _handleModelSelect(ctx) {
        const userId = ctx.from?.id;
        const modelId = ctx.match[1];
        const settings = this._getSettings(userId);

        settings.model = modelId;

        await ctx.answerCbQuery(`✅ Model switched`);
        await ctx.editMessageText(`✅ Selected model: \`${modelId}\``, { parse_mode: "Markdown" });
    }

    async _handleHelp(ctx) {
        await ctx.reply(
            "🧠 *AI Bot Help*\n\n" +
            "/ai <question> - Ask AI a question\n" +
            "/providers - Select AI provider\n" +
            "/models - Select model\n\n" +
            "*Supported providers:*\n" +
            "- Groq (default)\n" +
            "- Google Gemini\n" +
            "- OpenAI (GPT-4)\n" +
            "- Anthropic Claude\n" +
            "- NVIDIA NIM",
            { parse_mode: "Markdown" }
        );
    }

    async _sendLongMessage(ctx, text, maxLength = 4000) {
        if (text.length <= maxLength) {
            return ctx.reply(text, { parse_mode: "Markdown" });
        }

        const chunks = [];
        let current = "";

        for (const line of text.split("\n")) {
            if (current.length + line.length > maxLength) {
                if (current) chunks.push(current);
                current = line;
            } else {
                current += (current ? "\n" : "") + line;
            }
        }
        if (current) chunks.push(current);

        for (const chunk of chunks) {
            await ctx.reply(chunk, { parse_mode: "Markdown" });
        }
    }

    _escapeMarkdown(text) {
        if (!text) return "";
        return text.replace(/[_*[\]()~`>#+=|{}.!-]/g, "\\$&");
    }
}

module.exports = AiBot;
