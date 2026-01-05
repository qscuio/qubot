/**
 * RSS Page
 */
class RssPage {
    constructor() {
        this.subscriptions = [];
    }

    async render() {
        return `
            <div class="page" id="rssPage">
                <div class="page-content">
                    <div class="page-header">
                        <span class="page-title">📰 RSS Subscriptions</span>
                        <button class="btn btn-primary" onclick="rssPage.showAddModal()">+ Add Feed</button>
                    </div>
                    <div class="page-body">
                        <div class="rss-grid" id="rssGrid">
                            <div class="loading"><div class="spinner"></div></div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Add Feed Modal -->
            <div class="modal-overlay hidden" id="addFeedModal" onclick="rssPage.hideAddModal(event)">
                <div class="modal" onclick="event.stopPropagation()">
                    <div class="modal-header">
                        <span class="modal-title">Add RSS Feed</span>
                        <button class="btn btn-icon" onclick="rssPage.hideAddModal()">✕</button>
                    </div>
                    <div class="modal-body">
                        <div class="input-group">
                            <label class="input-label">Feed URL</label>
                            <input type="url" class="input" id="feedUrlInput" 
                                placeholder="https://example.com/feed.xml"
                                onkeydown="if(event.key==='Enter') rssPage.addFeed()">
                        </div>
                        <div id="feedPreview" class="mt-md"></div>
                    </div>
                    <div class="modal-footer">
                        <button class="btn btn-secondary" onclick="rssPage.hideAddModal()">Cancel</button>
                        <button class="btn btn-primary" id="addFeedBtn" onclick="rssPage.addFeed()">Add Feed</button>
                    </div>
                </div>
            </div>
        `;
    }

    async init() {
        await this.loadSubscriptions();
    }

    async loadSubscriptions() {
        const grid = document.getElementById('rssGrid');

        try {
            const data = await api.getRssSubscriptions();
            this.subscriptions = data.subscriptions || [];
            this.renderGrid();
        } catch (err) {
            grid.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">❌</div>
                    <div class="empty-state-text">Failed to load subscriptions</div>
                </div>
            `;
        }
    }

    renderGrid() {
        const grid = document.getElementById('rssGrid');

        if (this.subscriptions.length === 0) {
            grid.innerHTML = `
                <div class="empty-state" style="grid-column: 1 / -1;">
                    <div class="empty-state-icon">📰</div>
                    <div class="empty-state-title">No subscriptions yet</div>
                    <div class="empty-state-text">Add your first RSS feed to get started.</div>
                    <button class="btn btn-primary mt-md" onclick="rssPage.showAddModal()">+ Add Feed</button>
                </div>
            `;
            return;
        }

        grid.innerHTML = this.subscriptions.map(sub => `
            <div class="rss-card">
                <div class="rss-card-header">
                    <span class="rss-card-title">${this.escapeHtml(sub.title)}</span>
                    <button class="btn btn-icon" onclick="rssPage.removeFeed(${sub.id}, '${this.escapeHtml(sub.title)}')">🗑️</button>
                </div>
                <div class="rss-card-body">
                    <div class="rss-card-url">${this.escapeHtml(sub.url)}</div>
                    ${sub.latestItem ? `
                        <div class="rss-card-preview">
                            <strong>Latest:</strong> ${this.escapeHtml(sub.latestItem.title || '')}
                        </div>
                    ` : ''}
                </div>
            </div>
        `).join('');
    }

    showAddModal() {
        document.getElementById('addFeedModal').classList.remove('hidden');
        document.getElementById('feedUrlInput').focus();
        document.getElementById('feedPreview').innerHTML = '';
    }

    hideAddModal(event) {
        if (event && event.target.id !== 'addFeedModal') return;
        document.getElementById('addFeedModal').classList.add('hidden');
        document.getElementById('feedUrlInput').value = '';
        document.getElementById('feedPreview').innerHTML = '';
    }

    async addFeed() {
        const urlInput = document.getElementById('feedUrlInput');
        const url = urlInput.value.trim();
        const addBtn = document.getElementById('addFeedBtn');

        if (!url) {
            Toast.error('Please enter a URL');
            return;
        }

        addBtn.disabled = true;
        addBtn.textContent = 'Adding...';

        try {
            const result = await api.addRssSubscription(url);

            if (result.added) {
                Toast.success(`Added: ${result.title}`);
                this.hideAddModal();
                await this.loadSubscriptions();
            } else {
                Toast.info('Already subscribed to this feed');
            }
        } catch (err) {
            Toast.error(`Failed: ${err.message}`);
        }

        addBtn.disabled = false;
        addBtn.textContent = 'Add Feed';
    }

    async removeFeed(id, title) {
        if (!confirm(`Remove "${title}" from subscriptions?`)) return;

        try {
            await api.removeRssSubscription(id);
            Toast.success('Subscription removed');
            await this.loadSubscriptions();
        } catch (err) {
            Toast.error('Failed to remove subscription');
        }
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text || '';
        return div.innerHTML;
    }
}

window.rssPage = new RssPage();
