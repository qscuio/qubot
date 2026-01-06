# QuBot - Multi-Bot Telegram Application

A modular Telegram application with REST API support, built with Python (FastAPI + Aiogram + Telethon).

## Features

- 🤖 **Multi-Bot Architecture** - Multiple Userbots (MTProto) + unlimited Bot API bots
- 🔀 **Master-Slave Monitoring** - First session forwards to target, others monitor only
- 🌐 **REST API** - Full API for AI, RSS, and monitoring
-  **Channel Monitoring** - Monitor Telegram channels with keyword filters
- 📰 **RSS Subscriptions** - User-managed subscriptions delivered to TARGET_CHANNEL
- 🧠 **AI Chat** - Multi-provider AI (Groq, Gemini, OpenAI, Claude, NVIDIA) with chat history
- 🔗 **Webhook Mode** - Production-ready with webhook support
- 💾 **PostgreSQL Storage** - Persistent subscriptions, chat history, settings
- 🐳 **Dockerized** - Easy deployment with Docker Compose

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

### 🔔 Monitor Bot
| Command | Description |
|---------|-------------|
| `/start` | Main menu with start/stop controls |
| `/sources` | Manage source channels (with inline buttons) |
| `/add <channel>` | Add source channel |
| `/remove <channel>` | Remove source channel |
| `/vip <user>` | Add VIP user (instant forward) |
| `/unvip <user>` | Remove VIP user |
| `/vips` | Manage VIP users |
| `/clear` | Remove all sources |
| `/status` | Show current status |
| `/history` | Recent forwarded messages |
| `/help` | Show all commands |

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
│   │   └── github.py        # GitHub export service
│   ├── providers/           # AI providers
│   │   ├── groq.py
│   │   ├── gemini.py
│   │   ├── openai.py
│   │   ├── claude.py
│   │   └── nvidia.py
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
- Bot tokens: `RSS_BOT_TOKEN`, `AI_BOT_TOKEN`, `MONITOR_BOT_TOKEN`

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

### Telegram Sessions

| Variable | Description |
|----------|-------------|
| `TG_SESSIONS_JSON` | Sessions JSON array (see format above) |

### Bot Tokens

| Variable | Description |
|----------|-------------|
| `MONITOR_BOT_TOKEN` | Monitor bot (@BotFather) |
| `AI_BOT_TOKEN` | AI bot (@BotFather) |
| `RSS_BOT_TOKEN` | RSS bot (@BotFather) |

### Webhook

| Variable | Description | Example |
|----------|-------------|---------|
| `WEBHOOK_URL` | Webhook base URL | `https://bot.yourdomain.com` |
| `BOT_PORT` | Webhook server port | `3888` |
| `BOT_SECRET` | Webhook security token | Random string |

### AI Providers

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

### Monitoring

| Variable | Description | Example |
|----------|-------------|---------|
| `SOURCE_CHANNELS` | Channels to monitor | `-1001234567890,-1009876543210` |
| `TARGET_CHANNEL` | Forward destination | `-1001111111111` |
| `VIP_TARGET_CHANNEL` | VIP user messages destination | `-1002222222222` |
| `KEYWORDS` | Filter keywords (or `none`) | `bitcoin,crypto` |
| `FROM_USERS` | Filter by usernames | `@user1,@user2` |

### Access Control

| Variable | Description |
|----------|-------------|
| `ALLOWED_USERS` | Allowed Telegram user IDs | `123456789,987654321` |

### REST API

| Variable | Description |
|----------|-------------|
| `API_ENABLED` | Enable REST API | `true` |
| `API_KEYS` | API keys (key=userId,...) | `mykey=1` |

### GitHub Export

| Variable | Description |
|----------|-------------|
| `NOTES_REPO` | GitHub repo for exports | `git@github.com:user/notes.git` |
| `GIT_SSH_KEY_PATH` | SSH key path | `/root/.ssh/github_actions` |

### Other

| Variable | Description |
|----------|-------------|
| `LOG_LEVEL` | Log level: `debug`, `info`, `warn`, `error` |
| `RATE_LIMIT_MS` | Rate limiting (ms) | `5000` |

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
