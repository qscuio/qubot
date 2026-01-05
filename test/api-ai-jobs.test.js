const test = require("node:test");
const assert = require("node:assert/strict");
const { ApiServer } = require("../src/api");
const AiService = require("../src/services/AiService");
const { registerProvider } = require("../src/providers");
const { makeConfig } = require("./helpers/config");
const { FakeProvider } = require("./helpers/ai");
const { callExpress } = require("./helpers/express");

registerProvider("groq", new FakeProvider("FakeGroq"));

test("AI job endpoints return responses", async () => {
    const config = makeConfig({
        API_KEYS: "test:1"
    });
    const aiService = new AiService(config, null, null);
    const apiServer = new ApiServer(config, { ai: aiService });
    const app = apiServer.getApp();
    const authHeaders = { authorization: "Bearer test" };

    const jobsRes = await callExpress(app, {
        method: "GET",
        url: "/api/ai/jobs",
        headers: authHeaders
    });
    assert.equal(jobsRes.statusCode, 200);
    const jobsBody = jobsRes.body;
    const jobIds = jobsBody.jobs.map((job) => job.id);
    assert.ok(jobIds.includes("translate"));

    const translateRes = await callExpress(app, {
        method: "POST",
        url: "/api/ai/translate",
        headers: { ...authHeaders, "content-type": "application/json" },
        body: JSON.stringify({ text: "Hello", targetLanguage: "French" })
    });
    assert.equal(translateRes.statusCode, 200);
    const translateBody = translateRes.body;
    const translatePayload = JSON.parse(translateBody.translation);
    assert.ok(translatePayload.prompt.includes("French"));

    const funcRes = await callExpress(app, {
        method: "POST",
        url: "/api/ai/function-call",
        headers: { ...authHeaders, "content-type": "application/json" },
        body: JSON.stringify({
            task: "Create a user",
            functions: [{ name: "createUser", description: "Create a user", parameters: {} }]
        })
    });
    assert.equal(funcRes.statusCode, 200);
    const funcBody = funcRes.body;
    assert.ok(funcBody.result.prompt.includes("User request"));
});
