# QuBot - Multi-Bot Telegram Application

A modular Telegram application with REST API support, built with Python (FastAPI + Aiogram + Telethon).

## Features

### Core Features
- 🤖 **Multi-Bot Architecture** - Multiple Userbots (MTProto) + unlimited Bot API bots
- 🔀 **Master-Slave Monitoring** - First session forwards to target, others monitor only
- 🌐 **REST API** - Full API for AI, RSS, and monitoring
- 📡 **Channel Monitoring** - Monitor Telegram channels with keyword filters and AI summarization
- 📰 **RSS Subscriptions** - User-managed subscriptions delivered to TARGET_CHANNEL
- 🧠 **AI Chat** - Multi-provider AI (Groq, Gemini, OpenAI, Claude, NVIDIA, GLM, MiniMax, OpenRouter) with chat history
- 🔗 **Webhook Mode** - Production-ready with webhook support
- 💾 **PostgreSQL Storage** - Persistent subscriptions, chat history, settings
- 🐳 **Dockerized** - Easy deployment with Docker Compose

### A-Stock Market Features (China Market)
- 📊 **Limit-Up Tracker (涨停追踪)** - Track daily limit-up stocks, streaks (连板), sealed vs burst (首板/炸板)
- 🏭 **Sector Analysis (板块分析)** - Industry & concept sector tracking with daily/weekly/monthly reports
- 🔍 **AI Stock Scanner (启动信号扫描器)** - Scans for startup signals: breakout, volume surge, MA bullish

### Content Intelligence
- 🐦 **Twitter Monitoring** - Follow Twitter accounts, auto-forward new tweets to VIP channel
- 🕷️ **Web Crawler** - Crawl websites, extract content, store structured data
- 🔥 **Hot Words (热词统计)** - Daily trending word statistics with Chinese text segmentation (jieba)
- 🗜️ **Smart Compression** - Message deduplication (SimHash), quality scoring, and auto-categorization

## Bots

### 📰 RSS Bot
| Command | Description |
|---------|-------------|
| `/start` | Main menu with status |
| `/sub <url>` | Subscribe to RSS feed |
| `/unsub` | Unsubscribe (with inline buttons) |
| `/list` | List subscriptions |

**Token:** `RSS_BOT_TOKEN`

### 🧠 AI Bot
| Command | Description |
|---------|-------------|
| `/start` | Main menu with provider/model info |
| `/new` | Start new chat |
| `/chats` | List/switch chats |
| `/providers` | Select AI provider |
| `/models` | Select model |
| `/export` | Export chat to GitHub |

**Token:** `AI_BOT_TOKEN`

### 🤖 Agent Bot (Advanced)
| Command | Description |
|---------|-------------|
| `/start` | Advanced menu with agents/tools |
| `/ask <message>` | Advanced chat with tools |
| `/agent [name]` | Switch agents |
| `/tools` | List tools |
| `/skills` | List skills |
| `/export` | Export chat to GitHub |

**Token:** `AGENT_BOT_TOKEN`

### 🔔 Monitor Bot
| Command | Description |
|---------|-------------|
| `/start` | Main menu with start/stop controls |
| `/status` | Show current status |
| `/help` | Show all commands |
| **Sources** | |
| `/sources` | Manage source channels (with inline buttons) |
| `/add <channel>` | Add source channel |
| `/remove <channel>` | Remove source channel |
| `/clear` | Remove all sources |
| **VIP Users** | |
| `/vips` | Manage VIP users |
| `/vip <user>` | Add VIP user (instant forward, bypasses blacklist) |
| `/unvip <user>` | Remove VIP user |
| **Blacklist** | |
| `/blacklist` | Manage blocked channels |
| `/block <channel>` | Block channel (completely ignore) |
| `/unblock <channel>` | Unblock channel |
| **Twitter** | |
| `/twitters` | Manage Twitter follows |
| `/twitter <username>` | Follow Twitter account |
| `/untwitter <username>` | Unfollow Twitter account |
| **History** | |
| `/history` | Recent forwarded messages |

**Token:** `MONITOR_BOT_TOKEN`

## Architecture

```
                           ┌─────────────────────────────────────┐
                           │            Frontends                │
                           ├─────────────┬───────────────────────┤
                           │  Telegram   │     REST API          │
                           │    Bots     │     (Web UI, etc.)    │
                           └──────┬──────┴───────────┬───────────┘
                                  │                  │
                                  ▼                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Service Layer                             │
├─────────────────┬─────────────────┬─────────────────────────────┤
│   ai_service    │   rss_service   │       monitor_service       │
│   - Chat        │   - Subscribe   │   - Source management       │
│   - Providers   │   - Validate    │   - Keyword filtering       │
│   - Export      │   - Unsubscribe │   - Multi-session monitor   │
└─────────────────┴─────────────────┴─────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                          Storage                                 │
│                    PostgreSQL + Redis                            │
└─────────────────────────────────────────────────────────────────┘
```

### Project Structure

```
qubot/
├── app/
│   ├── api/                 # REST API endpoints
│   │   └── routes.py        # API router
│   ├── bots/                # Telegram bot handlers
│   │   ├── ai/              # AI bot commands
│   │   ├── rss/             # RSS bot commands
│   │   ├── monitor/         # Monitor bot commands
│   │   └── dispatcher.py    # Bot dispatcher
│   ├── services/            # Business logic
│   │   ├── ai/              # AI service + providers
│   │   ├── rss.py           # RSS subscription service
│   │   ├── monitor.py       # Channel monitoring service
│   │   ├── github.py        # GitHub export service
│   │   ├── limit_up.py      # Limit-up stock tracker (涨停追踪)
│   │   ├── sector.py        # Sector analysis service (板块分析)
│   │   ├── stock_scanner.py # AI stock scanner (启动信号扫描器)
│   │   ├── twitter.py       # Twitter monitoring service
│   │   ├── crawler.py       # Web crawler service
│   │   ├── hot_words.py     # Hot words statistics
│   │   ├── market_keywords.py # Market keywords library
│   │   ├── message_compressor.py # Message compression
│   │   └── message_dedup.py # Deduplication (SimHash)
│   ├── providers/           # AI providers
│   │   ├── groq.py
│   │   ├── gemini.py
│   │   ├── openai.py
│   │   ├── claude.py
│   │   ├── nvidia.py
│   │   ├── glm.py
│   │   ├── minimax.py
│   │   └── openrouter.py
│   ├── core/                # Core infrastructure
│   │   ├── config.py        # Settings (pydantic)
│   │   ├── database.py      # PostgreSQL + Redis
│   │   ├── bot.py           # TelegramService (Telethon)
│   │   └── logger.py        # Logging
│   └── main.py              # FastAPI entry point
├── scripts/
│   ├── generate_session.py  # Generate Telethon sessions
│   └── setup_webhook.py     # Register webhooks
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

## Quick Deploy

### Step 1: Configure

```bash
cp .env.example .env
# Edit .env with your values
```

**Required:**
- `TG_SESSIONS_JSON` - Telegram sessions (JSON array, see below)
- Bot tokens: `RSS_BOT_TOKEN`, `AI_BOT_TOKEN`, `AGENT_BOT_TOKEN`, `MONITOR_BOT_TOKEN`

**Sessions JSON Format:**
```json
[
  {
    "session": "1BVtsOH...",
    "api_id": 12345678,
    "api_hash": "abc123def456...",
    "master": true
  },
  {
    "session": "1CWutPI...",
    "api_id": 87654321,
    "api_hash": "xyz789ghi012..."
  }
]
```

> **Note:** The session with `"master": true` forwards messages to TARGET_CHANNEL. Other sessions are slaves (monitor only).
>
> **Important:** The JSON must be on a **single line** when stored as GitHub secret.

**Generating Session Strings:**

```bash
# Run the session generator
docker compose exec userbot python scripts/generate_session.py
```

When prompted:
1. Enter your **API_ID** (from my.telegram.org)
2. Enter your **API_HASH** (from my.telegram.org)
3. Enter your **phone number** (e.g., `+1234567890`)
4. Enter the **login code** sent to your Telegram

### Step 2: Run

```bash
docker compose up -d
docker compose logs -f
```

### Step 3: Verify

**Telegram:** Message your bot with `/start`

**Health Check:**
```bash
curl http://localhost:3888/health
```

## Environment Variables

### Telegram & Bots

| Variable | Description | Example |
|----------|-------------|---------|
| `TG_SESSIONS_JSON` | Telegram sessions JSON array (see Quick Deploy) | `[{"session":"...","api_id":123}]` |
| `MONITOR_BOT_TOKEN` | Monitor bot token (@BotFather) | - |
| `AI_BOT_TOKEN` | AI bot token (@BotFather) | - |
| `AGENT_BOT_TOKEN` | Agent bot token (@BotFather) | - |
| `RSS_BOT_TOKEN` | RSS bot token (@BotFather) | - |
| `CRAWLER_BOT_TOKEN` | Crawler bot token (@BotFather) | - |
| `ALLOWED_USERS` | Allowed Telegram user IDs | `123456789,987654321` |
| `WEBHOOK_URL` | Webhook base URL (optional) | `https://bot.yourdomain.com` |
| `BOT_PORT` | Webhook server port | `3000` |
| `BOT_SECRET` | Webhook security token | Random string |

### AI Configuration

QuBot supports **8 AI providers** with dynamic model fetching:

| Provider | Key Variable | Models |
|----------|--------------|--------|
| **Groq** | `GROQ_API_KEY` | Llama 4, Qwen3, DeepSeek, Mixtral |
| **Gemini** | `GEMINI_API_KEY` | Gemini 3, 2.5 Pro/Flash |
| **OpenAI** | `OPENAI_API_KEY` | GPT-5.x, GPT-4o, o3/o4-mini |
| **Claude** | `CLAUDE_API_KEY` | Claude Opus 4.5, Sonnet 4.5 |
| **NVIDIA** | `NVIDIA_API_KEY` | DeepSeek-V3.2, Nemotron, Llama |
| **GLM** | `GLM_API_KEY` | GLM-4.7, 4.6, 4.5, 4-flash |
| **MiniMax** | `MINIMAX_API_KEY` | M2.1, M2, M1, ABAB-7 |
| **OpenRouter** | `OPENROUTER_API_KEY` | 500+ models (unified gateway) |

> **Tip:** OpenRouter is recommended as it provides access to all providers through a single API key.

**Advanced AI Settings:**

| Variable | Description | Default |
|----------|-------------|---------|
| `AI_ADVANCED_PROVIDER` | Provider for advanced AI features | `groq` |
| `AI_EXTENDED_THINKING` | Enable Claude extended thinking | `false` |
| `SEARX_URL` | SearXNG URL for web search tool | - |
| `GITHUB_TOKEN` | GitHub token for GitHub tools | - |
| `CLOUDFLARE_API_TOKEN` | Cloudflare API token | - |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account ID | - |
| `AI_ALLOWED_PATHS` | Comma-separated allowed paths for file tools | - |

### Monitoring & Content

**Channel Monitoring:**

| Variable | Description | Example |
|----------|-------------|---------|
| `SOURCE_CHANNELS` | Channels to monitor | `-1001234567890,-1009876543210` |
| `TARGET_CHANNEL` | Forward destination | `-1001111111111` |
| `VIP_TARGET_CHANNEL` | VIP user messages destination | `-1002222222222` |
| `REPORT_TARGET_CHANNEL` | Daily reports destination | `-1003333333333` |
| `STOCK_ALERT_CHANNEL` | Limit-up stock alerts destination | `-1004444444444` |
| `BLACKLIST_CHANNELS` | Channels to completely ignore | `@spam,-1009999999999` |
| `KEYWORDS` | Filter keywords (or `none`) | `bitcoin,crypto` |
| `FROM_USERS` | Filter by usernames | `@user1,@user2` |

**Message Processing:**

| Variable | Description | Default |
|----------|-------------|---------|
| `MONITOR_SUMMARIZE` | Enable AI summarization | `true` |
| `MONITOR_BUFFER_SIZE` | Summarize after N messages | `200` |
| `MONITOR_BUFFER_TIMEOUT` | Summarize after N seconds | `7200` (2 hours) |
| `COMPRESSOR_MIN_LENGTH` | Minimum message length | `15` |
| `COMPRESSOR_MAX_MESSAGES` | Max messages after compression | `200` |
| `COMPRESSOR_SCORE_THRESHOLD` | Minimum quality score (0.0-1.0) | `0.2` |
| `DEDUP_CACHE_SIZE` | Max fingerprints to store | `5000` |
| `DEDUP_SIMILARITY_THRESHOLD` | SimHash similarity threshold (0.0-1.0) | `0.85` |

**Twitter Monitoring:**

| Variable | Description |
|----------|-------------|
| `TWITTER_ACCOUNTS` | Twitter credentials JSON: `[{"username":"x","password":"x","email":"x"}]` |

### Services & Features

| Variable | Description | Default |
|----------|-------------|---------|
| `ENABLE_LIMIT_UP` | Enable limit-up stock tracker (涨停追踪) | `true` |
| `ENABLE_SECTOR` | Enable sector analysis (板块分析) | `true` |
| `ENABLE_CRAWLER` | Enable web crawler service | `true` |
| `CRAWLER_INTERVAL_MS` | Crawl interval in milliseconds | `3600000` (1 hour) |
| `NOTES_REPO` | GitHub repo for chat exports | `git@github.com:user/notes.git` |
| `GIT_SSH_KEY_PATH` | SSH key path for GitHub | `/root/.ssh/github_actions` |

### Infrastructure

| Variable | Description | Default |
|----------|-------------|---------|
| `API_ENABLED` | Enable REST API | `true` |
| `API_PORT` | REST API server port | `3001` |
| `API_KEYS` | API keys (format: `key:userId,...`) | - |
| `WEBFRONT_URL` | Web frontend URL (for Nginx SSL) | - |
| `DATABASE_URL` | PostgreSQL connection URL | Auto-configured |
| `REDIS_URL` | Redis connection URL | - |
| `LOG_LEVEL` | Log level: `debug`, `info`, `warn`, `error` | `info` |
| `RATE_LIMIT_MS` | Rate limiting (ms) | `1000` |
| `RSS_POLL_INTERVAL_MS` | RSS poll interval | `300000` (5 min) |

## GitHub Actions Deployment

Add these secrets to your GitHub repository:

| Secret | Description |
|--------|-------------|
| `VPS_HOST` | VPS IP address |
| `VPS_USER` | SSH user |
| `VPS_SSH_KEY` | Private SSH key |
| `TG_SESSIONS_JSON` | Sessions JSON (single line) |
| `MONITOR_BOT_TOKEN` | Monitor bot token |
| `AI_BOT_TOKEN` | AI bot token |
| `AGENT_BOT_TOKEN` | Agent bot token |
| `RSS_BOT_TOKEN` | RSS bot token |
| `WEBHOOK_URL` | Webhook URL |
| `BOT_SECRET` | Webhook secret |
| ... | (other env variables) |

## Debugging

### Check Logs
```bash
docker compose logs -f userbot
docker compose logs userbot | grep -i error
```

### Check Webhook Status
```bash
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```

### Restart Services
```bash
docker compose down && docker compose up -d
docker compose logs -f
```

### Common Issues

| Issue | Solution |
|-------|----------|
| **Webhook rejected: invalid secret** | Restart container to re-register webhooks |
| **Bot not responding** | Check `ALLOWED_USERS` or logs for errors |
| **AI timeout** | Provider may be slow, check logs |

## Development

### Local Development

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run locally
python -m app.main
```

### Adding a New AI Provider

1. Create `app/providers/yourprovider.py`
2. Extend `BaseProvider` class
3. Implement `chat()` and `list_models()` methods
4. Register in `app/services/ai/__init__.py`
5. Add API key to config

### Adding a New Bot

1. Create `app/bots/yourbot/handlers.py`
2. Create router with command handlers
3. Register in `app/bots/dispatcher.py`
4. Add `YOUR_BOT_TOKEN` to config

## License

MIT
