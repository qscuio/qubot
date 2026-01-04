const BaseFeature = require("../BaseFeature");
const Parser = require("rss-parser");
const defaultSources = require("./defaultSources");

/**
 * RssFeature - Fetches RSS feeds and sends updates to Telegram.
 */
class RssFeature extends BaseFeature {
    constructor(services) {
        super(services);
        this.parser = new Parser({
            timeout: 10000,
            headers: {
                "User-Agent": "Mozilla/5.0 (compatible; QuBot/1.0; +https://github.com/qscuio/qubot)",
            },
        });
        this.sources = [];
        this.seenItems = new Set(); // Simple in-memory deduplication
        this.pollIntervalMs = 5 * 60 * 1000; // 5 minutes default
        this.pollTimer = null;
    }

    async onInit() {
        // Load sources from config or use defaults
        const customSources = this.config.get("RSS_SOURCES");
        if (customSources && customSources.length > 0) {
            // Custom sources from env (JSON string expected)
            try {
                this.sources = JSON.parse(customSources);
            } catch (e) {
                this.logger.warn("Failed to parse RSS_SOURCES, using defaults.");
                this.sources = defaultSources;
            }
        } else {
            this.sources = defaultSources;
        }

        // Filter enabled sources
        this.sources = this.sources.filter((s) => s.enabled !== false);

        // Poll interval from config
        const interval = this.config.get("RSS_POLL_INTERVAL_MS");
        if (interval) {
            this.pollIntervalMs = parseInt(interval, 10);
        }

        this.logger.info(`Loaded ${this.sources.length} RSS sources.`);
        this.logger.info(`Poll interval: ${this.pollIntervalMs / 1000}s`);
    }

    async onEnable() {
        if (this.sources.length === 0) {
            this.logger.warn("No RSS sources configured. Feature disabled.");
            return;
        }

        // Initial fetch
        await this._pollAllFeeds();

        // Start polling
        this.pollTimer = setInterval(() => {
            this._pollAllFeeds().catch((err) => {
                this.logger.error("Poll error", err);
            });
        }, this.pollIntervalMs);

        this.logger.info("RSS polling started.");
    }

    async onDisable() {
        if (this.pollTimer) {
            clearInterval(this.pollTimer);
            this.pollTimer = null;
        }
        this.logger.info("RSS polling stopped.");
    }

    async _pollAllFeeds() {
        this.logger.debug("Polling all RSS feeds...");

        for (const source of this.sources) {
            try {
                await this._fetchFeed(source);
            } catch (err) {
                this.logger.warn(`Failed to fetch ${source.name}: ${err.message}`);
            }
        }
    }

    async _fetchFeed(source) {
        const feed = await this.parser.parseURL(source.url);

        for (const item of feed.items.slice(0, 5)) {
            // Only process top 5 per poll
            const itemId = item.guid || item.link || item.title;
            if (this.seenItems.has(itemId)) continue;

            this.seenItems.add(itemId);

            // On first run, just mark as seen, don't send
            if (this.seenItems.size <= this.sources.length * 5) {
                continue;
            }

            await this._sendUpdate(source, item);
        }
    }

    async _sendUpdate(source, item) {
        const targetChannel = this.config.get("TARGET_CHANNEL");

        const message = this._formatMessage(source, item);

        await this.telegram.sendMessage(targetChannel, {
            message,
            parseMode: "html",
            linkPreview: false,
        });

        this.logger.info(`Sent RSS update: [${source.name}] ${item.title?.substring(0, 40)}...`);
    }

    _formatMessage(source, item) {
        const categoryEmoji = {
            news: "📰",
            tech: "💻",
            finance: "📈",
            deep: "🧠",
        };

        const emoji = categoryEmoji[source.category] || "📌";
        const title = this._escapeHtml(item.title || "No title");
        const link = item.link || "";
        const summary = this._escapeHtml(
            (item.contentSnippet || item.content || "").substring(0, 200)
        );

        return `${emoji} <b>${this._escapeHtml(source.name)}</b>\n\n<b>${title}</b>\n\n${summary}${summary.length >= 200 ? "..." : ""}\n\n<a href="${link}">Read more →</a>`;
    }

    _escapeHtml(text) {
        if (!text) return "";
        return text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");
    }
}

module.exports = RssFeature;
