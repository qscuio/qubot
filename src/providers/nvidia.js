const BaseProvider = require("./BaseProvider");

const TIMEOUT_MS = 120000; // 2 minutes for slow models like DeepSeek R1

class NvidiaProvider extends BaseProvider {
    constructor() {
        super("NVIDIA", "NVIDIA_API_KEY");
        this.defaultModel = "deepseek-ai/deepseek-r1";
        this.fallbackModels = {
            "deepseek-r1": "deepseek-ai/deepseek-r1",
            "deepseek-v3": "deepseek-ai/deepseek-v3.2",
            "llama-405b": "meta/llama-3.1-405b-instruct",
            "nemotron-ultra": "nvidia/llama-3.1-nemotron-ultra-253b-v1",
            "qwen3-coder": "qwen/qwen3-coder-480b-a35b-instruct",
            "llama-70b": "meta/llama-3.3-70b-instruct",
        };
    }

    async fetchModels(config) {
        // NVIDIA has too many models, use curated fallback list
        return this.getFallbackModels();
    }

    async call(apiKey, prompt, model, history = [], contextPrefix = "") {
        if (!apiKey) throw new Error("NVIDIA_API_KEY is not set");

        const messages = [];
        if (contextPrefix) messages.push({ role: "system", content: contextPrefix });
        for (const msg of history) {
            messages.push({ role: msg.role, content: msg.content });
        }
        messages.push({ role: "user", content: prompt });

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);

        try {
            console.log(`[NVIDIA] Calling API with model: ${model}`);
            console.log(`[NVIDIA] Key present: ${!!apiKey}, Key length: ${apiKey?.length}`);

            const response = await fetch("https://integrate.api.nvidia.com/v1/chat/completions", {
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
                throw new Error(`NVIDIA API Error: ${response.status} - ${errorText}`);
            }

            const data = await response.json();
            return { thinking: "", content: data.choices?.[0]?.message?.content || "" };
        } finally {
            clearTimeout(timeoutId);
        }
    }
}

module.exports = NvidiaProvider;
