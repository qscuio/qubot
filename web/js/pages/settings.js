/**
 * Settings Page
 */
class SettingsPage {
    constructor() {
        this.settings = null;
    }

    async render() {
        return `
            <div class="page" id="settingsPage">
                <div class="page-content" style="max-width: 600px; margin: 0 auto;">
                    <div class="page-header">
                        <span class="page-title">⚙️ Settings</span>
                    </div>
                    <div class="page-body">
                        <!-- API Key -->
                        <div class="card mb-md">
                            <div class="card-header">
                                <span class="card-title">🔑 API Key</span>
                            </div>
                            <div class="card-body">
                                <div class="input-group">
                                    <label class="input-label">Your API Key</label>
                                    <input type="password" class="input" id="apiKeyInput" 
                                        placeholder="Enter your API key"
                                        value="${api.getApiKey()}">
                                </div>
                                <button class="btn btn-primary mt-md" onclick="settingsPage.saveApiKey()">
                                    Save API Key
                                </button>
                            </div>
                        </div>

                        <!-- AI Settings -->
                        <div class="card mb-md">
                            <div class="card-header">
                                <span class="card-title">🧠 AI Provider</span>
                            </div>
                            <div class="card-body" id="aiSettingsContainer">
                                <div class="loading"><div class="spinner"></div></div>
                            </div>
                        </div>

                        <!-- Status -->
                        <div class="card">
                            <div class="card-header">
                                <span class="card-title">📊 System Status</span>
                            </div>
                            <div class="card-body" id="systemStatus">
                                <div class="loading"><div class="spinner"></div></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    async init() {
        await Promise.all([
            this.loadAiSettings(),
            this.loadStatus()
        ]);
    }

    async loadAiSettings() {
        const container = document.getElementById('aiSettingsContainer');

        try {
            const [settings, providersData] = await Promise.all([
                api.getAiSettings(),
                api.getProviders()
            ]);

            this.settings = settings;
            const providers = providersData.providers || [];

            container.innerHTML = `
                <div class="input-group mb-md">
                    <label class="input-label">Provider</label>
                    <select class="input" id="settingsProvider" onchange="settingsPage.onProviderChange()">
                        ${providers.map(p => `
                            <option value="${p.key}" ${p.key === settings.provider ? 'selected' : ''} ${!p.configured ? 'disabled' : ''}>
                                ${p.name}${!p.configured ? ' (not configured)' : ''}
                            </option>
                        `).join('')}
                    </select>
                </div>
                <div class="input-group">
                    <label class="input-label">Current Model</label>
                    <input type="text" class="input" id="settingsModel" value="${settings.model || ''}" readonly>
                </div>
            `;
        } catch (err) {
            container.innerHTML = `
                <div class="text-muted">Failed to load AI settings. Check your API key.</div>
            `;
        }
    }

    async onProviderChange() {
        const provider = document.getElementById('settingsProvider').value;

        try {
            await api.updateAiSettings(provider, null);
            Toast.success(`Switched to ${provider}`);
            await this.loadAiSettings();
        } catch (err) {
            Toast.error('Failed to update provider');
        }
    }

    async loadStatus() {
        const container = document.getElementById('systemStatus');

        try {
            const health = await api.getHealth();

            container.innerHTML = `
                <div class="flex justify-between mb-sm">
                    <span>Status</span>
                    <span class="text-sm" style="color: var(--accent-success);">✓ ${health.status}</span>
                </div>
                <div class="flex justify-between mb-sm">
                    <span>AI Service</span>
                    <span class="text-sm">${health.services?.ai ? '✓ Available' : '✕ Unavailable'}</span>
                </div>
                <div class="flex justify-between mb-sm">
                    <span>RSS Service</span>
                    <span class="text-sm">${health.services?.rss ? '✓ Available' : '✕ Unavailable'}</span>
                </div>
                <div class="flex justify-between">
                    <span>Monitor Service</span>
                    <span class="text-sm">${health.services?.monitor ? '✓ Available' : '✕ Unavailable'}</span>
                </div>
            `;
        } catch (err) {
            container.innerHTML = `
                <div class="text-muted">Failed to load status. Check connection and API key.</div>
            `;
        }
    }

    saveApiKey() {
        const input = document.getElementById('apiKeyInput');
        const key = input.value.trim();

        if (!key) {
            Toast.error('Please enter an API key');
            return;
        }

        api.setApiKey(key);
        Toast.success('API key saved!');

        // Reload settings
        this.loadAiSettings();
        this.loadStatus();
    }
}

window.settingsPage = new SettingsPage();
