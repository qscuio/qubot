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

## Historical Notes
### Mini App Link Issue (2026-01-13)
Problem:
"Bot application not found" when clicking stock list links in Telegram.

Root Cause:
`get_chart_url()` in `app/core/stock_links.py` uses a cached bot username from
`get_bot_username("crawler-bot")`. If the username is not cached yet, it falls
back to `WEBFRONT_URL`, and then to EastMoney if `WEBFRONT_URL` is missing.

BotFather Configuration:
- Bot username: `q_tty_crawler_bot`
- Mini App short name: `chart`
- Mini App URL: `https://cweb.278141394.xyz/miniapp/chart/`
- Direct link format: `https://t.me/q_tty_crawler_bot/chart?startapp={code}`

Solution:
Since the bot username is known and static, add it as a configuration option
or hardcode the fallback to ensure Mini App links work correctly.

Files Modified:
- `app/core/stock_links.py` - Fixed Mini App link generation

### Deployment Notes
- The bot is deployed on a remote VPS.
- Mini Apps require HTTPS with valid SSL certificates.
- The `chart` Mini App short name must be registered in BotFather.
