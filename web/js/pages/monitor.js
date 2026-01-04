/**
 * Monitor Page - Real-time channel monitoring
 */
class MonitorPage {
    constructor() {
        this.messages = [];
        this.isConnected = false;
        this.sources = null;
    }

    async render() {
        return `
            <div class="page" id="monitorPage">
                <aside class="page-sidebar">
                    <div class="page-header">
                        <span class="page-title">🔔 Sources</span>
                    </div>
                    <div class="card-body" id="monitorSources">
                        <div class="loading"><div class="spinner"></div></div>
                    </div>
                    <div class="card-footer">
                        <div class="input-group mb-md">
                            <input type="text" class="input" id="addSourceInput" 
                                placeholder="@channel or -100..."
                                onkeydown="if(event.key==='Enter') monitorPage.addSource()">
                        </div>
                        <button class="btn btn-primary" style="width: 100%" onclick="monitorPage.addSource()">
                            + Add Source
                        </button>
                    </div>
                </aside>
                <div class="page-content">
                    <div class="page-header">
                        <div class="flex items-center gap-md">
                            <span class="page-title">Live Stream</span>
                            <span class="status-dot ${this.isConnected ? 'connected' : ''}" id="streamStatus"></span>
                            <span class="text-sm text-muted" id="streamStatusText">
                                ${this.isConnected ? 'Connected' : 'Disconnected'}
                            </span>
                        </div>
                        <div class="flex gap-sm">
                            <button class="btn btn-primary" id="connectBtn" onclick="monitorPage.toggleConnection()">
                                ${this.isConnected ? '⏹️ Disconnect' : '▶️ Connect'}
                            </button>
                            <button class="btn btn-secondary" onclick="monitorPage.clearStream()">🗑️ Clear</button>
                        </div>
                    </div>
                    <div class="stream-container" id="streamContainer">
                        <div class="empty-state" id="streamEmpty">
                            <div class="empty-state-icon">🔔</div>
                            <div class="empty-state-title">No messages yet</div>
                            <div class="empty-state-text">Connect to start receiving real-time messages from monitored channels.</div>
                            <button class="btn btn-primary mt-md" onclick="monitorPage.toggleConnection()">▶️ Connect</button>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    async init() {
        await this.loadSources();
        await this.loadHistory();
    }

    async loadSources() {
        const container = document.getElementById('monitorSources');

        try {
            this.sources = await api.getMonitorSources();
            this.renderSources();
        } catch (err) {
            container.innerHTML = `
                <div class="text-muted text-sm">Failed to load sources</div>
            `;
        }
    }

    renderSources() {
        const container = document.getElementById('monitorSources');

        if (!this.sources?.channels?.length) {
            container.innerHTML = `
                <div class="text-muted text-sm">No sources configured</div>
            `;
            return;
        }

        container.innerHTML = `
            <div class="mb-md">
                <div class="text-sm text-muted mb-sm">Channels (${this.sources.channels.length})</div>
                ${this.sources.channels.map(ch => `
                    <div class="chat-item flex justify-between items-center">
                        <span>${this.escapeHtml(String(ch))}</span>
                        <button class="btn btn-icon" onclick="monitorPage.removeSource('${ch}')">✕</button>
                    </div>
                `).join('')}
            </div>
            ${this.sources.keywords?.length ? `
                <div class="mb-md">
                    <div class="text-sm text-muted mb-sm">Keywords</div>
                    <div class="text-sm">${this.sources.keywords.join(', ')}</div>
                </div>
            ` : ''}
            <div class="text-sm text-muted">
                Target: ${this.sources.targetChannel || 'Not set'}
            </div>
        `;
    }

    async addSource() {
        const input = document.getElementById('addSourceInput');
        const channelId = input.value.trim();

        if (!channelId) return;

        try {
            await api.addMonitorSource(channelId);
            Toast.success(`Added: ${channelId}`);
            input.value = '';
            await this.loadSources();
        } catch (err) {
            Toast.error(`Failed: ${err.message}`);
        }
    }

    async removeSource(channelId) {
        try {
            await api.removeMonitorSource(channelId);
            Toast.success('Source removed');
            await this.loadSources();
        } catch (err) {
            Toast.error('Failed to remove source');
        }
    }

    async loadHistory() {
        try {
            const data = await api.getMonitorHistory(20);
            if (data.length > 0) {
                this.messages = data.map(m => ({
                    source: m.source,
                    text: m.message,
                    timestamp: m.created_at
                })).reverse();
                this.renderStream();
            }
        } catch (err) {
            console.log('No history available');
        }
    }

    toggleConnection() {
        if (this.isConnected) {
            this.disconnect();
        } else {
            this.connect();
        }
    }

    connect() {
        api.connectWebSocket(
            (data) => this.onMessage(data),
            (status) => this.onStatusChange(status)
        );
    }

    disconnect() {
        api.disconnectWebSocket();
        this.onStatusChange('disconnected');
    }

    onMessage(data) {
        if (data.type === 'message') {
            this.messages.push({
                source: data.data.source,
                text: data.data.text,
                timestamp: data.data.timestamp || new Date().toISOString()
            });

            // Keep last 100 messages
            if (this.messages.length > 100) {
                this.messages.shift();
            }

            this.renderStream();
            this.scrollToBottom();
        }
    }

    onStatusChange(status) {
        this.isConnected = status === 'connected';

        const dot = document.getElementById('streamStatus');
        const text = document.getElementById('streamStatusText');
        const btn = document.getElementById('connectBtn');

        if (dot) {
            dot.className = `status-dot ${this.isConnected ? 'connected' : status === 'error' ? 'error' : ''}`;
        }
        if (text) {
            text.textContent = status === 'connected' ? 'Connected' : status === 'error' ? 'Error' : 'Disconnected';
        }
        if (btn) {
            btn.innerHTML = this.isConnected ? '⏹️ Disconnect' : '▶️ Connect';
        }

        // Update header status
        if (window.app?.header) {
            window.app.header.setStatus(status);
        }
    }

    renderStream() {
        const container = document.getElementById('streamContainer');

        if (this.messages.length === 0) {
            container.innerHTML = `
                <div class="empty-state" id="streamEmpty">
                    <div class="empty-state-icon">🔔</div>
                    <div class="empty-state-title">No messages yet</div>
                    <div class="empty-state-text">Connect to start receiving real-time messages.</div>
                </div>
            `;
            return;
        }

        container.innerHTML = this.messages.map(msg => `
            <div class="stream-message">
                <div class="stream-message-header">
                    <span class="stream-message-source">📢 ${this.escapeHtml(msg.source)}</span>
                    <span class="stream-message-time">${this.formatTime(msg.timestamp)}</span>
                </div>
                <div class="stream-message-content">${this.escapeHtml(msg.text)}</div>
            </div>
        `).join('');
    }

    scrollToBottom() {
        const container = document.getElementById('streamContainer');
        if (container) {
            container.scrollTop = container.scrollHeight;
        }
    }

    clearStream() {
        this.messages = [];
        this.renderStream();
    }

    formatTime(timestamp) {
        if (!timestamp) return '';
        const date = new Date(timestamp);
        return date.toLocaleTimeString();
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text || '';
        return div.innerHTML;
    }

    destroy() {
        this.disconnect();
    }
}

window.monitorPage = new MonitorPage();
