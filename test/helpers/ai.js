class FakeProvider {
    constructor(name = "Fake") {
        this.name = name;
        this.defaultModel = "fake-model";
    }

    isConfigured() {
        return true;
    }

    getApiKey() {
        return "fake-key";
    }

    async fetchModels() {
        return [{ id: "fake-model", name: "fake" }];
    }

    async call(apiKey, prompt, model, history = [], contextPrefix = "") {
        return {
            thinking: "",
            content: JSON.stringify({
                apiKey,
                prompt,
                model,
                history,
                contextPrefix
            })
        };
    }
}

module.exports = {
    FakeProvider
};
