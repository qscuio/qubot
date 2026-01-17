# AGENT.md

## Purpose
This document guides coding agents (including the Vibe Remote tool) to work
safely inside QuBot without breaking production flows. It emphasizes runtime
topology, data flows, lifecycle constraints, and the conventions that keep
the system stable.

## System Overview
QuBot is a multi-bot Telegram application composed of:
- Telethon userbots (MTProto) for high-throughput channel monitoring.
- Aiogram Bot API bots for command-driven features (AI, RSS, monitor control).
- FastAPI for REST endpoints and static hosting of the web UI / Mini Apps.
- PostgreSQL + Redis for persistence and caching (optional at runtime).
- A Vibe Remote subsystem that brokers CLI coding agents (Codex/Claude/Gemini).

## Runtime Topology (High Level)
- `app/main.py` (FastAPI lifespan) boot order:
  1) `db.connect()` (Postgres/Redis)
  2) `telegram_service.start()` (Telethon clients)
  3) `bot_dispatcher.start()` (Aiogram bots)
  4) Background services gated by feature flags
  5) Static mounts `/web` and `/miniapp`
- Shutdown reverses the order and stops long-running services first.

## Key Data Flows
### Channel Monitoring (Telethon)
- Telethon clients receive channel updates.
- `MonitorService` filters, deduplicates, and forwards to target channels.
- Message forwarding uses `telegram_service.main_client` only.
- Daily reports rely on `monitor_message_cache` in Postgres.

### Bot API Commands (Aiogram)
- Each bot is defined by a `BotSpec` in `app/bots/*/bot.py`.
- `bot_dispatcher` attaches routers and command lists.
- Webhook mode is automatic when `WEBHOOK_URL` is set.

### AI Chat
- `AiService` routes to providers (`app/providers/*`) based on settings.
- `AiStorage` persists chat history and settings in Postgres.
- AI jobs/prompts live in `app/services/ai/prompts.py`.

### Vibe Remote (Coding Agent Control)
- `app/services/vibe_remote/service.py` orchestrates CLI agents.
- `AgentRouter` resolves per-user or per-channel agent selection.
- `SessionManager` sets up per-user working directories.
- Git operations are performed via `GitOperations` (subprocess wrapper).
- GitHub Actions features use `GitHubActionsClient` (PyGithub, optional).

## Core Modules and Their Roles
- `app/core/config.py`: Single source of truth for environment configuration.
- `app/core/bot.py`: Telethon session lifecycle, forwarding, rate limits.
- `app/bots/dispatcher.py`: Aiogram app registry + webhook/polling setup.
- `app/services/monitor.py`: Monitoring pipeline, VIP/blacklist, reports.
- `app/services/rss.py`: RSS subscription + polling.
- `app/services/ai/`: Provider routing, storage, tools, and prompt jobs.
- `app/services/vibe_remote/`: CLI agents, session tracking, git/GHA ops.
- `app/api/routes.py`: REST API; `chart_router` always enabled.
- `app/core/security.py`: Rate limiting, scanner detection, iptables blocking.
- `app/core/database.py`: Postgres + Redis connection, schema initialization.
- `app/miniapps/chart/`: Stock chart Telegram Mini App (see Mini Apps section).

## Configuration Rules
- All settings are loaded via Pydantic in `app/core/config.py`.
- `TG_SESSIONS_JSON` is required for Telethon. It must be a single-line JSON
  array in secrets.
- Feature flags (`ENABLE_*`) gate services; respect them in new code.
- Optional integrations (DB, Redis, GitHub) must fail gracefully.
- If you add new env vars, update `README.md` and keep defaults safe.

## API & Web Contracts
- REST API routes live in `app/api/routes.py`.
- `/api/health` and `/api/*` endpoints are authenticated via API keys.
- `chart_router` is mounted unconditionally; do not remove it.
- The web UI uses `web/js/api.js`; verify any API changes against it and
  `docs/api.md` before shipping. Keep the web frontend and API in sync.
- Static hosting:
  - `/web` serves `web/`
  - `/miniapp` serves `app/miniapps/`

## Mini Apps Architecture

### Chart Mini App (`app/miniapps/chart/`)
A stock charting application for Telegram Mini Apps.

#### Technical Stack
- **No build step**: Vanilla ES6 modules, loaded directly by browser
- **Charting**: Lightweight Charts v4.1.0 (TradingView)
- **Telegram SDK**: `telegram-web-app.js` for Mini App integration
- **CSS**: Modular CSS with custom properties for theming

#### Directory Structure
```
app/miniapps/chart/
├── index.html              # Entry point, loads all CSS and main.js
├── css/
│   ├── variables.css       # Theme colors, spacing tokens
│   ├── base.css            # Reset, body, loading spinner
│   ├── layout.css          # Header, toolbar, panels, grid structure
│   ├── components.css      # Buttons, dropdowns, badges, search
│   └── responsive.css      # Mobile and landscape breakpoints
└── js/
    ├── main.js             # Init + event listener setup
    ├── core/               # Config, state, API, utilities
    ├── chart/              # Lightweight Charts wrappers, indicators
    ├── analysis/           # Chips, signals, tips, trend analysis
    ├── ui/                 # Header, toolbar, search, watchlist UI
    └── integrations/       # Telegram SDK, navigation, watchlist API
```

#### Design Decisions
- **Centralized State** (`js/core/state.js`): All app state in one object.
  Modify via `updateState()`. Series references kept in `mainSeries`/`subSeries`.
- **Authenticated Fetch** (`js/core/api.js`): All API calls use
  `authenticatedFetch()` which attaches `X-Telegram-Init-Data` header.
- **Modular CSS**: Each file has single responsibility. `layout.css` handles
  structure only; `components.css` handles individual element styles.
- **Header Layout**: Four rows (title, price, actions, stats), each centered.
  Uses `.header-row-*` classes in `layout.css`.
- **Mobile-First**: Search collapses to icon on mobile, expands on focus.
  Watchlist dropdown uses absolute positioning with high z-index.

#### API Endpoints
- `GET /api/chart/data/{code}?days=N&period=daily|weekly|monthly`
- `GET /api/chart/search?q={query}`
- `GET /api/chart/watchlist/list?user_id={id}`
- `POST /api/chart/watchlist/add` / `remove`

#### Debugging
- **Console**: All modules use `console.warn/error` for issues
- **URL params**: `?debug_user_id=123` bypasses Telegram for local testing
- **State inspection**: `window.state` not exposed; add temporarily if needed
- **Network**: Check `/api/chart/*` calls in DevTools Network tab
- **CSS issues**: Dropdowns require parent `overflow: visible`; check z-index
  hierarchy (header: 20, dropdowns: 100-1000)

#### Modification Guidelines
- **New UI component**: Add to `index.html` → style in `components.css` →
  logic in `js/ui/*.js` → wire events in `main.js`
- **New indicator**: Calculation in `indicators.js` → series ref in `state.js`
  → render in `chart-main.js` or `chart-sub.js`
- **New API call**: Use `authenticatedFetch()` from `js/core/api.js`

## Concurrency and Lifecycle Constraints
- Startup uses `asyncio.gather` for Telethon + Aiogram.
- Avoid blocking the event loop with sync IO.
  - Use `asyncio.to_thread` for heavy sync calls.
  - Use background tasks for long initializations.
- Telegram sending is rate-limited via `app/core/rate_limiter.py`.
- When adding services, provide `start()` and `stop()` hooks and register both
  in `app/main.py`.

## Database & Schema Notes
- `app/core/database.py` initializes most tables on connect.
- AI-specific tables are created in `AiStorage.ensure_tables()` (called by
  advanced AI services). If adding AI tables, update that path.
- Always add indexes for high-volume queries (monitor cache, history, RSS).

## Security & Access Control
- `SecurityMiddleware` enforces:
  - per-IP rate limits
  - suspicious path and user-agent blocking
  - optional iptables firewall blocking
- Telegram bot access is controlled by `ALLOWED_USERS`.
- When adding new entry points, reuse existing auth mechanisms and avoid
  bypassing them.

## Vibe Remote Safety Guidance
- CLI agents run external binaries; they can mutate files and run commands.
- `SessionManager` creates per-user workspaces under `VIBE_DEFAULT_CWD`.
  Do not change this behavior without validating user isolation.
- Git operations are performed through `GitOperations`; avoid direct `git`
  shelling unless needed for new capabilities.

## Change Safety Checklist
- Keep startup and shutdown symmetry in `app/main.py`.
- Preserve `chart_router` and static mount points.
- Register new bots in `app/bots/registry.py` and provide `BotSpec` commands.
- Keep async boundaries clean; no long sync work in handlers.
- When adding new API endpoints, update `docs/api.md` and ensure `web/js/api.js`
  still matches.
- Do not remove middleware (security, allowed users) or rate limiting.
- Make new services optional behind feature flags if they rely on external APIs.
- Prefer additive schema changes; keep migrations backwards compatible.

## Testing & Verification
- `pytest` is configured in `pyproject.toml` (unit/api/integration markers).
- Run at least unit tests after modifying service logic.
- For API changes, manually verify `/api/health`, `/api/ai/providers`, and
  any new endpoints.

## Deployment & Environment

### GitHub Actions CI/CD
Deployment is automated via `.github/workflows/deploy.yml`:

#### Workflow Triggers
- **Push to any branch**: Auto-deploys to configured VPS environments
- **Manual dispatch**: Select branch, force full setup, or force rebuild

#### Multi-Environment Matrix
Deploys to multiple VPS environments in parallel (e.g., CC, DMIT). Each
environment has its own secrets configured in GitHub repository settings.

#### Deployment Process
1. **Check enabled**: Skip if `DEPLOY_ENABLED` secret is not `true`
2. **Incremental detection**: Check `/opt/qubot/.deployed` marker
3. **First-time setup** (if needed):
   - Install Docker, Docker Compose, Git
   - Configure UFW firewall (80, 443, SSH)
   - Install Nginx and Certbot
   - Obtain SSL certificates via Let's Encrypt
   - Configure Nginx reverse proxy for webhook and web frontend
4. **Code deployment**:
   - Clone/pull to `/opt/qubot`
   - Checkout target branch
   - Export secrets as environment variables (not written to disk)
   - Write non-sensitive config to `.env`
   - Smart rebuild: only `--no-cache` if Dockerfile/requirements.txt changed
   - `docker compose up -d`
5. **Post-deploy**: Register Telegram webhooks via `scripts/setup_webhook.py`

#### Required Secrets (per environment)
```
# VPS Connection
VPS_HOST, VPS_USER, VPS_SSH_KEY, DEPLOY_ENABLED

# Telegram Bots
TG_SESSIONS_JSON, RSS_BOT_TOKEN, AI_BOT_TOKEN, CRAWLER_BOT_TOKEN, ...

# AI Providers
GROQ_API_KEY, GEMINI_API_KEY, OPENAI_API_KEY, CLAUDE_API_KEY, ...

# URLs & Config
WEBHOOK_URL, WEBFRONT_URL, BOT_PORT, BOT_SECRET, API_KEYS
```

#### Key Files
- `.github/workflows/deploy.yml` - Main deployment workflow
- `.github/workflows/test.yml` - Test workflow
- `docker-compose.yml` - Container orchestration
- `Dockerfile` - Application container
- `scripts/setup_webhook.py` - Telegram webhook registration

### Server Architecture
```
Internet → Nginx (SSL) → Docker Container (FastAPI :BOT_PORT)
                      ↘ /miniapp/* → Static files
                      ↘ /web/* → Static files
                      ↘ /api/* → REST API
                      ↘ /webhook/* → Telegram webhooks
```

### Mini App Configuration
- **Bot username**: `q_tty_crawler_bot`
- **Mini App short name**: `chart` (registered in BotFather)
- **Mini App URL**: `https://cweb.278141394.xyz/miniapp/chart/`
- **Deep link format**: `https://t.me/q_tty_crawler_bot/chart?startapp={code}`
- Mini Apps require HTTPS with valid SSL certificates

### Stock Link Generation
`app/core/stock_links.py` generates Mini App links. Fallback chain:
1. Cached bot username from `get_bot_username("crawler-bot")`
2. `WEBFRONT_URL` environment variable
3. External link (EastMoney)
