/**
 * AI Chat Page
 */
class ChatPage {
    constructor() {
        this.chats = [];
        this.currentChatId = null;
        this.messages = [];
        this.isLoading = false;
        this.settings = null;
        this.providers = [];
        this.models = [];
        this.searchQuery = '';
        this.streamQueue = [];
        this.streamTimer = null;
        this.streamActive = false;
        this.streamContent = '';
        this.streamFinalContent = '';
        this.streamTarget = null;
        this.streamDoneResolver = null;
        this.streamDonePromise = null;
        this.pendingChatRefresh = false;
    }

    async render() {
        return `
            <div class="page page-chat" id="chatPage">
                <aside class="page-sidebar chat-sidebar">
                    <div class="page-header chat-sidebar-header">
                        <span class="page-title">Chats</span>
                        <button class="btn btn-primary btn-compact" onclick="chatPage.newChat()">New chat</button>
                    </div>
                    <div class="chat-search">
                        <input type="search" class="input chat-search-input" id="chatSearch"
                            placeholder="Search chats..."
                            oninput="chatPage.onSearchChange(event)">
                    </div>
                    <div class="chat-list" id="chatList">
                        <div class="loading"><div class="spinner"></div></div>
                    </div>
                </aside>
                <div class="page-content">
                    <div class="page-header chat-topbar">
                        <div class="chat-title-wrap">
                            <span class="page-title" id="chatTitle">New Chat</span>
                            <div class="chat-subtitle">
                                <span class="text-muted text-sm">Provider</span>
                                <select class="input input-select" id="providerSelect" onchange="chatPage.onProviderChange()">
                                    <option value="">Loading...</option>
                                </select>
                            </div>
                        </div>
                        <div class="chat-actions">
                            <button class="btn btn-secondary" onclick="chatPage.exportChat()">Export</button>
                            <button class="btn btn-secondary" onclick="chatPage.clearChat()">Clear</button>
                        </div>
                    </div>
                    <div class="chat-models">
                        <div class="model-label text-sm text-muted">Models</div>
                        <div class="model-chips" id="modelChips">
                            <span class="model-chip muted">Loading...</span>
                        </div>
                    </div>
                    <div class="messages" id="messageList">
                        <div class="empty-state" id="emptyChat">
                            <div class="empty-state-icon">💬</div>
                            <div class="empty-state-title">Start a conversation</div>
                            <div class="empty-state-text">Send a message to begin chatting with AI.</div>
                        </div>
                    </div>
                    <div class="chat-input-area">
                        <div class="chat-input-wrapper">
                            <textarea class="chat-input" id="chatInput" 
                                placeholder="Type your message..." 
                                rows="1"
                                onkeydown="chatPage.onKeyDown(event)"></textarea>
                            <button class="send-btn" id="sendBtn" onclick="chatPage.sendMessage()">➤</button>
                        </div>
                        <div class="chat-hint">Enter to send. Shift + Enter for a new line.</div>
                    </div>
                </div>
            </div>
        `;
    }

    async init() {
        await Promise.all([
            this.loadChats(),
            this.loadSettings()
        ]);
        this.autoResizeTextarea();
        const searchInput = document.getElementById('chatSearch');
        if (searchInput) {
            searchInput.value = this.searchQuery;
        }
    }

    async loadSettings() {
        try {
            const [settings, providersData] = await Promise.all([
                api.getAiSettings(),
                api.getProviders()
            ]);
            this.settings = settings;
            this.providers = providersData.providers || [];

            const select = document.getElementById('providerSelect');
            select.innerHTML = this.providers.map(p =>
                `<option value="${p.key}" ${p.key === settings.provider ? 'selected' : ''} ${!p.configured ? 'disabled' : ''}>
                    ${p.name}${!p.configured ? ' ⚠️' : ''}
                </option>`
            ).join('');

            await this.loadModels(settings.provider, settings.model);
        } catch (err) {
            console.error('Failed to load settings:', err);
        }
    }

    async onProviderChange() {
        const select = document.getElementById('providerSelect');
        const provider = select.value;
        if (!provider) return;
        try {
            const modelsData = await api.getModels(provider);
            this.models = modelsData.models || [];
            const nextModel = this.pickModel(this.models, this.settings?.model);
            const updated = await api.updateAiSettings(provider, nextModel);
            this.settings = { ...this.settings, ...updated };
            this.renderModelChips();
            Toast.success(`Switched to ${provider}`);
        } catch (err) {
            Toast.error('Failed to switch provider');
        }
    }

    async loadModels(provider, preferredModel) {
        const chips = document.getElementById('modelChips');
        if (chips) {
            chips.innerHTML = '<span class="model-chip muted">Loading...</span>';
        }

        try {
            if (!provider) return;
            const data = await api.getModels(provider);
            this.models = data.models || [];
            const nextModel = this.pickModel(this.models, preferredModel);
            if (nextModel && nextModel !== preferredModel) {
                const updated = await api.updateAiSettings(provider, nextModel);
                this.settings = { ...this.settings, ...updated };
            }
            this.renderModelChips();
        } catch (err) {
            if (chips) {
                chips.innerHTML = '<span class="model-chip muted">No models available</span>';
            }
        }
    }

    pickModel(models, preferredModel) {
        if (!models || models.length === 0) return '';
        const match = models.find(m => m.id === preferredModel);
        if (match) return match.id;
        return models[0].id || models[0].name || '';
    }

    renderModelChips() {
        const chips = document.getElementById('modelChips');
        if (!chips) return;

        if (!this.models.length) {
            chips.innerHTML = '<span class="model-chip muted">No models available</span>';
            return;
        }

        chips.innerHTML = this.models.map(model => {
            const isActive = model.id === this.settings?.model;
            const label = this.escapeHtml(model.name || model.id);
            return `
                <button class="model-chip ${isActive ? 'active' : ''}" data-model="${this.escapeHtml(model.id)}"
                    onclick="chatPage.onModelSelect(this.dataset.model)">
                    ${label}
                </button>
            `;
        }).join('');
    }

    async onModelSelect(modelId) {
        if (!this.settings || !modelId || modelId === this.settings.model) return;
        try {
            const updated = await api.updateAiSettings(this.settings.provider, modelId);
            this.settings = { ...this.settings, ...updated };
            this.renderModelChips();
            Toast.success(`Model set to ${modelId}`);
        } catch (err) {
            Toast.error('Failed to switch model');
        }
    }

    onSearchChange(event) {
        this.searchQuery = event.target.value.trim().toLowerCase();
        this.renderChatList();
    }

    getFilteredChats() {
        if (!this.searchQuery) return this.chats;
        return this.chats.filter(chat =>
            (chat.title || '').toLowerCase().includes(this.searchQuery)
        );
    }

    async loadChats(options = {}) {
        const { autoSelect = true } = options;
        try {
            const data = await api.getChats(20);
            this.chats = data.chats || [];
            this.renderChatList();

            if (autoSelect) {
                // Select first active chat
                const active = this.chats.find(c => c.is_active);
                if (active) {
                    await this.selectChat(active.id);
                }
            } else if (this.currentChatId) {
                const current = this.chats.find(c => c.id === this.currentChatId);
                if (current) {
                    const title = document.getElementById('chatTitle');
                    if (title) {
                        title.textContent = current.title || 'Chat';
                    }
                }
            }
        } catch (err) {
            document.getElementById('chatList').innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-text">Failed to load chats</div>
                </div>
            `;
        }
    }

    renderChatList() {
        const list = document.getElementById('chatList');
        const visibleChats = this.getFilteredChats();

        if (this.chats.length === 0) {
            list.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-text">No chats yet</div>
                </div>
            `;
            return;
        }

        if (visibleChats.length === 0) {
            list.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-text">No chats match your search</div>
                </div>
            `;
            return;
        }

        list.innerHTML = visibleChats.map((chat, index) => `
            <div class="chat-item ${chat.id === this.currentChatId ? 'active' : ''}" 
                 style="--delay: ${index * 40}ms"
                 onclick="chatPage.selectChat(${chat.id})">
                <div class="chat-item-title">${this.escapeHtml(chat.title)}</div>
                <div class="chat-item-meta">${chat.is_active ? '✓ Active' : ''}</div>
            </div>
        `).join('');
    }

    async selectChat(chatId) {
        this.currentChatId = chatId;
        this.renderChatList();

        const messageList = document.getElementById('messageList');
        messageList.innerHTML = '<div class="loading"><div class="spinner"></div></div>';

        try {
            const chat = await api.getChat(chatId, 50);
            this.messages = chat.messages || [];
            document.getElementById('chatTitle').textContent = chat.title || 'Chat';

            await api.switchChat(chatId);
            this.renderMessages();
        } catch (err) {
            messageList.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-text">Failed to load chat</div>
                </div>
            `;
        }
    }

    renderMessages() {
        const container = document.getElementById('messageList');
        const empty = document.getElementById('emptyChat');

        if (this.messages.length === 0) {
            container.innerHTML = `
                <div class="empty-state" id="emptyChat">
                    <div class="empty-state-icon">💬</div>
                    <div class="empty-state-title">Start a conversation</div>
                    <div class="empty-state-text">Send a message to begin chatting with AI.</div>
                </div>
            `;
            return;
        }

        container.innerHTML = this.messages.map((msg, index) => `
            <div class="message ${msg.role}${msg.streaming ? ' streaming' : ''}" data-role="${msg.role === 'user' ? 'You' : 'QuBot'}" style="--delay: ${index * 30}ms">
                <div class="message-content">${msg.streaming ? this.escapeHtml(msg.content || '') : this.formatMessage(msg.content)}</div>
            </div>
        `).join('');

        container.scrollTop = container.scrollHeight;
    }

    formatMessage(content) {
        // Basic markdown-like formatting
        let html = this.escapeHtml(content || '');

        // Code blocks
        html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');

        // Inline code
        html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

        // Bold
        html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

        // Italic
        html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');

        return html;
    }

    async newChat() {
        try {
            const chat = await api.createChat();
            this.chats.unshift({ id: chat.id, title: chat.title || 'New Chat', is_active: true });
            await this.selectChat(chat.id);
            Toast.success('New chat created');
        } catch (err) {
            Toast.error('Failed to create chat');
        }
    }

    async sendMessage() {
        const input = document.getElementById('chatInput');
        const sendBtn = document.getElementById('sendBtn');
        const message = input.value.trim();

        if (!message || this.isLoading) return;

        this.isLoading = true;
        sendBtn.disabled = true;
        input.value = '';
        input.style.height = 'auto';

        // Add user message
        this.messages.push({ role: 'user', content: message });
        const streamingMessage = { role: 'assistant', content: '', streaming: true };
        this.messages.push(streamingMessage);
        this.renderMessages();

        const messageList = document.getElementById('messageList');
        const streamTarget = messageList.querySelector('.message.streaming .message-content');
        this.startStream(streamTarget);

        try {
            let response = null;
            try {
                response = await api.sendMessageStream(message, this.currentChatId, {
                    onMeta: (meta) => {
                        if (meta?.chatId && !this.currentChatId) {
                            this.currentChatId = meta.chatId;
                            this.pendingChatRefresh = true;
                        }
                    },
                    onChunk: (token) => {
                        if (token) {
                            this.streamQueue.push(token);
                        }
                    },
                    onDone: (data) => {
                        if (data?.content) {
                            this.streamFinalContent = data.content;
                        }
                    }
                });
            } catch (err) {
                this.stopStream();
                response = await api.sendMessage(message, this.currentChatId);
                this.streamFinalContent = response.content;
            }
            if (response?.content) {
                this.streamFinalContent = response.content;
            }

            // Update chat ID if new
            if (response.chatId && !this.currentChatId) {
                this.currentChatId = response.chatId;
                this.pendingChatRefresh = true;
            }

            await this.finishStream();

            streamingMessage.streaming = false;
            streamingMessage.content = this.streamFinalContent || this.streamContent || response.content || '';
            this.renderMessages();

            if (this.pendingChatRefresh) {
                this.pendingChatRefresh = false;
                await this.loadChats({ autoSelect: false });
            }
        } catch (err) {
            this.stopStream();
            streamingMessage.streaming = false;
            streamingMessage.content = `Error: ${err.message}`;
            this.renderMessages();
            Toast.error('Failed to send message');
            this.pendingChatRefresh = false;
        }

        this.isLoading = false;
        sendBtn.disabled = false;
        input.focus();
    }

    startStream(target) {
        this.streamQueue = [];
        this.streamContent = '';
        this.streamFinalContent = '';
        this.streamTarget = target;
        this.streamActive = true;

        if (this.streamTimer) {
            clearInterval(this.streamTimer);
        }

        this.streamDonePromise = new Promise((resolve) => {
            this.streamDoneResolver = resolve;
        });

        this.streamTimer = setInterval(() => {
            if (this.streamTarget && this.streamQueue.length) {
                const step = Math.max(3, Math.ceil(this.streamQueue.length / 20));
                const chunk = this.streamQueue.splice(0, step).join('');
                this.streamContent += chunk;
                this.streamTarget.textContent = this.streamContent;
                this.scrollToBottom();
            }

            if (!this.streamActive && this.streamQueue.length === 0) {
                clearInterval(this.streamTimer);
                this.streamTimer = null;
                this.streamDoneResolver?.();
            }
        }, 24);
    }

    async finishStream() {
        this.streamActive = false;
        if (this.streamDonePromise) {
            await this.streamDonePromise;
        }
        this.streamTarget = null;
        this.streamDonePromise = null;
        this.streamDoneResolver = null;
    }

    stopStream() {
        this.streamActive = false;
        this.streamQueue = [];
        if (this.streamTimer) {
            clearInterval(this.streamTimer);
            this.streamTimer = null;
        }
        this.streamDoneResolver?.();
        this.streamTarget = null;
        this.streamDonePromise = null;
        this.streamDoneResolver = null;
    }

    scrollToBottom() {
        const container = document.getElementById('messageList');
        if (container) {
            container.scrollTop = container.scrollHeight;
        }
    }

    async clearChat() {
        if (!this.currentChatId) return;

        if (!confirm('Clear all messages in this chat?')) return;

        try {
            await api.clearChat(this.currentChatId);
            this.messages = [];
            this.renderMessages();
            Toast.success('Chat cleared');
        } catch (err) {
            Toast.error('Failed to clear chat');
        }
    }

    async exportChat() {
        if (!this.currentChatId) return;

        try {
            Toast.info('Exporting chat...');
            const result = await api.exportChat(this.currentChatId);

            if (result.urls) {
                Toast.success('Exported to GitHub!');
                window.open(result.urls.notes, '_blank');
            } else {
                // Download as file
                const blob = new Blob([result.rawMarkdown], { type: 'text/markdown' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = result.filename;
                a.click();
                URL.revokeObjectURL(url);
                Toast.success('Downloaded!');
            }
        } catch (err) {
            Toast.error('Export failed');
        }
    }

    onKeyDown(event) {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            this.sendMessage();
        }
    }

    autoResizeTextarea() {
        const textarea = document.getElementById('chatInput');
        if (!textarea) return;

        textarea.addEventListener('input', () => {
            textarea.style.height = 'auto';
            textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
        });
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text || '';
        return div.innerHTML;
    }
}

window.chatPage = new ChatPage();
