# Personal Telegram Userbot Monitor

A professional, plugin-based Telegram application that combines:
- **Userbot (MTProto)**: For monitoring channels and forwarding messages
- **Bot (Bot API)**: For RSS subscription commands

## Features
- **Dual Architecture**: Userbot + Bot working together
- **Channel Monitoring**: Monitor Telegram channels in real-time
- **Keyword Filtering**: Only forward messages containing specific keywords
- **User Whitelist**: Optionally filter by sender
- **RSS Feeds**: 16 curated news sources (BBC, Guardian, HN, etc.)
- **RSS Subscription**: `/sub`, `/unsub`, `/list` commands via Bot
- **Rate Limiting**: Built-in rate limiter to prevent bans
- **PostgreSQL**: Persistent storage for subscriptions
- **Dockerized**: Easy deployment with Docker Compose

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Application                          │
├─────────────────────────────────────────────────────────────┤
│  TelegramService (Userbot)    │    BotService (Bot API)     │
│  - Channel monitoring         │    - /sub, /unsub, /list    │
│  - Message forwarding         │    - RSS update notifications│
├─────────────────────────────────────────────────────────────┤
│                    StorageService (PostgreSQL)              │
└─────────────────────────────────────────────────────────────┘
```

```
src/
├── index.js
├── core/
│   ├── App.js
│   ├── TelegramService.js      # Userbot (MTProto)
│   ├── BotService.js           # Bot API (Telegraf)
│   ├── StorageService.js       # PostgreSQL
│   ├── ConfigService.js
│   ├── FeatureManager.js
│   ├── RateLimiter.js
│   └── Logger.js
└── features/
    ├── BaseFeature.js
    ├── channel-monitor/        # Userbot feature
    ├── rss/                    # Default RSS sources
    └── rss-subscription/       # Bot commands feature
```

## Bot Commands

| Command | Description |
|---------|-------------|
| `/sub <url>` | Subscribe to an RSS feed |
| `/unsub <url or id>` | Unsubscribe from a feed |
| `/list` | List your subscriptions |
| `/check` | Check subscription status |
| `/help` | Show help |

## Setup

### 1. Prerequisites
- Telegram API credentials from [my.telegram.org](https://my.telegram.org)
- Bot Token from [@BotFather](https://t.me/BotFather)
- VPS with Docker

### 2. Generate Session String
```bash
npm install
npm run generate-session
```

### 3. GitHub Secrets

| Secret | Description |
| :--- | :--- |
| `API_ID` | Telegram API ID |
| `API_HASH` | Telegram API Hash |
| `TG_SESSION` | Session string (from step 2) |
| `BOT_TOKEN` | Bot token from @BotFather |
| `SOURCE_CHANNELS` | Channels to monitor |
| `TARGET_CHANNEL` | Output channel |
| `KEYWORDS` | Keywords to filter |
| `VPS_HOST` | VPS IP/Domain |
| `VPS_USER` | SSH Username |
| `VPS_SSH_KEY` | SSH Private Key |

### 4. Deploy
Push to `main` branch to trigger deployment.

### 5. Check Logs
```bash
docker logs -f telegram-userbot-monitor-userbot-1
```
