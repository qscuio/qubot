const BotInstance = require("../../core/BotInstance");
const Parser = require("rss-parser");
const crypto = require("crypto");

/**
 * RssBot - Handles RSS subscription commands.
 */
class RssBot extends BotInstance {
    constructor(token, storage) {
        super("rss-bot", token);
        this.storage = storage;
        this.parser = new Parser({
            timeout: 15000,
            headers: {
                "User-Agent": "Mozilla/5.0 (compatible; QuBot/1.0)",
            },
        });
        this.pollIntervalMs = 5 * 60 * 1000;
        this.pollTimer = null;
    }

    async setup() {
        if (!this.isEnabled()) {
            this.logger.warn("RSS Bot token not configured.");
            return;
        }

        // Register commands
        this.command("sub", "订阅 RSS 源", (ctx) => this._handleSub(ctx));
        this.command("unsub", "取消订阅", (ctx) => this._handleUnsub(ctx));
        this.command("list", "查看订阅列表", (ctx) => this._handleList(ctx));
        this.command("check", "检查订阅状态", (ctx) => this._handleCheck(ctx));
        this.command("help", "帮助", (ctx) => this._handleHelp(ctx));

        this.logger.info("RssBot commands registered.");
    }

    async start() {
        await super.start();

        // Start polling if storage is available
        if (this.storage && this.storage.pool) {
            this._startPolling();
        }
    }

    async stop() {
        if (this.pollTimer) {
            clearInterval(this.pollTimer);
            this.pollTimer = null;
        }
        await super.stop();
    }

    // ============= Command Handlers =============

    async _handleSub(ctx) {
        const chatId = ctx.chat.id;
        const text = ctx.message.text;
        const url = this._extractUrl(text);

        if (!url) {
            return ctx.reply("📌 用法: /sub <RSS URL>\n例如: /sub https://example.com/feed.xml");
        }

        try {
            await ctx.reply("⏳ 正在验证 RSS 源...");
            const feed = await this.parser.parseURL(url);
            const title = feed.title || "Untitled Feed";

            const source = await this.storage.createSource(url, title);
            const added = await this.storage.addSubscription(chatId, source.id);

            if (added) {
                await ctx.reply(`✅ 订阅成功!\n\n📰 ${title}\n🔗 ${url}`);
                this.logger.info(`User ${chatId} subscribed to [${source.id}] ${title}`);
            } else {
                await ctx.reply(`⚠️ 你已经订阅过这个源了: ${title}`);
            }
        } catch (err) {
            this.logger.error(`Failed to subscribe to ${url}`, err);
            await ctx.reply(`❌ 订阅失败: ${err.message}`);
        }
    }

    async _handleUnsub(ctx) {
        const chatId = ctx.chat.id;
        const args = ctx.message.text.split(" ").slice(1);
        const urlOrId = args[0];

        if (!urlOrId) {
            return ctx.reply("📌 用法: /unsub <RSS URL 或 ID>");
        }

        try {
            let source;
            if (/^\d+$/.test(urlOrId)) {
                source = await this.storage.getSourceById(parseInt(urlOrId));
            } else {
                source = await this.storage.getSourceByLink(urlOrId);
            }

            if (!source) {
                return ctx.reply("❌ 未找到该订阅源。");
            }

            const removed = await this.storage.removeSubscription(chatId, source.id);
            if (removed) {
                await ctx.reply(`✅ 已取消订阅: ${source.title}`);
            } else {
                await ctx.reply("⚠️ 你没有订阅这个源。");
            }
        } catch (err) {
            await ctx.reply(`❌ 取消订阅失败: ${err.message}`);
        }
    }

    async _handleList(ctx) {
        const chatId = ctx.chat.id;

        try {
            const subs = await this.storage.getSubscriptionsByUser(chatId);

            if (subs.length === 0) {
                return ctx.reply("📭 你还没有订阅任何RSS源。\n\n使用 /sub <URL> 添加订阅。");
            }

            let msg = `📚 你的订阅列表 (${subs.length}个)\n\n`;
            for (const sub of subs) {
                msg += `[${sub.source_id}] ${sub.title || "Untitled"}\n`;
            }
            await ctx.reply(msg);
        } catch (err) {
            await ctx.reply(`❌ 获取列表失败: ${err.message}`);
        }
    }

    async _handleCheck(ctx) {
        const chatId = ctx.chat.id;

        try {
            const subs = await this.storage.getSubscriptionsByUser(chatId);
            const sources = await this.storage.getAllSources();

            await ctx.reply(
                `📊 订阅状态\n\n` +
                `🔢 你的订阅数: ${subs.length}\n` +
                `📰 系统RSS源总数: ${sources.length}`
            );
        } catch (err) {
            await ctx.reply(`❌ 检查失败: ${err.message}`);
        }
    }

    async _handleHelp(ctx) {
        await ctx.reply(
            "📖 *RSS 订阅帮助*\n\n" +
            "/sub <url> - 订阅 RSS 源\n" +
            "/unsub <url 或 id> - 取消订阅\n" +
            "/list - 查看订阅列表\n" +
            "/check - 检查订阅状态",
            { parse_mode: "Markdown" }
        );
    }

    // ============= Polling =============

    _startPolling() {
        setTimeout(() => {
            this._pollFeeds().catch((e) => this.logger.error("Poll error", e));
        }, 60000);

        this.pollTimer = setInterval(() => {
            this._pollFeeds().catch((e) => this.logger.error("Poll error", e));
        }, this.pollIntervalMs);

        this.logger.info(`Started polling every ${this.pollIntervalMs / 1000}s`);
    }

    async _pollFeeds() {
        const sources = await this.storage.getAllSources();

        for (const source of sources) {
            try {
                const feed = await this.parser.parseURL(source.link);

                for (const item of feed.items.slice(0, 5)) {
                    const hashId = this._generateHashId(source.link, item.guid || item.link);

                    if (await this.storage.contentExists(hashId)) continue;

                    await this.storage.addContent(
                        hashId, source.id, item.guid || "", item.link || "", item.title || ""
                    );

                    const subs = await this.storage.getSubscribersBySource(source.id);
                    for (const sub of subs) {
                        try {
                            const msg = `📰 *${source.title}*\n\n*${item.title || "No title"}*\n\n[阅读原文](${item.link})`;
                            await this.sendMessage(sub.user_id, msg, { parse_mode: "Markdown" });
                        } catch (e) {
                            this.logger.warn(`Failed to send to ${sub.user_id}`);
                        }
                    }
                }

                await this.storage.clearSourceErrorCount(source.id);
            } catch (err) {
                await this.storage.incrementSourceErrorCount(source.id);
            }
        }
    }

    _extractUrl(text) {
        const match = text.match(/https?:\/\/[^\s]+/);
        return match ? match[0] : null;
    }

    _generateHashId(sourceLink, itemId) {
        return crypto.createHash("md5").update(`${sourceLink}:${itemId}`).digest("hex");
    }
}

module.exports = RssBot;
