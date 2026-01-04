# QuBot - Multi-Bot Telegram Application

A professional, modular Telegram application with REST API support for building alternative frontends.

## Features

- 🤖 **Multi-Bot Architecture** - 1 Userbot (MTProto) + unlimited Bot API bots
- 🌐 **REST API** - Full API for AI, RSS, and monitoring (run your own UI!)
- 🔌 **WebSocket** - Real-time message streaming from monitored channels
- 📡 **Channel Monitoring** - Monitor Telegram channels with keyword filters
- 📰 **RSS Subscriptions** - User-managed subscriptions delivered to TARGET_CHANNEL
- 🧠 **AI Chat** - Multi-provider AI (Groq, Gemini, OpenAI, Claude, NVIDIA) with chat history
- 🔗 **Webhook Mode** - Nginx reverse proxy with Let's Encrypt SSL
- 💾 **PostgreSQL Storage** - Persistent subscriptions, chat history, settings
- 🐳 **Dockerized** - Easy deployment with Docker Compose

## Bots

### 📰 RSS Bot
| Command | Description |
|---------|-------------|
| `/start` | Welcome & quick actions |
| `/sub <url>` | Subscribe to RSS feed |
| `/unsub <id>` | Unsubscribe |
| `/list` | List subscriptions |
| `/status` | Check bot status |

**Token:** `RSS_BOT_TOKEN`

### 🧠 AI Bot
| Command | Description |
|---------|-------------|
| `/ai <text>` | Ask AI (or just send a message) |
| `/new` | Start new chat |
| `/chats` | List/switch chats |
| `/providers` | Select AI provider |
| `/models` | Select model |
| `/export` | Export chat to GitHub |

**Token:** `AI_BOT_TOKEN`

### 🔔 Monitor Bot
| Command | Description |
|---------|-------------|
| `/sources` | List source channels |
| `/add <channel>` | Add source channel |
| `/remove <channel>` | Remove source |
| `/history` | Recent forwarded messages |
| `/monitor` | Start/stop monitoring |
| `/filters` | Show filter policies |

**Token:** `MONITOR_BOT_TOKEN`

## Architecture

```
                           ┌─────────────────────────────────────┐
                           │            Frontends                │
                           ├─────────────┬───────────────────────┤
                           │  Telegram   │     REST API / WS     │
                           │    Bots     │     (Web UI, etc.)    │
                           └──────┬──────┴───────────┬───────────┘
                                  │                  │
                                  ▼                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Service Layer                             │
├─────────────────┬─────────────────┬─────────────────────────────┤
│   AiService     │   RssService    │       MonitorService        │
│   - Chat        │   - Subscribe   │   - Source management       │
│   - Providers   │   - Validate    │   - Real-time streaming     │
│   - Export      │   - Unsubscribe │   - Filter policies         │
└─────────────────┴─────────────────┴─────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                          Storage                                 │
│                    PostgreSQL + Redis                            │
└─────────────────────────────────────────────────────────────────┘
```

```
src/
├── api/                    # REST API
│   ├── ApiServer.js        # Express server
│   ├── WebSocketHandler.js # Real-time streaming
│   └── auth.js             # API key auth
├── services/               # Business logic (decoupled from Telegram)
│   ├── AiService.js        # AI chat logic
│   ├── RssService.js       # RSS subscription logic
│   └── MonitorService.js   # Channel monitoring logic
├── bots/                   # Telegram bots (thin wrappers)
│   ├── ai-bot/             # AI chat commands
│   ├── rss-bot/            # RSS subscription commands
│   └── monitor-bot/        # Channel monitoring commands
├── core/                   # Core infrastructure
│   ├── App.js              # Main entry
│   ├── BotManager.js       # Manages bots
│   ├── StorageService.js   # PostgreSQL
│   └── TelegramService.js  # Userbot (MTProto)
└── providers/              # AI providers
```

## REST API

Full API documentation: [docs/api.md](docs/api.md)

**Quick start:**
```bash
# Add to .env
API_KEYS=myapikey:1

# Start app
npm start

# Test API
curl http://localhost:3001/health
curl -H "Authorization: Bearer myapikey" http://localhost:3001/api/ai/providers
```

**Key endpoints:**
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| POST | `/api/ai/chat` | Send message, get AI response |
| GET | `/api/rss/subscriptions` | List subscriptions |
| GET | `/api/monitor/sources` | List source channels |
| WS | `/ws/monitor` | Real-time message stream |

## Quick Deploy

### Step 1: Configure

```bash
cp .env.example .env
# Edit .env with your values
```

**Required:**
- `API_ID`, `API_HASH`, `TG_SESSION` - Telegram API credentials
- Bot tokens: `RSS_BOT_TOKEN`, `AI_BOT_TOKEN`, `MONITOR_BOT_TOKEN`

**Optional:**
- `API_KEYS` - For REST API access
- AI provider keys: `GROQ_API_KEY`, `GEMINI_API_KEY`, etc.

### Step 2: Run

```bash
docker compose up -d
docker compose logs -f
```

### Step 3: Verify

**Telegram:** Message your bot with `/start`

**REST API:**
```bash
curl http://localhost:3001/health
```

## GitHub Secrets (for CI/CD)

| Secret | Description |
|--------|-------------|
| `VPS_HOST` | VPS IP address |
| `VPS_USER` | SSH user |
| `VPS_SSH_KEY` | Private SSH key |
| `API_ID` | Telegram API ID |
| `API_HASH` | Telegram API Hash |
| `TG_SESSION` | Session string |
| `RSS_BOT_TOKEN` | RSS Bot token |
| `AI_BOT_TOKEN` | AI Bot token |
| `MONITOR_BOT_TOKEN` | Monitor Bot token |
| `WEBHOOK_URL` | HTTPS webhook URL |

## Adding a New Bot

1. Create `src/bots/your-bot/index.js`
2. Extend `BotInstance`
3. Create `src/services/YourService.js` for business logic
4. Register in `App.js`
5. Add `YOUR_BOT_TOKEN` to config

## License

MIT
