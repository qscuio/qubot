const BaseProvider = require("./BaseProvider");

const TIMEOUT_MS = 90000; // 90 seconds

class OpenAIProvider extends BaseProvider {
    constructor() {
        super("OpenAI", "OPENAI_API_KEY");
        this.defaultModel = "gpt-4o-mini";
        this.fallbackModels = {
            "gpt-4o": "gpt-4o",
            "gpt-4o-mini": "gpt-4o-mini",
            "gpt-4-turbo": "gpt-4-turbo",
        };
    }

    async fetchModels(config) {
        const apiKey = this.getApiKey(config);
        if (!apiKey) return this.getFallbackModels();

        try {
            const response = await fetch("https://api.openai.com/v1/models", {
                headers: { Authorization: `Bearer ${apiKey}` },
            });

            if (!response.ok) return this.getFallbackModels();

            const data = await response.json();
            return (data.data || [])
                .filter((m) => m.id && (m.id.includes("gpt") || m.id.includes("o1") || m.id.includes("o3")))
                .filter((m) => !m.id.includes("instruct") && !m.id.includes("realtime"))
                .sort((a, b) => b.id.localeCompare(a.id))
                .map((m) => ({ id: m.id, name: m.id }));
        } catch (err) {
            this.logger.warn("Failed to fetch models, using fallback");
            return this.getFallbackModels();
        }
    }

    async call(apiKey, prompt, model, history = [], contextPrefix = "") {
        if (!apiKey) throw new Error("OPENAI_API_KEY is not set");

        const messages = [];
        if (contextPrefix) messages.push({ role: "system", content: contextPrefix });
        for (const msg of history) {
            messages.push({ role: msg.role, content: msg.content });
        }
        messages.push({ role: "user", content: prompt });

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);

        try {
            const response = await fetch("https://api.openai.com/v1/chat/completions", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer ${apiKey}`,
                },
                body: JSON.stringify({ model, messages, max_tokens: 4096 }),
                signal: controller.signal,
            });

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`OpenAI API Error: ${response.status} - ${errorText}`);
            }

            const data = await response.json();
            return { thinking: "", content: data.choices?.[0]?.message?.content || "" };
        } finally {
            clearTimeout(timeoutId);
        }
    }
}

module.exports = OpenAIProvider;
