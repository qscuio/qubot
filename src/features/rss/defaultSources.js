/**
 * Default RSS sources - curated high-quality feeds.
 * Updated with verified working URLs.
 */
module.exports = [
    // === 综合新闻 (Working) ===
    {
        name: "BBC News",
        url: "https://feeds.bbci.co.uk/news/rss.xml",
        category: "news",
        enabled: true,
    },
    {
        name: "The Guardian",
        url: "https://www.theguardian.com/world/rss",
        category: "news",
        enabled: true,
    },
    {
        name: "NPR News",
        url: "https://feeds.npr.org/1001/rss.xml",
        category: "news",
        enabled: true,
    },
    {
        name: "Al Jazeera",
        url: "https://www.aljazeera.com/xml/rss/all.xml",
        category: "news",
        enabled: true,
    },

    // === 科技 / 互联网 / 创业 (Working) ===
    {
        name: "Hacker News",
        url: "https://hnrss.org/frontpage",
        category: "tech",
        enabled: true,
    },
    {
        name: "TechCrunch",
        url: "https://techcrunch.com/feed/",
        category: "tech",
        enabled: true,
    },
    {
        name: "The Verge",
        url: "https://www.theverge.com/rss/index.xml",
        category: "tech",
        enabled: true,
    },
    {
        name: "Ars Technica",
        url: "https://feeds.arstechnica.com/arstechnica/index",
        category: "tech",
        enabled: true,
    },
    {
        name: "Wired",
        url: "https://www.wired.com/feed/rss",
        category: "tech",
        enabled: true,
    },

    // === 商业 / 金融 / 宏观 (Working) ===
    {
        name: "Financial Times",
        url: "https://www.ft.com/rss/home",
        category: "finance",
        enabled: true,
    },
    {
        name: "Bloomberg",
        url: "https://feeds.bloomberg.com/markets/news.rss",
        category: "finance",
        enabled: true,
    },
    {
        name: "CNBC",
        url: "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        category: "finance",
        enabled: true,
    },

    // === 深度 / 思想 / 长文 (Working) ===
    {
        name: "The Atlantic",
        url: "https://www.theatlantic.com/feed/all/",
        category: "deep",
        enabled: true,
    },
    {
        name: "MIT Technology Review",
        url: "https://www.technologyreview.com/feed/",
        category: "deep",
        enabled: true,
    },
    {
        name: "Quanta Magazine",
        url: "https://api.quantamagazine.org/feed/",
        category: "deep",
        enabled: true,
    },
];
