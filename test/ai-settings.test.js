const test = require("node:test");
const assert = require("node:assert/strict");
const { createTestDatabase } = require("./helpers/db");
const { makeConfig } = require("./helpers/config");
const StorageService = require("../src/core/StorageService");
const AiService = require("../src/services/AiService");

test("AI settings persist per user", async (t) => {
    const db = await createTestDatabase();
    if (!db.available) {
        t.skip("DATABASE_URL or TEST_DATABASE_URL is not set");
        return;
    }

    const config = makeConfig({
        DATABASE_URL: db.databaseUrl
    });

    const storage = new StorageService(config);
    t.after(async () => {
        await storage.close();
        await db.cleanup();
    });
    await storage.init();

    const aiService = new AiService(config, storage, null);
    const userId = 123;

    await aiService.updateSettings(userId, "groq", "model-1");
    const settings = await aiService.getSettings(userId);

    assert.equal(settings.provider, "groq");
    assert.equal(settings.model, "model-1");
});
