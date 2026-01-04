/**
 * QuBot Web App - Main Application
 */
class App {
    constructor() {
        this.header = new Header();
        this.currentPage = null;
        this.pages = {
            chat: chatPage,
            rss: rssPage,
            monitor: monitorPage,
            settings: settingsPage
        };
    }

    async init() {
        // Check for API key
        if (!api.getApiKey()) {
            this.showApiKeyPrompt();
        } else {
            this.checkConnection();
        }

        // Setup routing
        window.addEventListener('hashchange', () => this.route());

        // Initial route
        await this.route();
    }

    showApiKeyPrompt() {
        const main = document.getElementById('mainContent');
        main.innerHTML = `
            <div class="page" style="display: flex; align-items: center; justify-content: center;">
                <div class="card" style="max-width: 400px; width: 100%;">
                    <div class="card-header">
                        <span class="card-title">🔑 Welcome to QuBot</span>
                    </div>
                    <div class="card-body">
                        <p class="text-muted mb-md">Enter your API key to get started.</p>
                        <div class="input-group">
                            <label class="input-label">API Key</label>
                            <input type="password" class="input" id="welcomeApiKey" 
                                placeholder="Your API key"
                                onkeydown="if(event.key==='Enter') app.saveWelcomeApiKey()">
                        </div>
                    </div>
                    <div class="card-footer">
                        <button class="btn btn-primary" style="width: 100%;" onclick="app.saveWelcomeApiKey()">
                            Continue
                        </button>
                    </div>
                </div>
            </div>
        `;
    }

    async saveWelcomeApiKey() {
        const input = document.getElementById('welcomeApiKey');
        const key = input.value.trim();

        if (!key) {
            Toast.error('Please enter an API key');
            return;
        }

        api.setApiKey(key);

        // Test connection
        try {
            await api.getHealth();
            Toast.success('Connected!');
            await this.route();
        } catch (err) {
            Toast.error('Invalid API key or server unreachable');
        }
    }

    async checkConnection() {
        try {
            const health = await api.getHealth();
            this.header.setStatus('connected', 'Online');
        } catch (err) {
            this.header.setStatus('error', 'Offline');
        }
    }

    async route() {
        const hash = window.location.hash.slice(2) || 'chat';
        const pageName = hash.split('/')[0];

        // Validate page
        if (!this.pages[pageName]) {
            window.location.hash = '#/chat';
            return;
        }

        // Cleanup current page
        if (this.currentPage && this.currentPage.destroy) {
            this.currentPage.destroy();
        }

        // Update nav
        this.header.setActiveNav(pageName);

        // Render new page
        const page = this.pages[pageName];
        const main = document.getElementById('mainContent');

        main.innerHTML = await page.render();

        // Initialize page
        if (page.init) {
            await page.init();
        }

        this.currentPage = page;
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.app = new App();
    window.app.init();
});
