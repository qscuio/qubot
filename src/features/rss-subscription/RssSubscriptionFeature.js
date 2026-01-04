const BaseFeature = require("../BaseFeature");
const Parser = require("rss-parser");
const crypto = require("crypto");

/**
 * RssSubscriptionFeature - User-managed RSS subscriptions via Bot commands.
 * Uses Bot API for commands, Userbot for sending updates.
 */
class RssSubscriptionFeature extends BaseFeature {
    constructor(services) {
        super(services);
        this.storage = services.storage;
        this.bot = services.bot;
        this.parser = new Parser({
            timeout: 15000,
            headers: {
                "User-Agent": "Mozilla/5.0 (compatible; QuBot/1.0)",
            },
        });
        this.pollIntervalMs = 5 * 60 * 1000; // 5 minutes
        this.pollTimer = null;
    }

    async onInit() {
        if (!this.storage || !this.storage.pool) {
            this.logger.warn("Storage not available. RssSubscriptionFeature disabled.");
            this.enabled = false;
            return;
        }
        if (!this.bot || !this.bot.isEnabled()) {
            this.logger.warn("Bot not available. RssSubscriptionFeature disabled.");
            this.enabled = false;
            return;
        }
        this.enabled = true;
        this.logger.info("RssSubscriptionFeature initialized.");
    }

    async onEnable() {
        if (!this.enabled) return;

        // Register bot commands
        this._registerCommands();

        // Start polling for updates
        this._startPolling();

        this.logger.info("RssSubscriptionFeature enabled.");
    }

    async onDisable() {
        if (this.pollTimer) {
            clearInterval(this.pollTimer);
            this.pollTimer = null;
        }
        this.logger.info("RssSubscriptionFeature disabled.");
    }

    _registerCommands() {
        // /sub - Subscribe to RSS
        this.bot.command("sub", async (ctx) => {
            await this._handleSubCommand(ctx);
        });

        // /unsub - Unsubscribe
        this.bot.command("unsub", async (ctx) => {
            await this._handleUnsubCommand(ctx);
        });

        // /list - List subscriptions
        this.bot.command("list", async (ctx) => {
            await this._handleListCommand(ctx);
        });

        // /check - Check subscription status
        this.bot.command("check", async (ctx) => {
            await this._handleCheckCommand(ctx);
        });

        // /help - Help
        this.bot.command("help", async (ctx) => {
            await ctx.reply(
                "📖 *RSS 订阅帮助*\n\n" +
                "/sub <url> - 订阅 RSS 源\n" +
                "/unsub <url 或 id> - 取消订阅\n" +
                "/list - 查看订阅列表\n" +
                "/check - 检查订阅状态",
                { parse_mode: "Markdown" }
            );
        });

        this.logger.info("Bot commands registered: /sub, /unsub, /list, /check, /help");
    }

    // ============= Command Handlers =============

    async _handleSubCommand(ctx) {
        const chatId = ctx.chat.id;
        const text = ctx.message.text;
        const url = this._extractUrl(text);

        if (!url) {
            await ctx.reply(
                "📌 用法: /sub <RSS URL>\n例如: /sub https://example.com/feed.xml"
            );
            return;
        }

        try {
            // Validate RSS feed
            this.logger.info(`Validating RSS: ${url}`);
            await ctx.reply("⏳ 正在验证 RSS 源...");

            const feed = await this.parser.parseURL(url);
            const title = feed.title || "Untitled Feed";

            // Create or get source
            const source = await this.storage.createSource(url, title);

            // Add subscription
            const added = await this.storage.addSubscription(chatId, source.id);

            if (added) {
                await ctx.reply(`✅ 订阅成功!\n\n📰 ${title}\n🔗 ${url}`);
                this.logger.info(`User ${chatId} subscribed to [${source.id}] ${title}`);
            } else {
                await ctx.reply(`⚠️ 你已经订阅过这个源了: ${title}`);
            }
        } catch (err) {
            this.logger.error(`Failed to subscribe to ${url}`, err);
            await ctx.reply(`❌ 订阅失败: ${err.message}\n\n请检查URL是否是有效的RSS源。`);
        }
    }

    async _handleUnsubCommand(ctx) {
        const chatId = ctx.chat.id;
        const text = ctx.message.text;
        const args = text.split(" ").slice(1);
        const urlOrId = args[0];

        if (!urlOrId) {
            await ctx.reply(
                "📌 用法: /unsub <RSS URL 或 ID>\n例如: /unsub https://example.com/feed.xml\n或: /unsub 1"
            );
            return;
        }

        try {
            let source;
            if (/^\d+$/.test(urlOrId)) {
                source = await this.storage.getSourceById(parseInt(urlOrId));
            } else {
                source = await this.storage.getSourceByLink(urlOrId);
            }

            if (!source) {
                await ctx.reply("❌ 未找到该订阅源。");
                return;
            }

            const removed = await this.storage.removeSubscription(chatId, source.id);

            if (removed) {
                await ctx.reply(`✅ 已取消订阅: ${source.title}`);
                this.logger.info(`User ${chatId} unsubscribed from [${source.id}] ${source.title}`);
            } else {
                await ctx.reply("⚠️ 你没有订阅这个源。");
            }
        } catch (err) {
            this.logger.error(`Failed to unsubscribe`, err);
            await ctx.reply(`❌ 取消订阅失败: ${err.message}`);
        }
    }

    async _handleListCommand(ctx) {
        const chatId = ctx.chat.id;

        try {
            const subscriptions = await this.storage.getSubscriptionsByUser(chatId);

            if (subscriptions.length === 0) {
                await ctx.reply(
                    "📭 你还没有订阅任何RSS源。\n\n使用 /sub <URL> 添加订阅。"
                );
                return;
            }

            let msg = `📚 *你的订阅列表* (${subscriptions.length}个)\n\n`;
            for (const sub of subscriptions) {
                msg += `\\[${sub.source_id}\\] ${this._escapeMarkdown(sub.title || "Untitled")}\n`;
            }

            await ctx.reply(msg, { parse_mode: "MarkdownV2" });
        } catch (err) {
            this.logger.error(`Failed to list subscriptions`, err);
            await ctx.reply(`❌ 获取订阅列表失败: ${err.message}`);
        }
    }

    async _handleCheckCommand(ctx) {
        const chatId = ctx.chat.id;

        try {
            const subscriptions = await this.storage.getSubscriptionsByUser(chatId);
            const sources = await this.storage.getAllSources();

            await ctx.reply(
                `📊 *订阅状态*\n\n` +
                `🔢 你的订阅数: ${subscriptions.length}\n` +
                `📰 系统RSS源总数: ${sources.length}`,
                { parse_mode: "Markdown" }
            );
        } catch (err) {
            this.logger.error(`Failed to check status`, err);
            await ctx.reply(`❌ 检查状态失败: ${err.message}`);
        }
    }

    // ============= Polling =============

    _startPolling() {
        // Initial poll after 1 min
        setTimeout(() => {
            this._pollSubscribedFeeds().catch((e) => this.logger.error("Poll error", e));
        }, 60000);

        // Regular polling
        this.pollTimer = setInterval(() => {
            this._pollSubscribedFeeds().catch((e) => this.logger.error("Poll error", e));
        }, this.pollIntervalMs);

        this.logger.info(`Started polling subscribed feeds every ${this.pollIntervalMs / 1000}s`);
    }

    async _pollSubscribedFeeds() {
        const sources = await this.storage.getAllSources();
        this.logger.debug(`Polling ${sources.length} subscribed sources...`);

        for (const source of sources) {
            try {
                await this._fetchAndNotify(source);
                await this.storage.clearSourceErrorCount(source.id);
            } catch (err) {
                this.logger.warn(`Failed to fetch ${source.title}: ${err.message}`);
                await this.storage.incrementSourceErrorCount(source.id);
            }
        }
    }

    async _fetchAndNotify(source) {
        const feed = await this.parser.parseURL(source.link);

        for (const item of feed.items.slice(0, 5)) {
            const hashId = this._generateHashId(source.link, item.guid || item.link);

            // Check if already seen
            const exists = await this.storage.contentExists(hashId);
            if (exists) continue;

            // Save content
            await this.storage.addContent(
                hashId,
                source.id,
                item.guid || "",
                item.link || "",
                item.title || ""
            );

            // Get subscribers
            const subscribers = await this.storage.getSubscribersBySource(source.id);

            // Notify each subscriber via Bot
            for (const sub of subscribers) {
                const msg = this._formatMessage(source, item);
                try {
                    await this.bot.sendMessage(sub.user_id, msg, {
                        parse_mode: "Markdown",
                        disable_web_page_preview: false,
                    });
                } catch (err) {
                    this.logger.warn(`Failed to send to ${sub.user_id}: ${err.message}`);
                }
            }

            if (subscribers.length > 0) {
                this.logger.info(`Notified ${subscribers.length} users about: ${item.title?.substring(0, 40)}...`);
            }
        }
    }

    _formatMessage(source, item) {
        const title = item.title || "No title";
        const link = item.link || "";
        const snippet = (item.contentSnippet || "").substring(0, 150);

        return `📰 *${this._escapeMarkdown(source.title)}*\n\n` +
            `*${this._escapeMarkdown(title)}*\n\n` +
            `${this._escapeMarkdown(snippet)}${snippet.length >= 150 ? "..." : ""}\n\n` +
            `[阅读原文](${link})`;
    }

    _extractUrl(text) {
        const match = text.match(/https?:\/\/[^\s]+/);
        return match ? match[0] : null;
    }

    _generateHashId(sourceLink, itemId) {
        return crypto
            .createHash("md5")
            .update(`${sourceLink}:${itemId}`)
            .digest("hex");
    }

    _escapeMarkdown(text) {
        if (!text) return "";
        return text.replace(/[_*[\]()~`>#+=|{}.!-]/g, "\\$&");
    }
}

module.exports = RssSubscriptionFeature;
