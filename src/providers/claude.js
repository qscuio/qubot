const BaseProvider = require("./BaseProvider");

const TIMEOUT_MS = 55000;

class ClaudeProvider extends BaseProvider {
    constructor() {
        super("Claude", "CLAUDE_API_KEY");
        this.defaultModel = "claude-sonnet-4-20250514";
        this.fallbackModels = {
            "sonnet": "claude-sonnet-4-20250514",
            "haiku": "claude-3-5-haiku-20241022",
            "opus": "claude-3-opus-20240229",
        };
    }

    async fetchModels(config) {
        // Claude doesn't have a public models API
        return this.getFallbackModels();
    }

    async call(apiKey, prompt, model, history = [], contextPrefix = "") {
        if (!apiKey) throw new Error("CLAUDE_API_KEY is not set");

        const messages = [];
        for (const msg of history) {
            messages.push({ role: msg.role, content: msg.content });
        }
        const fullPrompt = contextPrefix ? `${contextPrefix}${prompt}` : prompt;
        messages.push({ role: "user", content: fullPrompt });

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);

        try {
            const response = await fetch("https://api.anthropic.com/v1/messages", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "x-api-key": apiKey,
                    "anthropic-version": "2023-06-01",
                },
                body: JSON.stringify({ model, max_tokens: 4096, messages }),
                signal: controller.signal,
            });

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`Claude API Error: ${response.status} - ${errorText}`);
            }

            const data = await response.json();
            let thinking = "", content = "";
            if (data.content) {
                for (const block of data.content) {
                    if (block.type === "thinking") thinking += block.thinking || "";
                    else if (block.type === "text") content += block.text || "";
                }
            }
            return { thinking, content };
        } finally {
            clearTimeout(timeoutId);
        }
    }
}

module.exports = ClaudeProvider;
