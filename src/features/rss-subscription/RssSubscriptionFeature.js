const BaseFeature = require("../BaseFeature");
const Parser = require("rss-parser");
const crypto = require("crypto");

/**
 * RssSubscriptionFeature - User-managed RSS subscriptions via Telegram commands.
 * Commands: /sub, /unsub, /list, /check
 */
class RssSubscriptionFeature extends BaseFeature {
    constructor(services) {
        super(services);
        this.storage = services.storage;
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
        this.enabled = true;
        this.logger.info("RssSubscriptionFeature initialized.");
    }

    async onEnable() {
        if (!this.enabled) return;

        // Register command handlers
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
        const client = this.telegram.getClient();

        // /sub - Subscribe to RSS
        client.addEventHandler(async (event) => {
            const message = event.message;
            if (!message?.message?.startsWith("/sub")) return;

            await this._handleSubCommand(message);
        });

        // /unsub - Unsubscribe
        client.addEventHandler(async (event) => {
            const message = event.message;
            if (!message?.message?.startsWith("/unsub")) return;

            await this._handleUnsubCommand(message);
        });

        // /list - List subscriptions
        client.addEventHandler(async (event) => {
            const message = event.message;
            if (!message?.message?.startsWith("/list")) return;

            await this._handleListCommand(message);
        });

        // /check - Check subscription status
        client.addEventHandler(async (event) => {
            const message = event.message;
            if (!message?.message?.startsWith("/check")) return;

            await this._handleCheckCommand(message);
        });

        this.logger.info("Command handlers registered: /sub, /unsub, /list, /check");
    }

    // ============= Command Handlers =============

    async _handleSubCommand(message) {
        const chatId = message.chatId?.toString() || message.peerId?.userId?.toString();
        const text = message.message;
        const url = this._extractUrl(text);

        if (!url) {
            await this.telegram.sendMessage(chatId, {
                message: "📌 用法: /sub <RSS URL>\n例如: /sub https://example.com/feed.xml",
            });
            return;
        }

        try {
            // Validate RSS feed
            this.logger.info(`Validating RSS: ${url}`);
            const feed = await this.parser.parseURL(url);
            const title = feed.title || "Untitled Feed";

            // Create or get source
            const source = await this.storage.createSource(url, title);

            // Add subscription
            const added = await this.storage.addSubscription(chatId, source.id);

            if (added) {
                await this.telegram.sendMessage(chatId, {
                    message: `✅ 订阅成功!\n\n📰 ${title}\n🔗 ${url}`,
                });
                this.logger.info(`User ${chatId} subscribed to [${source.id}] ${title}`);
            } else {
                await this.telegram.sendMessage(chatId, {
                    message: `⚠️ 你已经订阅过这个源了: ${title}`,
                });
            }
        } catch (err) {
            this.logger.error(`Failed to subscribe to ${url}`, err);
            await this.telegram.sendMessage(chatId, {
                message: `❌ 订阅失败: ${err.message}\n\n请检查URL是否是有效的RSS源。`,
            });
        }
    }

    async _handleUnsubCommand(message) {
        const chatId = message.chatId?.toString() || message.peerId?.userId?.toString();
        const text = message.message;
        const urlOrId = this._extractUrl(text) || text.split(" ")[1];

        if (!urlOrId) {
            await this.telegram.sendMessage(chatId, {
                message: "📌 用法: /unsub <RSS URL 或 ID>\n例如: /unsub https://example.com/feed.xml\n或: /unsub 1",
            });
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
                await this.telegram.sendMessage(chatId, {
                    message: "❌ 未找到该订阅源。",
                });
                return;
            }

            const removed = await this.storage.removeSubscription(chatId, source.id);

            if (removed) {
                await this.telegram.sendMessage(chatId, {
                    message: `✅ 已取消订阅: ${source.title}`,
                });
                this.logger.info(`User ${chatId} unsubscribed from [${source.id}] ${source.title}`);
            } else {
                await this.telegram.sendMessage(chatId, {
                    message: "⚠️ 你没有订阅这个源。",
                });
            }
        } catch (err) {
            this.logger.error(`Failed to unsubscribe`, err);
            await this.telegram.sendMessage(chatId, {
                message: `❌ 取消订阅失败: ${err.message}`,
            });
        }
    }

    async _handleListCommand(message) {
        const chatId = message.chatId?.toString() || message.peerId?.userId?.toString();

        try {
            const subscriptions = await this.storage.getSubscriptionsByUser(chatId);

            if (subscriptions.length === 0) {
                await this.telegram.sendMessage(chatId, {
                    message: "📭 你还没有订阅任何RSS源。\n\n使用 /sub <URL> 添加订阅。",
                });
                return;
            }

            let msg = `📚 你的订阅列表 (${subscriptions.length}个)\n\n`;
            for (const sub of subscriptions) {
                msg += `[${sub.source_id}] ${sub.title || "Untitled"}\n    🔗 ${sub.link}\n\n`;
            }

            await this.telegram.sendMessage(chatId, { message: msg });
        } catch (err) {
            this.logger.error(`Failed to list subscriptions`, err);
            await this.telegram.sendMessage(chatId, {
                message: `❌ 获取订阅列表失败: ${err.message}`,
            });
        }
    }

    async _handleCheckCommand(message) {
        const chatId = message.chatId?.toString() || message.peerId?.userId?.toString();

        try {
            const subscriptions = await this.storage.getSubscriptionsByUser(chatId);
            const sources = await this.storage.getAllSources();

            await this.telegram.sendMessage(chatId, {
                message: `📊 订阅状态\n\n` +
                    `🔢 你的订阅数: ${subscriptions.length}\n` +
                    `📰 系统RSS源总数: ${sources.length}`,
            });
        } catch (err) {
            this.logger.error(`Failed to check status`, err);
            await this.telegram.sendMessage(chatId, {
                message: `❌ 检查状态失败: ${err.message}`,
            });
        }
    }

    // ============= Polling =============

    _startPolling() {
        // Initial poll after 1 min (let the default RSS feature populate first)
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

            // Notify each subscriber
            for (const sub of subscribers) {
                const msg = this._formatMessage(source, item);
                await this.telegram.sendMessage(sub.user_id.toString(), {
                    message: msg,
                    linkPreview: false,
                });
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

        return `📰 ${source.title}\n\n` +
            `**${title}**\n\n` +
            `${snippet}${snippet.length >= 150 ? "..." : ""}\n\n` +
            `🔗 ${link}`;
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
}

module.exports = RssSubscriptionFeature;
