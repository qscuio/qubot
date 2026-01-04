/**
 * QuBot API Client
 * Handles all REST API and WebSocket communication.
 */
class ApiClient {
    constructor() {
        const isFile = window.location.protocol === 'file:' || window.location.origin === 'null';
        const defaultBaseUrl = isFile ? 'http://localhost:3001' : window.location.origin;
        this.baseUrl = window.QUBOT_API_BASE || defaultBaseUrl;
        this.apiKey = localStorage.getItem('qubot_api_key') || '';
        this.ws = null;
        this.wsCallbacks = new Map();
    }

    setApiKey(key) {
        this.apiKey = key;
        localStorage.setItem('qubot_api_key', key);
    }

    getApiKey() {
        return this.apiKey;
    }

    async request(endpoint, options = {}) {
        const url = `${this.baseUrl}${endpoint}`;
        const headers = {
            'Content-Type': 'application/json',
            ...options.headers
        };

        if (this.apiKey) {
            headers['Authorization'] = `Bearer ${this.apiKey}`;
        }

        try {
            const response = await fetch(url, {
                ...options,
                headers
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.message || data.error || 'Request failed');
            }

            return data;
        } catch (err) {
            console.error('API Error:', err);
            throw err;
        }
    }

    // Health & Status
    async getHealth() {
        return this.request('/health');
    }

    async getStatus() {
        return this.request('/api/status');
    }

    // AI Endpoints
    async getAiSettings() {
        return this.request('/api/ai/settings');
    }

    async updateAiSettings(provider, model) {
        return this.request('/api/ai/settings', {
            method: 'PUT',
            body: JSON.stringify({ provider, model })
        });
    }

    async getProviders() {
        return this.request('/api/ai/providers');
    }

    async getModels(provider) {
        const query = provider ? `?provider=${encodeURIComponent(provider)}` : "";
        return this.request(`/api/ai/models${query}`);
    }

    async sendMessage(message, chatId = null) {
        return this.request('/api/ai/chat', {
            method: 'POST',
            body: JSON.stringify({ message, chatId })
        });
    }

    async sendMessageStream(message, chatId = null, handlers = {}) {
        const url = `${this.baseUrl}/api/ai/chat/stream`;
        const headers = {
            'Content-Type': 'application/json'
        };

        if (this.apiKey) {
            headers['Authorization'] = `Bearer ${this.apiKey}`;
        }

        const response = await fetch(url, {
            method: 'POST',
            headers,
            body: JSON.stringify({ message, chatId })
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(errorText || 'Stream request failed');
        }

        if (!response.body) {
            throw new Error('Streaming not supported by the browser');
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        const result = { content: '', chatId: null, provider: null, model: null };

        const parseEvent = (chunk) => {
            const lines = chunk.split('\n');
            let event = 'message';
            const dataLines = [];
            for (const line of lines) {
                if (line.startsWith('event:')) {
                    event = line.slice(6).trim();
                } else if (line.startsWith('data:')) {
                    dataLines.push(line.slice(5).trim());
                }
            }
            if (!dataLines.length) return null;
            const dataText = dataLines.join('\n');
            let data = dataText;
            try {
                data = JSON.parse(dataText);
            } catch (err) {
                data = dataText;
            }
            return { event, data };
        };

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const parts = buffer.split('\n\n');
            buffer = parts.pop() || '';

            for (const part of parts) {
                const parsed = parseEvent(part.trim());
                if (!parsed) continue;

                if (parsed.event === 'meta') {
                    Object.assign(result, parsed.data || {});
                    handlers.onMeta?.(parsed.data);
                } else if (parsed.event === 'chunk') {
                    const token = parsed.data?.token ?? parsed.data;
                    result.content += token || '';
                    handlers.onChunk?.(token || '');
                } else if (parsed.event === 'done') {
                    if (parsed.data?.content) {
                        result.content = parsed.data.content;
                    }
                    handlers.onDone?.(parsed.data);
                } else if (parsed.event === 'error') {
                    const message = parsed.data?.error || 'Stream error';
                    handlers.onError?.(message);
                    throw new Error(message);
                }
            }
        }

        return result;
    }

    async getChats(limit = 20) {
        return this.request(`/api/ai/chats?limit=${limit}`);
    }

    async createChat() {
        return this.request('/api/ai/chats', { method: 'POST' });
    }

    async getChat(chatId, messageLimit = 50) {
        return this.request(`/api/ai/chats/${chatId}?limit=${messageLimit}`);
    }

    async switchChat(chatId) {
        return this.request(`/api/ai/chats/${chatId}`, { method: 'PUT' });
    }

    async clearChat(chatId) {
        return this.request(`/api/ai/chats/${chatId}/messages`, { method: 'DELETE' });
    }

    async exportChat(chatId) {
        return this.request(`/api/ai/chats/${chatId}/export`, { method: 'POST' });
    }

    // RSS Endpoints
    async getRssSubscriptions() {
        return this.request('/api/rss/subscriptions');
    }

    async addRssSubscription(url) {
        return this.request('/api/rss/subscriptions', {
            method: 'POST',
            body: JSON.stringify({ url })
        });
    }

    async removeRssSubscription(id) {
        return this.request(`/api/rss/subscriptions/${id}`, { method: 'DELETE' });
    }

    async validateRssFeed(url) {
        return this.request('/api/rss/validate', {
            method: 'POST',
            body: JSON.stringify({ url })
        });
    }

    // Monitor Endpoints
    async getMonitorSources() {
        return this.request('/api/monitor/sources');
    }

    async addMonitorSource(channelId) {
        return this.request('/api/monitor/sources', {
            method: 'POST',
            body: JSON.stringify({ channelId })
        });
    }

    async removeMonitorSource(channelId) {
        return this.request(`/api/monitor/sources/${encodeURIComponent(channelId)}`, {
            method: 'DELETE'
        });
    }

    async getMonitorFilters() {
        return this.request('/api/monitor/filters');
    }

    async updateMonitorFilters(filters) {
        return this.request('/api/monitor/filters', {
            method: 'PUT',
            body: JSON.stringify(filters)
        });
    }

    async getMonitorHistory(limit = 50) {
        return this.request(`/api/monitor/history?limit=${limit}`);
    }

    async startMonitor() {
        return this.request('/api/monitor/start', { method: 'POST' });
    }

    async stopMonitor() {
        return this.request('/api/monitor/stop', { method: 'POST' });
    }

    // WebSocket
    connectWebSocket(onMessage, onStatusChange) {
        if (this.ws) {
            this.ws.close();
        }

        const wsUrl = `${this.baseUrl.replace('http', 'ws')}/ws/monitor?token=${this.apiKey}`;

        try {
            this.ws = new WebSocket(wsUrl);

            this.ws.onopen = () => {
                console.log('WebSocket connected');
                onStatusChange?.('connected');
            };

            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    onMessage?.(data);
                } catch (err) {
                    console.error('WS parse error:', err);
                }
            };

            this.ws.onclose = () => {
                console.log('WebSocket disconnected');
                onStatusChange?.('disconnected');
            };

            this.ws.onerror = (err) => {
                console.error('WebSocket error:', err);
                onStatusChange?.('error');
            };
        } catch (err) {
            console.error('WebSocket connection failed:', err);
            onStatusChange?.('error');
        }
    }

    disconnectWebSocket() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }

    sendWebSocketMessage(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
        }
    }
}

// Global instance
window.api = new ApiClient();
