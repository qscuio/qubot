const BaseProvider = require("./BaseProvider");

const TIMEOUT_MS = 90000; // 90 seconds

class GeminiProvider extends BaseProvider {
    constructor() {
        super("Gemini", "GEMINI_API_KEY");
        this.defaultModel = "gemini-2.0-flash";
        this.fallbackModels = {
            "flash": "gemini-2.0-flash",
            "flash-lite": "gemini-2.0-flash-lite",
            "pro": "gemini-2.5-pro-preview-06-05",
        };
    }

    async fetchModels(config) {
        const apiKey = this.getApiKey(config);
        if (!apiKey) return this.getFallbackModels();

        try {
            const response = await fetch(
                `https://generativelanguage.googleapis.com/v1beta/models?key=${apiKey}`
            );

            if (!response.ok) return this.getFallbackModels();

            const data = await response.json();
            return (data.models || [])
                .filter((m) => m.name && m.supportedGenerationMethods?.includes("generateContent"))
                .map((m) => ({
                    id: m.name.replace("models/", ""),
                    name: m.displayName || m.name.replace("models/", ""),
                }));
        } catch (err) {
            this.logger.warn("Failed to fetch models, using fallback");
            return this.getFallbackModels();
        }
    }

    async call(apiKey, prompt, model, history = [], contextPrefix = "") {
        if (!apiKey) throw new Error("GEMINI_API_KEY is not set");

        const contents = [];
        for (const msg of history) {
            contents.push({
                role: msg.role === "assistant" ? "model" : "user",
                parts: [{ text: msg.content }],
            });
        }
        const fullPrompt = contextPrefix ? `${contextPrefix}${prompt}` : prompt;
        contents.push({ role: "user", parts: [{ text: fullPrompt }] });

        const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`;
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);

        try {
            const response = await fetch(url, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ contents }),
                signal: controller.signal,
            });

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`Gemini API Error: ${response.status} - ${errorText}`);
            }

            const data = await response.json();
            let thinking = "", content = "";
            if (data.candidates?.[0]?.content?.parts) {
                for (const part of data.candidates[0].content.parts) {
                    if (part.thought) thinking += part.text || "";
                    else content += part.text || "";
                }
            }
            return { thinking, content };
        } finally {
            clearTimeout(timeoutId);
        }
    }
}

module.exports = GeminiProvider;
