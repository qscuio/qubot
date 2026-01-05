# QuBot REST API Documentation

The REST API enables building alternative frontends (web UI, mobile app, CLI) while maintaining the same backend services used by Telegram bots.

## Base URL

```
http://localhost:3001
```

Default port is `3001`. Configure via `API_PORT` environment variable.

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

## Endpoints

### Health & Status

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/health` | ❌ | Health check |
| GET | `/api/status` | ✅ | System status |

#### GET /health
```bash
curl http://localhost:3001/health
```
```json
{
  "status": "ok",
  "timestamp": "2024-01-04T12:00:00Z",
  "services": { "ai": true, "rss": true, "monitor": true }
}
```

---

### AI Chat

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/ai/settings` | Get AI settings |
| PUT | `/api/ai/settings` | Update provider/model |
| GET | `/api/ai/providers` | List AI providers |
| GET | `/api/ai/models` | Get models for current provider |
| POST | `/api/ai/chat` | Send message, get response |
| POST | `/api/ai/chat/stream` | Stream response via SSE |
| GET | `/api/ai/chats` | List chat sessions |
| POST | `/api/ai/chats` | Create new chat |
| GET | `/api/ai/chats/:id` | Get chat with messages |
| PUT | `/api/ai/chats/:id` | Switch/rename chat |
| DELETE | `/api/ai/chats/:id/messages` | Clear chat history |
| POST | `/api/ai/chats/:id/export` | Export to markdown |

#### POST /api/ai/chat
```bash
curl -X POST http://localhost:3001/api/ai/chat \
  -H "Authorization: Bearer myapikey" \
  -H "Content-Type: application/json" \
  -d '{"message": "What is quantum computing?"}'
```
```json
{
  "content": "Quantum computing is...",
  "thinking": null,
  "chatId": 5,
  "provider": "groq",
  "model": "llama3-70b-8192"
}
```

#### POST /api/ai/chat/stream
Server-Sent Events (SSE) stream of response chunks.
```bash
curl -N -X POST http://localhost:3001/api/ai/chat/stream \
  -H "Authorization: Bearer myapikey" \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello"}'
```

Example events:
```
event: meta
data: {"chatId":5,"provider":"groq","model":"llama-3.3-70b-versatile"}

event: chunk
data: {"token":"Hello"}

event: done
data: {"content":"Hello there!"}
```

#### GET /api/ai/providers
```bash
curl http://localhost:3001/api/ai/providers \
  -H "Authorization: Bearer myapikey"
```
```json
{
  "providers": [
    { "key": "groq", "name": "Groq", "configured": true },
    { "key": "gemini", "name": "Google Gemini", "configured": false }
  ]
}
```

`/api/ai/models` also accepts an optional `provider` query to preview models before switching providers.

---

### RSS Subscriptions

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/rss/subscriptions` | List subscriptions |
| POST | `/api/rss/subscriptions` | Subscribe to feed |
| DELETE | `/api/rss/subscriptions/:id` | Unsubscribe |
| POST | `/api/rss/validate` | Validate RSS URL |

#### POST /api/rss/subscriptions
```bash
curl -X POST http://localhost:3001/api/rss/subscriptions \
  -H "Authorization: Bearer myapikey" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/feed.xml"}'
```
```json
{
  "added": true,
  "title": "Example Blog",
  "url": "https://example.com/feed.xml"
}
```

---

### Channel Monitor

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/monitor/sources` | List source channels |
| POST | `/api/monitor/sources` | Add source channel |
| DELETE | `/api/monitor/sources/:id` | Remove source |
| GET | `/api/monitor/filters` | Get user's filter policies |
| PUT | `/api/monitor/filters` | Update filter policies |
| GET | `/api/monitor/history` | Get forwarded messages |
| POST | `/api/monitor/start` | Start monitoring |
| POST | `/api/monitor/stop` | Stop monitoring |

#### POST /api/monitor/sources
```bash
curl -X POST http://localhost:3001/api/monitor/sources \
  -H "Authorization: Bearer myapikey" \
  -H "Content-Type: application/json" \
  -d '{"channelId": "@channel_name"}'
```

#### PUT /api/monitor/filters
```bash
curl -X PUT http://localhost:3001/api/monitor/filters \
  -H "Authorization: Bearer myapikey" \
  -H "Content-Type: application/json" \
  -d '{
    "channels": ["@channel1"],
    "keywords": ["bitcoin", "crypto"],
    "users": [],
    "enabled": true
  }'
```

---

## WebSocket

Real-time message streaming from monitored channels.

**Connection:**
```
ws://localhost:3001/ws/monitor?token=<API_KEY>
```

**Received messages:**
```json
{
  "type": "message",
  "data": {
    "id": 12345,
    "text": "Message content...",
    "source": "@channel_name",
    "sourceId": "-1001234567890",
    "timestamp": "2024-01-04T12:00:00Z"
  }
}
```

**Send to update filters:**
```json
{
  "type": "update_filters",
  "filters": {
    "keywords": ["important"],
    "enabled": true
  }
}
```

---

## Error Responses

```json
{
  "error": "Error type",
  "message": "Detailed error message"
}
```

| Status | Meaning |
|--------|---------|
| 400 | Bad request (missing/invalid params) |
| 401 | Unauthorized (invalid/missing API key) |
| 404 | Not found |
| 500 | Internal server error |

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `API_ENABLED` | `true` | Enable/disable API |
| `API_PORT` | `3001` | API server port |
| `API_KEYS` | - | API keys (format: `key:userId,...`) |
