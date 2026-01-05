const Logger = require("../core/Logger");
const Parser = require("rss-parser");

const parser = new Parser();

/**
 * RssService - Business logic for RSS subscription management.
 * Decoupled from Telegram, can be used by REST API or any frontend.
 * Can use AiService for content analysis if available.
 */
class RssService {
    constructor(config, storage, aiService = null) {
        this.config = config;
        this.storage = storage;
        this.aiService = aiService;
        this.logger = new Logger("RssService");
    }

    /**
     * Set the AI service (allows injection after construction).
     */
    setAiService(aiService) {
        this.aiService = aiService;
    }

    /**
     * Validate an RSS feed URL.
     * Returns feed info if valid.
     */
    async validateFeed(url) {
        try {
            const feed = await parser.parseURL(url);
            const latestItem = feed.items[0];

            return {
                valid: true,
                title: feed.title || url,
                description: feed.description || "",
                itemCount: feed.items.length,
                latestItem: latestItem ? {
                    title: latestItem.title,
                    link: latestItem.link,
                    pubDate: latestItem.pubDate
                } : null
            };
        } catch (err) {
            return {
                valid: false,
                error: err.message
            };
        }
    }

    /**
     * Subscribe to an RSS feed.
     */
    async subscribe(userId, url, chatId = null) {
        if (!this.storage) {
            throw new Error("Storage not available");
        }

        // Validate feed first
        const validation = await this.validateFeed(url);
        if (!validation.valid) {
            throw new Error(`Invalid RSS feed: ${validation.error}`);
        }

        const added = await this.storage.addRssSubscription(
            userId,
            chatId || userId,
            url,
            validation.title
        );

        return {
            added,
            title: validation.title,
            url
        };
    }

    /**
     * Unsubscribe from an RSS feed.
     */
    async unsubscribe(userId, sourceIdOrUrl) {
        if (!this.storage) {
            throw new Error("Storage not available");
        }

        const subs = await this.storage.getRssSubscriptions(userId);
        const source = subs.find(s =>
            s.url === sourceIdOrUrl ||
            String(s.id) === String(sourceIdOrUrl)
        );

        if (!source) {
            throw new Error("Subscription not found");
        }

        const removed = await this.storage.removeRssSubscription(userId, source.url);
        return {
            removed,
            title: source.title,
            url: source.url
        };
    }

    /**
     * Get user's RSS subscriptions.
     */
    async getSubscriptions(userId) {
        if (!this.storage) {
            return [];
        }
        return await this.storage.getRssSubscriptions(userId);
    }

    /**
     * Get all RSS sources in the system.
     */
    async getAllSources() {
        if (!this.storage) {
            return [];
        }
        return await this.storage.getAllSources();
    }

    /**
     * Fetch and process a single feed.
     * Returns new items found.
     */
    async fetchFeed(sourceId) {
        if (!this.storage) {
            throw new Error("Storage not available");
        }

        const source = await this.storage.getSourceById(sourceId);
        if (!source) {
            throw new Error("Source not found");
        }

        const feed = await parser.parseURL(source.link);
        const newItems = [];

        for (const item of feed.items) {
            const itemId = item.guid || item.link || item.title;
            const hashId = `${source.id}:${itemId}`;

            const exists = await this.storage.contentExists(hashId);
            if (exists) {
                break; // Stop at first seen item
            }

            await this.storage.addContent(hashId, source.id, itemId, item.link, item.title);
            newItems.push({
                title: item.title,
                link: item.link,
                snippet: (item.contentSnippet || "").substring(0, 200),
                pubDate: item.pubDate
            });
        }

        return {
            source: {
                id: source.id,
                title: source.title,
                link: source.link
            },
            newItems
        };
    }

    // ============================================================
    // AI-POWERED ANALYSIS METHODS
    // ============================================================

    /**
     * Summarize an RSS item's content using AI.
     * @param {object} item - RSS item with content
     * @returns {Promise<string>} - AI-generated summary
     */
    async summarizeItem(item) {
        if (!this.aiService?.isAnalysisAvailable()) {
            return item.contentSnippet || item.title || "";
        }

        const content = item.content || item.contentSnippet || item.title;
        return await this.aiService.summarize(content, 150);
    }

    /**
     * Categorize an RSS item into categories.
     * @param {object} item - RSS item
     * @param {string[]} categories - Available categories
     */
    async categorizeItem(item, categories) {
        if (!this.aiService?.isAnalysisAvailable()) {
            return { category: "uncategorized", confidence: "low", reasoning: "AI not available" };
        }

        const text = `${item.title || ""}\n\n${item.contentSnippet || ""}`;
        return await this.aiService.categorize(text, categories);
    }

    /**
     * Analyze feed items and rank by relevance to a query.
     * @param {object[]} items - Feed items
     * @param {string} query - User's interest query
     * @returns {Promise<object[]>} - Items with relevance scores
     */
    async rankByRelevance(items, query) {
        if (!this.aiService?.isAnalysisAvailable() || items.length === 0) {
            return items.map((item, idx) => ({ ...item, relevance: 1 - idx * 0.1 }));
        }
        try {
            return await this.aiService.rankByRelevance(items, query);
        } catch (err) {
            this.logger.warn("Relevance ranking failed", err.message);
            return items;
        }
    }
}

module.exports = RssService;
