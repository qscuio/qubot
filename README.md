# Personal Telegram Userbot Monitor

A professional, plugin-based Telegram Userbot built with Node.js and GramJS for monitoring channels, filtering messages, and forwarding summaries.

## Features
- **Plugin Architecture**: Extensible design for adding new features easily.
- **Channel Monitoring**: Listen to specific channels for new messages.
- **Keyword Filtering**: Only forward messages containing specific keywords.
- **User Whitelist**: Optionally filter by sender.
- **RSS Feeds**: 15 curated news sources (BBC, Guardian, HN, TechCrunch, etc.)
- **RSS Subscription**: Dynamic `/sub`, `/unsub`, `/list`, `/check` commands
- **Rate Limiting**: Built-in rate limiter to prevent Telegram bans.
- **PostgreSQL**: Persistent storage for subscriptions.
- **Dockerized**: Easy deployment using Docker and Docker Compose.
- **GitHub Actions**: Automated deployment to VPS.

## Architecture

```
src/
├── index.js                    # Entry point
├── core/
│   ├── App.js                  # Main application class
│   ├── TelegramService.js      # Telegram client wrapper
│   ├── ConfigService.js        # Configuration loader
│   ├── StorageService.js       # PostgreSQL storage
│   ├── FeatureManager.js       # Feature lifecycle manager
│   ├── RateLimiter.js          # Rate limiting utility
│   └── Logger.js               # Logging utility
└── features/
    ├── BaseFeature.js          # Abstract base class
    ├── channel-monitor/
    │   └── ChannelMonitorFeature.js
    ├── rss/
    │   ├── RssFeature.js
    │   └── defaultSources.js   # 15 curated RSS sources
    └── rss-subscription/
        └── RssSubscriptionFeature.js  # /sub, /unsub, /list
```

## RSS Subscription Commands

| Command | Description |
|---------|-------------|
| `/sub <url>` | Subscribe to an RSS feed |
| `/unsub <url or id>` | Unsubscribe from a feed |
| `/list` | List your subscriptions |
| `/check` | Check subscription status |

## Setup & Configuration

### 1. Prerequisites
- **Telegram API Credentials**: Get from [my.telegram.org](https://my.telegram.org).
- **Telegram Session String**: Generate once locally.
- **VPS**: A server with Docker and SSH access.

### 2. Generating the Session String
```bash
npm install
npm run generate-session
```

### 3. GitHub Secrets

| Secret Name | Description | Example |
| :--- | :--- | :--- |
| `API_ID` | Telegram API ID | `123456` |
| `API_HASH` | Telegram API Hash | `abcdef123456...` |
| `TG_SESSION` | Session string | `1ApWap...` |
| `SOURCE_CHANNELS` | Channels to monitor | `news_channel,-100123456` |
| `TARGET_CHANNEL` | Output channel | `my_news_feed` |
| `KEYWORDS` | Keywords to filter | `release,launch` |
| `FROM_USERS` | (Optional) User whitelist | `admin,123456` |
| `DATABASE_URL` | PostgreSQL connection | `postgresql://user:pass@host:5432/db` |
| `RATE_LIMIT_MS` | (Optional) Rate limit in ms | `30000` |
| `VPS_HOST` | VPS IP/Domain | `192.168.1.100` |
| `VPS_USER` | SSH Username | `root` |
| `VPS_SSH_KEY` | SSH Private Key | `-----BEGIN...` |

### 4. Deployment
Push to `main` branch to trigger automatic deployment.

### 5. Check Logs
```bash
docker logs -f telegram-userbot-monitor-userbot-1
```

## Adding New Features

1. Create folder in `src/features/`
2. Create `*Feature.js` extending `BaseFeature`
3. Implement `onInit()` and `onEnable()`
4. The `FeatureManager` will automatically discover and load it.
