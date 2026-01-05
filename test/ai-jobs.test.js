const test = require("node:test");
const assert = require("node:assert/strict");
const { buildJobPrompt, listJobs } = require("../src/services/ai/PromptCatalog");
const { registerProvider } = require("../src/providers");
const AiService = require("../src/services/AiService");
const { makeConfig } = require("./helpers/config");
const { FakeProvider } = require("./helpers/ai");

registerProvider("groq", new FakeProvider("FakeGroq"));

test("prompt catalog exposes jobs and builds prompts", () => {
    const jobs = listJobs();
    const jobIds = jobs.map((job) => job.id);
    assert.ok(jobIds.includes("translate"));
    assert.ok(jobIds.includes("language_learning"));

    const { system, prompt } = buildJobPrompt("translate", {
        text: "Hello",
        targetLanguage: "Spanish",
        sourceLanguage: "English"
    });

    assert.ok(system.includes("translator"));
    assert.ok(prompt.includes("Spanish"));
    assert.ok(prompt.includes("Hello"));
});

test("AiService.runJob combines system and context", async () => {
    const config = makeConfig({});
    const aiService = new AiService(config, null, null);

    const response = await aiService.runJob(
        "analysis",
        { prompt: "Check this" },
        { provider: "groq", model: "fake-model", contextPrefix: "Extra context" }
    );

    const payload = JSON.parse(response.content);
    assert.equal(payload.prompt, "Check this");
    assert.ok(payload.contextPrefix.includes("careful analyst"));
    assert.ok(payload.contextPrefix.includes("Extra context"));
});
