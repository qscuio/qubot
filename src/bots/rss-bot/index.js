const BotInstance = require("../../core/BotInstance");
const Parser = require("rss-parser");

const parser = new Parser();

/**
 * RssBot - Telegram interface for RSS subscriptions.
 * Delegates subscription logic to RssService.
 * Handles Telegram-specific UI and RSS polling.
 */
class RssBot extends BotInstance {
    constructor(token, config, storage, allowedUsers, rssService = null) {
        super("rss-bot", token, allowedUsers);
        this.config = config;
        this.storage = storage;
        this.rssService = rssService;
        this.pollInterval = null;
        this.pollIntervalMs = 5 * 60 * 1000; // 5 minutes
        this.lastPollBySource = new Map();
        this.pendingSubscriptions = new Map();
    }

    /**
     * Set the RSS service (allows injection after construction).
     */
    setService(rssService) {
        this.rssService = rssService;
    }

    async setup() {
        if (!this.isEnabled()) {
            this.logger.warn("RSS Bot token not configured.");
            return;
        }

        // Register commands
        this.command("start", "Start and get help", (ctx) => this._handleStart(ctx));
        this.command("sub", "Subscribe to RSS feed", (ctx) => this._handleSub(ctx));
        this.command("unsub", "Unsubscribe from feed", (ctx) => this._handleUnsub(ctx));
        this.command("list", "List subscriptions", (ctx) => this._handleList(ctx));
        this.command("status", "Check bot status", (ctx) => this._handleStatus(ctx));
        this.command("help", "Show help", (ctx) => this._handleHelp(ctx));

        // Callback actions
        this.action("cmd_sub", (ctx) => {
            ctx.answerCbQuery();
            return ctx.reply("📌 Usage: /sub <RSS URL>\nExample: /sub https://example.com/feed.xml");
        });
        this.action("cmd_list", (ctx) => this._handleList(ctx));
        this.action("cmd_status", (ctx) => this._handleStatus(ctx));
        this.action("cmd_help", (ctx) => this._handleHelp(ctx));
        this.action("cmd_start", (ctx) => this._handleStart(ctx));
        this.action(/^unsub:(\d+)$/, (ctx) => this._handleUnsubButton(ctx));
        this.action(/^confirm_sub:(.+)$/, (ctx) => this._handleSubConfirm(ctx));
        this.action(/^cancel_sub:(.+)$/, (ctx) => ctx.editMessageText("❌ Subscription cancelled."));

        this.logger.info("RssBot commands registered.");
    }

    _quickActionsKeyboard() {
        return {
            inline_keyboard: [
                [{ text: "➕ Subscribe", callback_data: "cmd_sub" }, { text: "📋 My Feeds", callback_data: "cmd_list" }],
                [{ text: "📊 Status", callback_data: "cmd_status" }, { text: "❓ Help", callback_data: "cmd_help" }],
            ]
        };
    }

    async start() {
        await super.start();
        this._startPolling();
    }

    _startPolling() {
        if (!this.storage && !this.rssService) {
            this.logger.warn("Storage/service not available, RSS polling disabled.");
            return;
        }

        this.pollInterval = setInterval(async () => {
            await this._pollFeeds();
        }, this.pollIntervalMs);

        this.logger.info(`RSS polling started (interval: ${this.pollIntervalMs / 1000}s)`);
    }

    async _pollFeeds() {
        try {
            let sources;
            if (this.rssService) {
                sources = await this.rssService.getAllSources();
            } else if (this.storage) {
                sources = await this.storage.getAllSources();
            } else {
                return;
            }

            this.logger.debug(`Polling ${sources.length} RSS sources...`);

            for (const source of sources) {
                try {
                    await this._fetchAndNotify(source);
                    if (this.storage) {
                        await this.storage.clearSourceErrorCount(source.id);
                    }
                } catch (err) {
                    this.logger.warn(`Failed to fetch ${source.title || source.link}: ${err.message}`);
                    if (this.storage) {
                        await this.storage.incrementSourceErrorCount(source.id);
                    }
                }
            }
        } catch (err) {
            this.logger.error("Poll cycle failed", err);
        }
    }

    async _fetchAndNotify(source) {
        // Rate limiting: minimum 30s between polls per source
        const now = Date.now();
        const lastPoll = this.lastPollBySource.get(source.id) || 0;
        if (now - lastPoll < 30000) {
            return;
        }
        this.lastPollBySource.set(source.id, now);

        const feed = await parser.parseURL(source.link);
        const targetChannel = this.config.get("TARGET_CHANNEL");

        for (const item of feed.items) {
            const itemId = item.guid || item.link || item.title;
            const hashId = `${source.id}:${itemId}`;

            const exists = this.storage ? await this.storage.contentExists(hashId) : false;
            if (exists) {
                break;
            }

            if (this.storage) {
                await this.storage.addContent(hashId, source.id, itemId, item.link, item.title);
            }

            const subscribers = this.storage
                ? await this.storage.getSubscribersBySource(source.id)
                : [];
            const subCount = subscribers.length;

            const message = this._formatUpdate(source, item, subCount);

            try {
                await this.sendMessage(targetChannel, message, {
                    parse_mode: "HTML",
                    disable_web_page_preview: false
                });
                this.logger.info(`Posted update from ${source.title} to ${targetChannel}`);
            } catch (err) {
                this.logger.warn(`Failed to post to ${targetChannel}: ${err.message}`);
            }
        }
    }

    _formatUpdate(source, item, subscriberCount = 0) {
        const title = this._escapeHtml(item.title || "No title");
        const link = item.link || "";
        const snippet = this._escapeHtml((item.contentSnippet || "").substring(0, 200));
        const sourceName = this._escapeHtml(source.title || "RSS");
        const subInfo = subscriberCount > 0 ? ` | ${subscriberCount} subscribers` : "";

        return `📰 <b>${sourceName}</b>${subInfo}\n\n<b>${title}</b>\n\n${snippet}${snippet.length >= 200 ? "..." : ""}\n\n<a href="${link}">Read more →</a>`;
    }

    _escapeHtml(text) {
        if (!text) return "";
        return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    async _handleSub(ctx) {
        const userId = ctx.from?.id;
        const chatId = ctx.chat?.id;
        const url = (ctx.message.text || "").replace("/sub", "").trim();

        if (!url) {
            return ctx.reply("📌 Usage: /sub <RSS URL>\nExample: /sub https://example.com/feed.xml", {
                reply_markup: this._quickActionsKeyboard()
            });
        }

        try {
            await ctx.reply("⏳ Validating RSS feed...");

            // Use service if available
            let validation;
            if (this.rssService) {
                validation = await this.rssService.validateFeed(url);
            } else {
                const feed = await parser.parseURL(url);
                validation = {
                    valid: true,
                    title: feed.title || url,
                    latestItem: feed.items[0]
                };
            }

            if (!validation.valid) {
                return ctx.reply(`❌ Invalid feed: ${validation.error}`, {
                    reply_markup: this._quickActionsKeyboard()
                });
            }

            const title = validation.title;
            const preview = validation.latestItem
                ? `\n\n📄 <b>Latest:</b> ${this._escapeHtml(validation.latestItem.title?.substring(0, 60) || "No title")}...`
                : "";

            // Generate token for confirmation
            const token = `${userId}_${Date.now().toString(36)}`;
            this.pendingSubscriptions.set(token, {
                url,
                title,
                userId,
                chatId,
                expires: Date.now() + 5 * 60 * 1000
            });

            this._cleanupPendingSubscriptions();

            const buttons = [[
                { text: "✅ Subscribe", callback_data: `confirm_sub:${token}` },
                { text: "❌ Cancel", callback_data: `cancel_sub:${token}` }
            ]];

            await ctx.reply(
                `📰 <b>${this._escapeHtml(title)}</b>\n\n🔗 ${url}${preview}\n\n<i>Send updates to TARGET_CHANNEL?</i>`,
                { parse_mode: "HTML", reply_markup: { inline_keyboard: buttons } }
            );
        } catch (err) {
            await ctx.reply(`❌ Subscribe failed: ${err.message}`, {
                reply_markup: this._quickActionsKeyboard()
            });
        }
    }

    _cleanupPendingSubscriptions() {
        const now = Date.now();
        for (const [token, data] of this.pendingSubscriptions) {
            if (data.expires < now) {
                this.pendingSubscriptions.delete(token);
            }
        }
    }

    async _handleSubConfirm(ctx) {
        const token = ctx.match[1];
        const pending = this.pendingSubscriptions.get(token);

        if (!pending) {
            return ctx.answerCbQuery("Request expired. Please use /sub again.");
        }

        this.pendingSubscriptions.delete(token);

        try {
            const { url, title, userId, chatId } = pending;
            let added;

            if (this.rssService) {
                const result = await this.rssService.subscribe(userId, url, chatId);
                added = result.added;
            } else if (this.storage) {
                added = await this.storage.addRssSubscription(userId, chatId, url, title);
            } else {
                await ctx.answerCbQuery("Database unavailable");
                return ctx.editMessageText("❌ Database unavailable. Cannot persist subscriptions.");
            }

            if (added) {
                await ctx.answerCbQuery("Subscribed!");
                await ctx.editMessageText(
                    `✅ <b>Subscribed!</b>\n\n📰 ${this._escapeHtml(title)}\n🔗 ${url}\n\n<i>Updates will be posted to TARGET_CHANNEL.</i>`,
                    { parse_mode: "HTML" }
                );
            } else {
                await ctx.answerCbQuery("Already subscribed");
                await ctx.editMessageText(`⚠️ You're already subscribed to: ${this._escapeHtml(title)}`, { parse_mode: "HTML" });
            }
        } catch (err) {
            await ctx.answerCbQuery(`Error: ${err.message}`);
        }
    }

    async _handleUnsub(ctx) {
        const userId = ctx.from?.id;
        const input = (ctx.message.text || "").replace("/unsub", "").trim();

        if (!input) {
            return ctx.reply("📌 Usage: /unsub <RSS URL or ID>", {
                reply_markup: this._quickActionsKeyboard()
            });
        }

        try {
            if (this.rssService) {
                const result = await this.rssService.unsubscribe(userId, input);
                await ctx.reply(`✅ Unsubscribed: ${result.title}`);
            } else if (this.storage) {
                const subs = await this.storage.getRssSubscriptions(userId);
                const source = subs.find((s) => s.url === input || String(s.id) === input);

                if (!source) {
                    return ctx.reply("❌ Subscription not found.");
                }

                await this.storage.removeRssSubscription(userId, source.url);
                await ctx.reply(`✅ Unsubscribed: ${source.title}`);
            } else {
                return ctx.reply("❌ Database unavailable.", { reply_markup: this._quickActionsKeyboard() });
            }
        } catch (err) {
            await ctx.reply(`❌ Unsubscribe failed: ${err.message}`);
        }
    }

    async _handleList(ctx) {
        const userId = ctx.from?.id;

        try {
            let subs;
            if (this.rssService) {
                subs = await this.rssService.getSubscriptions(userId);
            } else if (this.storage) {
                subs = await this.storage.getRssSubscriptions(userId);
            } else {
                return ctx.reply("❌ Database unavailable.");
            }

            if (subs.length === 0) {
                return ctx.reply("📭 You have no subscriptions.\n\nUse /sub <URL> to add one.", {
                    reply_markup: this._quickActionsKeyboard()
                });
            }

            const buttons = subs.map((s) => [{
                text: `🗑️ ${s.title.substring(0, 25)}`,
                callback_data: `unsub:${s.id}`
            }]);

            buttons.push([{ text: "➕ Subscribe", callback_data: "cmd_sub" }, { text: "🏠 Home", callback_data: "cmd_start" }]);

            await ctx.reply(`📚 <b>Your subscriptions (${subs.length})</b>\n\n<i>Tap to unsubscribe:</i>`, {
                parse_mode: "HTML",
                reply_markup: { inline_keyboard: buttons }
            });

            if (ctx.callbackQuery) {
                await ctx.answerCbQuery();
            }
        } catch (err) {
            await ctx.reply(`❌ Failed to get list: ${err.message}`);
        }
    }

    async _handleUnsubButton(ctx) {
        const userId = ctx.from?.id;
        const sourceId = parseInt(ctx.match[1], 10);

        try {
            let subs;
            if (this.rssService) {
                subs = await this.rssService.getSubscriptions(userId);
            } else {
                subs = await this.storage.getRssSubscriptions(userId);
            }

            const source = subs.find((s) => s.id === sourceId);

            if (!source) {
                return ctx.answerCbQuery("Not found");
            }

            if (this.rssService) {
                await this.rssService.unsubscribe(userId, source.url);
            } else {
                await this.storage.removeRssSubscription(userId, source.url);
            }

            await ctx.answerCbQuery(`Unsubscribed: ${source.title}`);
            await ctx.editMessageText(`✅ Unsubscribed from: ${source.title}`);
        } catch (err) {
            await ctx.answerCbQuery(`Error: ${err.message}`);
        }
    }

    async _handleStart(ctx) {
        const inlineButtons = [
            [{ text: "➕ Subscribe", callback_data: "cmd_sub" }, { text: "📋 My Feeds", callback_data: "cmd_list" }],
            [{ text: "📊 Status", callback_data: "cmd_status" }, { text: "❓ Help", callback_data: "cmd_help" }],
        ];

        await ctx.reply(
            "📰 <b>Welcome to RSS Bot!</b>\n\n" +
            "Subscribe to RSS feeds and get updates in TARGET_CHANNEL.\n\n" +
            "<i>Use the buttons below or send a command to get started!</i>",
            { parse_mode: "HTML", reply_markup: { inline_keyboard: inlineButtons } }
        );
    }

    async _handleStatus(ctx) {
        const userId = ctx.from?.id;
        let subCount = 0;
        let sourceCount = 0;
        const dbStatus = (this.storage || this.rssService) ? "✅ Connected" : "❌ Unavailable";

        try {
            if (this.rssService) {
                const subs = await this.rssService.getSubscriptions(userId);
                subCount = subs.length;
                const sources = await this.rssService.getAllSources();
                sourceCount = sources.length;
            } else if (this.storage) {
                const subs = await this.storage.getRssSubscriptions(userId);
                subCount = subs.length;
                const sources = await this.storage.getAllSources();
                sourceCount = sources.length;
            }
        } catch (err) {
            // Ignore
        }

        await ctx.reply(
            "📊 *RSS Bot Status*\n\n" +
            `• Database: ${dbStatus}\n` +
            `• Your subscriptions: ${subCount}\n` +
            `• Total sources tracked: ${sourceCount}\n` +
            `• Polling interval: 5 min`,
            { parse_mode: "Markdown" }
        );
    }

    async _handleHelp(ctx) {
        await ctx.reply(
            "📰 *RSS Bot Help*\n\n" +
            "/start - Welcome & quick actions\n" +
            "/sub <url> - Subscribe to RSS feed\n" +
            "/unsub <url|id> - Unsubscribe\n" +
            "/list - List subscriptions (with unsub buttons)\n" +
            "/status - Check bot & database status\n" +
            "/help - Show this help",
            { parse_mode: "Markdown" }
        );
    }

    async stop() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
        }
        await super.stop();
    }
}

module.exports = RssBot;
