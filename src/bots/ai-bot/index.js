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
        this.command("ai", "AI 对话", (ctx) => this._handleAi(ctx));
        this.command("providers", "选择 AI 提供商", (ctx) => this._handleProviders(ctx));
        this.command("models", "选择模型", (ctx) => this._handleModels(ctx));
        this.command("help", "帮助", (ctx) => this._handleHelp(ctx));

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
            return ctx.reply("📌 用法: /ai <问题>\n例如: /ai 什么是量子计算?");
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
                `❌ ${provider.name} API Key 未配置。\n\n` +
                `使用 /providers 切换到已配置的提供商。`
            );
        }

        await ctx.sendChatAction("typing");

        const statusMsg = await ctx.reply(
            `🤔 思考中...\n\n📡 ${provider.name}: ${settings.model}`
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
                `✅ 完成!`
            );

            if (response.thinking) {
                const thinking = response.thinking.substring(0, 800);
                await ctx.reply(
                    `💭 *推理过程:*\n\n_${this._escapeMarkdown(thinking)}${response.thinking.length > 800 ? "..." : ""}_`,
                    { parse_mode: "Markdown" }
                );
            }

            if (response.content) {
                await this._sendLongMessage(ctx, `💬 *${provider.name}:*\n\n${response.content}`);
            } else {
                await ctx.reply("⚠️ AI 没有返回响应，请尝试其他模型。");
            }
        } catch (err) {
            clearInterval(typingInterval);
            this.logger.error("AI request failed", err);
            await ctx.reply(`❌ 请求失败: ${err.message}\n\n使用 /providers 切换提供商。`);
        }
    }

    async _handleProviders(ctx) {
        const userId = ctx.from?.id;
        const settings = this._getSettings(userId);

        const buttons = listProviders().map((p) => [{
            text: `${p.key === settings.provider ? "✅ " : ""}${p.name}`,
            callback_data: `provider:${p.key}`,
        }]);

        await ctx.reply("🔌 选择 AI 提供商:", {
            reply_markup: { inline_keyboard: buttons },
        });
    }

    async _handleProviderSelect(ctx) {
        const userId = ctx.from?.id;
        const providerKey = ctx.match[1];
        const provider = getProvider(providerKey);

        if (!provider) {
            return ctx.answerCbQuery("❌ 未知提供商");
        }

        const settings = this._getSettings(userId);
        settings.provider = providerKey;
        settings.model = provider.defaultModel;

        await ctx.answerCbQuery(`✅ 已切换到 ${provider.name}`);
        await ctx.editMessageText(
            `✅ 已选择: *${provider.name}*\n\n📝 默认模型: \`${provider.defaultModel}\`\n\n使用 /models 切换模型`,
            { parse_mode: "Markdown" }
        );
    }

    async _handleModels(ctx) {
        const userId = ctx.from?.id;
        const settings = this._getSettings(userId);
        const provider = getProvider(settings.provider);

        await ctx.reply("⏳ 正在获取模型列表...");

        // Fetch models (with caching)
        let models;
        if (this.cachedModels.has(settings.provider)) {
            models = this.cachedModels.get(settings.provider);
        } else {
            models = await fetchModels(settings.provider, this.config);
            this.cachedModels.set(settings.provider, models);
        }

        if (models.length === 0) {
            return ctx.reply("❌ 当前提供商没有可用模型");
        }

        // Limit to 10 models for UI
        const displayModels = models.slice(0, 10);

        const buttons = displayModels.map((m) => [{
            text: `${m.id === settings.model ? "✅ " : ""}${m.name}`,
            callback_data: `model:${m.id}`,
        }]);

        await ctx.reply(`📝 选择模型 (${provider.name}):`, {
            reply_markup: { inline_keyboard: buttons },
        });
    }

    async _handleModelSelect(ctx) {
        const userId = ctx.from?.id;
        const modelId = ctx.match[1];
        const settings = this._getSettings(userId);

        settings.model = modelId;

        await ctx.answerCbQuery(`✅ 模型已切换`);
        await ctx.editMessageText(`✅ 已选择模型: \`${modelId}\``, { parse_mode: "Markdown" });
    }

    async _handleHelp(ctx) {
        await ctx.reply(
            "🧠 *AI Bot 帮助*\n\n" +
            "/ai <问题> - 向 AI 提问\n" +
            "/providers - 选择 AI 提供商\n" +
            "/models - 选择模型\n\n" +
            "*支持的提供商:*\n" +
            "- Groq (默认)\n" +
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
