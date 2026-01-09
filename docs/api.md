# QuBot REST API Documentation

The REST API enables building alternative frontends (web UI, mobile app, CLI) while maintaining the same backend services used by Telegram bots.

## Base URL

```
http://localhost:10002
```

Default port is `10002`. Configure via `API_PORT` environment variable.

## Authentication

All `/api/*` endpoints require API key authentication.

**Header:**
```
Authorization: Bearer <API_KEY>
```

**Configuration:**
```bash
# .env
API_KEYS=myapikey:1,anotherapikey:2
```

Format: `key:userId` pairs, comma-separated. The userId is used for per-user data isolation.

---

## Endpoints Overview

### Health & Status

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/health` | ✅ | Service health check with status |

### Monitor

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/monitor/status` | ✅ | Get current monitor status |
| POST | `/api/monitor/start` | ✅ | Start the monitoring service |
| POST | `/api/monitor/stop` | ✅ | Stop the monitoring service |

### AI Chat

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/ai/providers` | ✅ | List available AI providers |
| GET | `/api/ai/models/{provider}` | ✅ | Get models for a specific provider |
| POST | `/api/ai/chat` | ✅ | Send message and get AI response |
| POST | `/api/ai/summarize` | ✅ | Summarize text content |

### RSS Subscriptions

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/rss/subscriptions` | ✅ | List user's RSS subscriptions |
| POST | `/api/rss/subscribe` | ✅ | Subscribe to a new RSS feed |
| DELETE | `/api/rss/unsubscribe/{id}` | ✅ | Unsubscribe from a feed |

---

## Detailed API Reference

### GET /api/health

Returns the current health status of all services.

**Request:**
```bash
curl http://localhost:10002/api/health \
  -H "Authorization: Bearer myapikey"
```

**Response:**
```json
{
  "status": "ok",
  "telegram": true,
  "ai_available": true,
  "monitor_running": false
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | Overall status (`ok` or `error`) |
| `telegram` | boolean | Telegram Telethon client connected |
| `ai_available` | boolean | At least one AI provider configured |
| `monitor_running` | boolean | Monitor service is active |

---

### GET /api/monitor/status

Get the current status of the channel monitoring service.

**Request:**
```bash
curl http://localhost:10002/api/monitor/status \
  -H "Authorization: Bearer myapikey"
```

**Response:**
```json
{
  "running": true,
  "sources": 5,
  "target": "-1001234567890"
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `running` | boolean | Whether monitoring is active |
| `sources` | integer | Number of source channels being monitored |
| `target` | string | Target channel ID for forwarding |

---

### POST /api/monitor/start

Start the channel monitoring service.

**Request:**
```bash
curl -X POST http://localhost:10002/api/monitor/start \
  -H "Authorization: Bearer myapikey"
```

**Response:**
```json
{"status": "started"}
```

---

### POST /api/monitor/stop

Stop the channel monitoring service.

**Request:**
```bash
curl -X POST http://localhost:10002/api/monitor/stop \
  -H "Authorization: Bearer myapikey"
```

**Response:**
```json
{"status": "stopped"}
```

---

### GET /api/ai/providers

List all available AI providers and their configuration status.

**Request:**
```bash
curl http://localhost:10002/api/ai/providers \
  -H "Authorization: Bearer myapikey"
```

**Response:**
```json
{
  "providers": [
    {"key": "groq", "name": "Groq", "configured": true},
    {"key": "gemini", "name": "Google Gemini", "configured": true},
    {"key": "openai", "name": "OpenAI", "configured": false},
    {"key": "claude", "name": "Anthropic Claude", "configured": false},
    {"key": "nvidia", "name": "NVIDIA NIM", "configured": false},
    {"key": "glm", "name": "GLM (zhipuai)", "configured": false},
    {"key": "minimax", "name": "MiniMax", "configured": false},
    {"key": "openrouter", "name": "OpenRouter", "configured": true}
  ]
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `providers` | array | List of provider objects |
| `providers[].key` | string | Provider identifier |
| `providers[].name` | string | Display name |
| `providers[].configured` | boolean | Whether API key is set |

---

### GET /api/ai/models/{provider}

Get available models for a specific AI provider.

**Request:**
```bash
curl http://localhost:10002/api/ai/models/groq \
  -H "Authorization: Bearer myapikey"
```

**Response:**
```json
{
  "provider": "groq",
  "models": [
    "llama-3.3-70b-versatile",
    "llama-3.1-70b-versatile",
    "mixtral-8x7b-32768",
    "gemma2-9b-it"
  ]
}
```

**URL Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `provider` | string | ✅ | Provider key (e.g., `groq`, `gemini`, `openai`) |

---

### POST /api/ai/chat

Send a message and get an AI response. Uses the user's configured provider and model.

**Request:**
```bash
curl -X POST http://localhost:10002/api/ai/chat \
  -H "Authorization: Bearer myapikey" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is quantum computing?",
    "system_prompt": "You are a helpful physics teacher."
  }'
```

**Request Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `message` | string | ✅ | User message to send |
| `provider` | string | ❌ | Override AI provider |
| `model` | string | ❌ | Override model name |
| `system_prompt` | string | ❌ | Custom system prompt |

**Response:**
```json
{
  "content": "Quantum computing is a type of computation that harnesses quantum mechanical phenomena like superposition and entanglement to process information in fundamentally different ways than classical computers...",
  "provider": "groq",
  "model": "llama-3.3-70b-versatile"
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `content` | string | AI-generated response |
| `provider` | string | Provider used for generation |
| `model` | string | Model used for generation |

**Error Responses:**

| Status | Description |
|--------|-------------|
| 503 | AI service not configured (no provider API keys set) |

---

### POST /api/ai/summarize

Summarize text content with configurable length and language.

**Request:**
```bash
curl -X POST http://localhost:10002/api/ai/summarize \
  -H "Authorization: Bearer myapikey" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "A very long article about technology trends...",
    "max_length": 200,
    "language": "en"
  }'
```

**Request Body:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `text` | string | ✅ | - | Text content to summarize |
| `max_length` | integer | ❌ | 200 | Maximum summary length in characters |
| `language` | string | ❌ | `en` | Output language: `en` (English) or `zh` (Chinese) |

**Response:**
```json
{
  "summary": "This article discusses emerging technology trends including AI, quantum computing, and sustainable tech. Key points include: increased AI adoption, breakthrough in quantum error correction, and green data center initiatives.",
  "language": "en"
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `summary` | string | Generated summary |
| `language` | string | Language of the summary |

---

### GET /api/rss/subscriptions

List all RSS subscriptions for the authenticated user.

**Request:**
```bash
curl http://localhost:10002/api/rss/subscriptions \
  -H "Authorization: Bearer myapikey"
```

**Response:**
```json
{
  "subscriptions": [
    {
      "id": 1,
      "url": "https://example.com/feed.xml",
      "title": "Example Blog",
      "chat_id": "123456789",
      "created_at": "2024-01-04T12:00:00Z"
    },
    {
      "id": 2,
      "url": "https://news.ycombinator.com/rss",
      "title": "Hacker News",
      "chat_id": "123456789",
      "created_at": "2024-01-05T08:30:00Z"
    }
  ]
}
```

---

### POST /api/rss/subscribe

Subscribe to a new RSS feed.

**Request:**
```bash
curl -X POST http://localhost:10002/api/rss/subscribe \
  -H "Authorization: Bearer myapikey" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/feed.xml",
    "chat_id": "123456789"
  }'
```

**Request Body:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `url` | string | ✅ | - | RSS/Atom feed URL |
| `chat_id` | string | ❌ | User's ID | Target chat for notifications |

**Response:**
```json
{
  "added": true,
  "title": "Example Blog",
  "url": "https://example.com/feed.xml"
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `added` | boolean | Whether subscription was created |
| `title` | string | Detected feed title |
| `url` | string | Feed URL |

**Error Responses:**

| Status | Description |
|--------|-------------|
| 400 | Invalid RSS URL or feed cannot be parsed |

---

### DELETE /api/rss/unsubscribe/{source_id}

Unsubscribe from an RSS feed.

**Request:**
```bash
curl -X DELETE http://localhost:10002/api/rss/unsubscribe/1 \
  -H "Authorization: Bearer myapikey"
```

**URL Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `source_id` | string | ✅ | Subscription ID to remove |

**Response:**
```json
{"removed": true}
```

**Error Responses:**

| Status | Description |
|--------|-------------|
| 404 | Subscription not found |

---

## Error Responses

All error responses follow this format:

```json
{
  "detail": "Error message"
}
```

**Common HTTP Status Codes:**

| Status | Meaning |
|--------|---------|
| 400 | Bad request (missing/invalid parameters) |
| 401 | Unauthorized (invalid or missing API key) |
| 404 | Resource not found |
| 503 | Service unavailable (e.g., AI not configured) |
| 500 | Internal server error |

---

## AI Service Methods

The AI service provides additional methods used internally by the application. These are not exposed as REST endpoints but document the full capability:

| Method | Description | Used By |
|--------|-------------|---------|
| `chat` | Interactive chat with history | Telegram AI Bot |
| `summarize` | Summarize text | Monitor reports, API |
| `translate` | Translate between languages | Job system |
| `categorize` | Classify text into categories | Content analysis |
| `get_sentiment` | Sentiment analysis | Message scoring |
| `analyze` | General-purpose analysis | Reports, insights |
| `run_job` | Execute a predefined AI job | Job catalog |

**Available AI Jobs:**

| Job ID | Description |
|--------|-------------|
| `chat` | General chat assistant |
| `summarize` | Text summarization |
| `translate` | Language translation |
| `categorize` | Text categorization |
| `sentiment` | Sentiment analysis |
| `chat_summary` | Conversation context summary |
| `chat_notes` | Structured knowledge extraction |
| `analysis` | Flexible analysis with custom format |

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `API_ENABLED` | `true` | Enable/disable REST API |
| `API_PORT` | `10002` | API server port |
| `API_KEYS` | - | API keys (format: `key:userId,...`) |
