const BotInstance = require("../../core/BotInstance");
const Parser = require("rss-parser");

const parser = new Parser();

/**
 * RssBot - RSS subscription bot.
 * Commands: /sub, /unsub, /list, /check, /help
 */
class RssBot extends BotInstance {
    constructor(token, storage, allowedUsers) {
        super("rss-bot", token, allowedUsers);
        this.storage = storage;
        this.pollInterval = null;
        this.pollIntervalMs = 5 * 60 * 1000; // 5 minutes
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

        // Callback actions for inline buttons
        this.action("cmd_sub", (ctx) => ctx.reply("📌 Usage: /sub <RSS URL>\nExample: /sub https://example.com/feed.xml"));
        this.action("cmd_list", (ctx) => this._handleList(ctx));
        this.action(/^unsub:(\d+)$/, (ctx) => this._handleUnsubButton(ctx));

        this.logger.info("RssBot commands registered.");
    }

    async start() {
        await super.start();
        this._startPolling();
    }

    _startPolling() {
        if (!this.storage) {
            this.logger.warn("Storage not available, RSS polling disabled.");
            return;
        }

        this.pollInterval = setInterval(async () => {
            await this._pollFeeds();
        }, this.pollIntervalMs);

        this.logger.info(`RSS polling started (interval: ${this.pollIntervalMs / 1000}s)`);
    }

    async _pollFeeds() {
        if (!this.storage) return;

        try {
            const sources = await this.storage.getAllSources();
            this.logger.debug(`Polling ${sources.length} RSS sources...`);

            for (const source of sources) {
                try {
                    await this._fetchAndNotify(source);
                    await this.storage.clearSourceErrorCount(source.id);
                } catch (err) {
                    this.logger.warn(`Failed to fetch ${source.title || source.link}: ${err.message}`);
                    await this.storage.incrementSourceErrorCount(source.id);
                }
            }
        } catch (err) {
            this.logger.error("Poll cycle failed", err);
        }
    }

    async _fetchAndNotify(source) {
        const feed = await parser.parseURL(source.link);

        for (const item of feed.items.slice(0, 5)) {
            const itemId = item.guid || item.link || item.title;
            const hashId = `${source.id}:${itemId}`;

            // Skip if already seen
            const exists = await this.storage.contentExists(hashId);
            if (exists) continue;

            // Mark as seen
            await this.storage.addContent(hashId, source.id, itemId, item.link, item.title);

            // Notify all subscribers
            const subscribers = await this.storage.getSubscribersBySource(source.id);
            for (const sub of subscribers) {
                try {
                    const message = this._formatUpdate(source, item);
                    await this.sendMessage(sub.user_id, message, { parse_mode: "HTML", disable_web_page_preview: false });
                } catch (err) {
                    this.logger.warn(`Failed to notify user ${sub.user_id}: ${err.message}`);
                }
            }
        }
    }

    _formatUpdate(source, item) {
        const title = this._escapeHtml(item.title || "No title");
        const link = item.link || "";
        const snippet = this._escapeHtml((item.contentSnippet || "").substring(0, 200));
        const sourceName = this._escapeHtml(source.title || "RSS");

        return `📰 <b>${sourceName}</b>\n\n<b>${title}</b>\n\n${snippet}${snippet.length >= 200 ? "..." : ""}\n\n<a href="${link}">Read more →</a>`;
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
            return ctx.reply("📌 Usage: /sub <RSS URL>\nExample: /sub https://example.com/feed.xml");
        }

        try {
            await ctx.reply("⏳ Validating RSS feed...");
            const feed = await parser.parseURL(url);
            const title = feed.title || url;

            if (this.storage) {
                const added = await this.storage.addRssSubscription(userId, chatId, url, title);
                if (added) {
                    await ctx.reply(`✅ Subscribed!\n\n📰 ${title}\n🔗 ${url}`);
                } else {
                    await ctx.reply(`⚠️ You're already subscribed to: ${title}`);
                }
            }
        } catch (err) {
            await ctx.reply(`❌ Subscribe failed: ${err.message}`);
        }
    }

    async _handleUnsub(ctx) {
        const userId = ctx.from?.id;
        const input = (ctx.message.text || "").replace("/unsub", "").trim();

        if (!input) {
            return ctx.reply("📌 Usage: /unsub <RSS URL or ID>");
        }

        try {
            if (this.storage) {
                const subs = await this.storage.getRssSubscriptions(userId);
                const source = subs.find((s) => s.url === input || String(s.id) === input);

                if (!source) {
                    return ctx.reply("❌ Subscription not found.");
                }

                const removed = await this.storage.removeRssSubscription(userId, source.url);
                if (removed) {
                    await ctx.reply(`✅ Unsubscribed: ${source.title}`);
                } else {
                    await ctx.reply("⚠️ You're not subscribed to this feed.");
                }
            }
        } catch (err) {
            await ctx.reply(`❌ Unsubscribe failed: ${err.message}`);
        }
    }

    async _handleList(ctx) {
        const userId = ctx.from?.id;

        try {
            if (!this.storage) {
                return ctx.reply("❌ Database unavailable.");
            }

            const subs = await this.storage.getRssSubscriptions(userId);
            if (subs.length === 0) {
                return ctx.reply("📭 You have no subscriptions.\n\nUse /sub <URL> to add one.", {
                    reply_markup: {
                        inline_keyboard: [[{ text: "➕ Subscribe", callback_data: "cmd_sub" }]]
                    }
                });
            }

            // Build inline buttons for each subscription
            const buttons = subs.map((s) => [{
                text: `🗑️ ${s.title.substring(0, 25)}`,
                callback_data: `unsub:${s.id}`
            }]);

            await ctx.reply(`📚 *Your subscriptions (${subs.length})*\n\nTap to unsubscribe:`, {
                parse_mode: "Markdown",
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
            const subs = await this.storage.getRssSubscriptions(userId);
            const source = subs.find((s) => s.id === sourceId);

            if (!source) {
                return ctx.answerCbQuery("Not found");
            }

            await this.storage.removeRssSubscription(userId, source.url);
            await ctx.answerCbQuery(`Unsubscribed: ${source.title}`);
            await ctx.editMessageText(`✅ Unsubscribed from: ${source.title}`);
        } catch (err) {
            await ctx.answerCbQuery(`Error: ${err.message}`);
        }
    }

    async _handleStart(ctx) {
        const buttons = [
            [{ text: "➕ Subscribe to Feed", callback_data: "cmd_sub" }],
            [{ text: "📋 My Subscriptions", callback_data: "cmd_list" }],
        ];

        await ctx.reply(
            "📰 *Welcome to RSS Bot!*\n\n" +
            "Subscribe to RSS feeds and get updates directly in Telegram.\n\n" +
            "*Commands:*\n" +
            "/sub <url> - Subscribe to a feed\n" +
            "/list - View subscriptions\n" +
            "/status - Check bot status",
            { parse_mode: "Markdown", reply_markup: { inline_keyboard: buttons } }
        );
    }

    async _handleStatus(ctx) {
        const userId = ctx.from?.id;
        let subCount = 0;
        let sourceCount = 0;
        const dbStatus = this.storage ? "✅ Connected" : "❌ Unavailable";

        if (this.storage) {
            try {
                const subs = await this.storage.getRssSubscriptions(userId);
                subCount = subs.length;
                const sources = await this.storage.getAllSources();
                sourceCount = sources.length;
            } catch (err) {
                // Ignore
            }
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
