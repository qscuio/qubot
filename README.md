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

### Required Secrets

| Secret | Description | Example |
|--------|-------------|---------|
| **VPS** | | |
| `VPS_HOST` | VPS IP address | `123.45.67.89` |
| `VPS_USER` | SSH user | `root` |
| `VPS_SSH_KEY` | Private SSH key | `-----BEGIN OPENSSH...` |
| **Telegram API** | | |
| `API_ID` | Telegram API ID | `12345678` |
| `API_HASH` | Telegram API Hash | `abc123...` |
| `TG_SESSION` | Session string | `1BVtsOH...` |
| **Bot Tokens** | | |
| `RSS_BOT_TOKEN` | RSS Bot token | `123:ABC...` |
| `AI_BOT_TOKEN` | AI Bot token | `456:DEF...` |
| `MONITOR_BOT_TOKEN` | Monitor Bot token | `789:GHI...` |

### Webhook & Web Frontend

| Secret | Description | Example |
|--------|-------------|---------|
| `WEBHOOK_URL` | Bot webhook domain | `https://bot.yourdomain.com` |
| `WEBFRONT_URL` | Web frontend domain | `https://app.yourdomain.com` |
| `BOT_PORT` | Webhook server port | `3000` |
| `BOT_SECRET` | Webhook security token | Random string |
| `API_PORT` | REST API server port | `3001` |
| `API_KEYS` | API keys (key:userId,...) | `mykey:1,otherkey:2` |

### AI Providers (Optional)

| Secret | Description |
|--------|-------------|
| `GROQ_API_KEY` | Groq API key |
| `GEMINI_API_KEY` | Google Gemini API key |
| `OPENAI_API_KEY` | OpenAI API key |
| `CLAUDE_API_KEY` | Anthropic Claude key |
| `NVIDIA_API_KEY` | NVIDIA NIM key |

### Monitoring (Optional)

| Secret | Description | Example |
|--------|-------------|---------|
| `SOURCE_CHANNELS` | Channels to monitor | `@channel1,@channel2` |
| `TARGET_CHANNEL` | Forward destination | `@mychannel` |
| `KEYWORDS` | Filter keywords | `bitcoin,crypto` |
| `FROM_USERS` | Filter by usernames | `@user1,@user2` |

### Other

| Secret | Description |
|--------|-------------|
| `NOTES_REPO` | GitHub repo for exports |
| `LOG_LEVEL` | `debug`, `info`, `warn`, `error` |

---

## Debugging

### Check Service Status
```bash
# SSH to VPS
ssh your-vps
cd /opt/qubot

# Container status
docker compose ps

# View logs
docker compose logs -f
docker compose logs userbot --tail 100

# Check specific service
docker compose logs userbot 2>&1 | grep -i error
```

### Check API Server
```bash
# On VPS - is port 3001 listening?
curl http://localhost:3001/health

# From outside - through Nginx
curl https://app.yourdomain.com/health
```

### Check Nginx
```bash
# Test Nginx config
sudo nginx -t

# View Nginx logs
sudo tail -f /var/log/nginx/error.log

# Check sites enabled
ls -la /etc/nginx/sites-enabled/
```

### Common Issues

| Issue | Solution |
|-------|----------|
| **502 Bad Gateway** | API server not running. Check `docker compose logs` |
| **Connection refused** | Port not open. Run `ufw allow 3001` |
| **Unauthorized** | Check `API_KEYS` in .env matches your request |
| **WebSocket fails** | Check Nginx has `proxy_set_header Upgrade` |

### Restart Services
```bash
cd /opt/qubot
docker compose down
docker compose up -d --build
docker compose logs -f
```

---

## Adding a New Bot

1. Create `src/bots/your-bot/index.js`
2. Extend `BotInstance`
3. Create `src/services/YourService.js` for business logic
4. Register in `App.js`
5. Add `YOUR_BOT_TOKEN` to GitHub Secrets

## License

MIT
