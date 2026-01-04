/**
 * Default RSS sources - curated high-quality feeds.
 */
module.exports = [
    // === 综合新闻 ===
    {
        name: "BBC News",
        url: "https://feeds.bbci.co.uk/news/rss.xml",
        category: "news",
        enabled: true,
    },
    {
        name: "Reuters",
        url: "https://www.reuters.com/rssFeed/worldNews",
        category: "news",
        enabled: true,
    },
    {
        name: "Associated Press",
        url: "https://apnews.com/rss",
        category: "news",
        enabled: true,
    },
    {
        name: "财新网",
        url: "https://www.caixin.com/rss/all.xml",
        category: "news",
        enabled: true,
    },

    // === 科技 / 互联网 / 创业 ===
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
        name: "36氪",
        url: "https://36kr.com/feed",
        category: "tech",
        enabled: true,
    },

    // === 商业 / 金融 / 宏观 ===
    {
        name: "Financial Times",
        url: "https://www.ft.com/rss/home",
        category: "finance",
        enabled: true,
    },
    {
        name: "The Economist",
        url: "https://www.economist.com/rss",
        category: "finance",
        enabled: true,
    },
    {
        name: "华尔街见闻",
        url: "https://wallstreetcn.com/rss",
        category: "finance",
        enabled: true,
    },

    // === 深度 / 思想 / 长文 ===
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
        name: "Medium AI",
        url: "https://medium.com/feed/tag/artificial-intelligence",
        category: "deep",
        enabled: true,
    },
];
