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
        this.command("sub", "Subscribe to RSS feed", (ctx) => this._handleSub(ctx));
        this.command("unsub", "Unsubscribe from feed", (ctx) => this._handleUnsub(ctx));
        this.command("list", "List subscriptions", (ctx) => this._handleList(ctx));
        this.command("check", "Check subscription status", (ctx) => this._handleCheck(ctx));
        this.command("help", "Show help", (ctx) => this._handleHelp(ctx));

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
        // TODO: Implement feed polling and notification
        this.logger.debug("Polling RSS feeds...");
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
                const source = subs.find((s) => s.url === input || s.id === input);

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
            if (this.storage) {
                const subs = await this.storage.getRssSubscriptions(userId);
                if (subs.length === 0) {
                    return ctx.reply("📭 You have no subscriptions.\n\nUse /sub <URL> to add one.");
                }

                let msg = `📚 Your subscriptions (${subs.length})\n\n`;
                subs.forEach((s, i) => {
                    msg += `${i + 1}. ${s.title}\n   ${s.url}\n\n`;
                });
                await ctx.reply(msg);
            }
        } catch (err) {
            await ctx.reply(`❌ Failed to get list: ${err.message}`);
        }
    }

    async _handleCheck(ctx) {
        const userId = ctx.from?.id;

        try {
            if (this.storage) {
                const subs = await this.storage.getRssSubscriptions(userId);
                await ctx.reply(`📊 Status:\n\n• Subscriptions: ${subs.length}\n• Bot: Active\n• Polling: Every 5 min`);
            }
        } catch (err) {
            await ctx.reply(`❌ Check failed: ${err.message}`);
        }
    }

    async _handleHelp(ctx) {
        await ctx.reply(
            "📰 *RSS Bot Help*\n\n" +
            "/sub <url> - Subscribe to RSS feed\n" +
            "/unsub <url|id> - Unsubscribe\n" +
            "/list - List subscriptions\n" +
            "/check - Check status\n" +
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
