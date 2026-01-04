# QuBot - Multi-Bot Telegram Application

A professional, plugin-based Telegram application with a flexible multi-bot architecture supporting 1 Userbot + N Bot API bots.

## Features

- 🤖 **Multi-Bot Architecture** - 1 Userbot (MTProto) + unlimited Bot API bots
- 📡 **Channel Monitoring** - Real-time Telegram channel monitoring
- 📰 **RSS Subscription** - Subscribe to RSS feeds via bot commands
- 🧠 **AI Chat** - Multi-provider AI support (Groq, Gemini, OpenAI, Claude, NVIDIA)
- 📚 **16 Default RSS Sources** - BBC, Guardian, Hacker News, TechCrunch, etc.
- � **Webhook Mode** - Nginx reverse proxy with Let's Encrypt SSL
- 💾 **PostgreSQL Storage** - Persistent subscription data
- 🐳 **Dockerized** - Easy deployment with Docker Compose
- 🚀 **GitHub Actions** - Automated deployment to VPS

## Default Bots

### 📰 RSS Bot
| Command | Description |
|---------|-------------|
| `/sub <url>` | Subscribe to RSS feed |
| `/unsub <id>` | Unsubscribe |
| `/list` | List subscriptions |
| `/check` | Check status |

**Token:** `RSS_BOT_TOKEN`

### 🧠 AI Bot (Coming Soon)
| Command | Description |
|---------|-------------|
| `/ai <text>` | Ask AI |
| `/providers` | Select provider |
| `/models` | Select model |

**Token:** `AI_BOT_TOKEN`

## Quick Deploy

### Step 1: SSH Key Setup (on VPS)

```bash
ssh-keygen -t ed25519 -C "github-actions" -f ~/.ssh/github_actions
cat ~/.ssh/github_actions.pub >> ~/.ssh/authorized_keys
cat ~/.ssh/github_actions  # Copy to VPS_SSH_KEY secret
```

### Step 2: DNS Record

Point a domain to your VPS:

| Type | Name | Value |
|------|------|-------|
| A | bot | Your VPS IP |

Your `WEBHOOK_URL` will be `https://bot.yourdomain.com`

> ⚠️ **Cloudflare**: Use DNS-only mode (gray cloud) for Let's Encrypt.

### Step 3: Create Telegram Bots

Create bots from [@BotFather](https://t.me/BotFather):
1. **RSS Bot** - `/newbot` → copy token
2. **AI Bot** - `/newbot` → copy token

### Step 4: Get API Credentials

1. Go to [my.telegram.org](https://my.telegram.org)
2. Create app → copy `API_ID` and `API_HASH`

### Step 5: Generate Session

```bash
git clone git@github.com:your-username/qubot.git
cd qubot && npm install
npm run generate-session
```

### Step 6: Configure GitHub Secrets

**VPS:**
| Secret | Value |
|--------|-------|
| `VPS_HOST` | VPS IP |
| `VPS_USER` | SSH user |
| `VPS_SSH_KEY` | Private key |

**Telegram API:**
| Secret | Value |
|--------|-------|
| `API_ID` | API ID |
| `API_HASH` | API Hash |
| `TG_SESSION` | Session string |

**Bot Tokens:**
| Secret | Value |
|--------|-------|
| `RSS_BOT_TOKEN` | RSS Bot token |
| `AI_BOT_TOKEN` | AI Bot token |

**Webhook (for HTTPS mode):**

> All bots share ONE webhook server on `BOT_PORT`. Each bot has its own path: `/webhook/rss-bot`, `/webhook/ai-bot`

| Secret | Description | Example |
|--------|-------------|---------|
| `WEBHOOK_URL` | Your domain with HTTPS | `https://bot.yourdomain.com` |
| `BOT_PORT` | Express server port | `3000` |
| `BOT_SECRET` | Webhook security token | Random string |

**Monitoring:**
| Secret | Value |
|--------|-------|
| `SOURCE_CHANNELS` | Channels to monitor |
| `TARGET_CHANNEL` | Output channel |
| `KEYWORDS` | Filter keywords |

**AI Keys (optional):**
| Secret | Value |
|--------|-------|
| `GROQ_API_KEY` | Groq key |
| `GEMINI_API_KEY` | Gemini key |
| `OPENAI_API_KEY` | OpenAI key |
| `CLAUDE_API_KEY` | Claude key |

### Step 7: Deploy

Push to `main` or run workflow manually.

The workflow:
- ✅ Installs Docker & Nginx
- ✅ Obtains SSL certificate
- ✅ Deploys with Docker Compose
- ✅ Registers webhooks

### Step 8: Verify

```bash
ssh your-vps
cd /opt/qubot
docker compose logs -f
```

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        BotManager                            │
├──────────────────┬───────────────────────────────────────────┤
│   Userbot        │           Bot API Bots                    │
│   (MTProto)      │   ┌──────────┐   ┌──────────┐             │
│   - Monitoring   │   │ RSS Bot  │   │ AI Bot   │             │
│   - Forwarding   │   │ /sub     │   │ /ai      │             │
└──────────────────┴───────────────────────────────────────────┘
          │                    │
          ▼                    ▼
    ┌──────────────────────────────────┐
    │     WebhookServer (Express)      │
    │     /health, /webhook/:botName   │
    └──────────────────────────────────┘
          │
          ▼
    ┌──────────────────────────────────┐
    │     Nginx + Let's Encrypt SSL    │
    └──────────────────────────────────┘
```

```
src/
├── core/
│   ├── App.js              # Main entry
│   ├── BotManager.js       # Manages bots
│   ├── BotInstance.js      # Bot base class
│   ├── WebhookServer.js    # Express server
│   ├── TelegramService.js  # Userbot
│   └── StorageService.js   # PostgreSQL
├── bots/
│   ├── rss-bot/            # RSS Bot
│   └── ai-bot/             # AI Bot
└── features/
    ├── channel-monitor/    # Userbot feature
    └── rss/                # Default sources
```

## Adding a New Bot

1. Create `src/bots/your-bot/index.js`
2. Extend `BotInstance`
3. Register in `App.js`
4. Add `YOUR_BOT_TOKEN` to secrets

## Local Development

```bash
cp .env.example .env  # Edit values
docker compose up -d
docker compose logs -f
```

## License

MIT
