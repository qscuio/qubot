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
    }

    async render() {
        return `
            <div class="page" id="chatPage">
                <aside class="page-sidebar">
                    <div class="page-header">
                        <span class="page-title">💬 Chats</span>
                        <button class="btn btn-primary" onclick="chatPage.newChat()">+ New</button>
                    </div>
                    <div class="chat-list" id="chatList">
                        <div class="loading"><div class="spinner"></div></div>
                    </div>
                </aside>
                <div class="page-content">
                    <div class="page-header">
                        <div class="flex items-center gap-md">
                            <span class="page-title" id="chatTitle">New Chat</span>
                            <select class="input" id="providerSelect" onchange="chatPage.onProviderChange()">
                                <option value="">Loading...</option>
                            </select>
                        </div>
                        <div class="flex gap-sm">
                            <button class="btn btn-secondary" onclick="chatPage.exportChat()">📤 Export</button>
                            <button class="btn btn-secondary" onclick="chatPage.clearChat()">🗑️ Clear</button>
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
    }

    async loadSettings() {
        try {
            const [settings, providersData] = await Promise.all([
                api.getAiSettings(),
                api.getProviders()
            ]);
            this.settings = settings;

            const select = document.getElementById('providerSelect');
            select.innerHTML = providersData.providers.map(p =>
                `<option value="${p.key}" ${p.key === settings.provider ? 'selected' : ''} ${!p.configured ? 'disabled' : ''}>
                    ${p.name}${!p.configured ? ' ⚠️' : ''}
                </option>`
            ).join('');
        } catch (err) {
            console.error('Failed to load settings:', err);
        }
    }

    async onProviderChange() {
        const select = document.getElementById('providerSelect');
        const provider = select.value;
        try {
            await api.updateAiSettings(provider, null);
            Toast.success(`Switched to ${provider}`);
        } catch (err) {
            Toast.error('Failed to switch provider');
        }
    }

    async loadChats() {
        try {
            const data = await api.getChats(20);
            this.chats = data.chats || [];
            this.renderChatList();

            // Select first active chat
            const active = this.chats.find(c => c.is_active);
            if (active) {
                await this.selectChat(active.id);
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

        if (this.chats.length === 0) {
            list.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-text">No chats yet</div>
                </div>
            `;
            return;
        }

        list.innerHTML = this.chats.map(chat => `
            <div class="chat-item ${chat.id === this.currentChatId ? 'active' : ''}" 
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

        container.innerHTML = this.messages.map(msg => `
            <div class="message ${msg.role}">
                <div class="message-content">${this.formatMessage(msg.content)}</div>
            </div>
        `).join('');

        container.scrollTop = container.scrollHeight;
    }

    formatMessage(content) {
        // Basic markdown-like formatting
        let html = this.escapeHtml(content);

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
        this.renderMessages();

        // Add loading placeholder
        const messageList = document.getElementById('messageList');
        const loadingDiv = document.createElement('div');
        loadingDiv.className = 'message assistant';
        loadingDiv.innerHTML = '<div class="message-content">🤔 Thinking...</div>';
        messageList.appendChild(loadingDiv);
        messageList.scrollTop = messageList.scrollHeight;

        try {
            const response = await api.sendMessage(message, this.currentChatId);

            // Update chat ID if new
            if (response.chatId && !this.currentChatId) {
                this.currentChatId = response.chatId;
                await this.loadChats();
            }

            // Replace loading with response
            this.messages.push({ role: 'assistant', content: response.content });
            this.renderMessages();
        } catch (err) {
            loadingDiv.innerHTML = `<div class="message-content">❌ Error: ${err.message}</div>`;
            Toast.error('Failed to send message');
        }

        this.isLoading = false;
        sendBtn.disabled = false;
        input.focus();
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
        div.textContent = text;
        return div.innerHTML;
    }
}

window.chatPage = new ChatPage();
