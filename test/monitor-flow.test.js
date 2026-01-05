const test = require("node:test");
const assert = require("node:assert/strict");
const { createTestDatabase } = require("./helpers/db");
const { makeConfig } = require("./helpers/config");
const StorageService = require("../src/core/StorageService");
const MonitorService = require("../src/services/MonitorService");

test("monitor history is scoped per user and respects filters", async (t) => {
    const db = await createTestDatabase();
    if (!db.available) {
        t.skip("DATABASE_URL or TEST_DATABASE_URL is not set");
        return;
    }

    const config = makeConfig({
        DATABASE_URL: db.databaseUrl,
        API_KEYS: "key1:42,key2:7",
        ALLOWED_USERS: [],
        KEYWORDS: [],
        FROM_USERS: []
    });

    const storage = new StorageService(config);
    t.after(async () => {
        await storage.close();
        await db.cleanup();
    });
    await storage.init();

    const monitorService = new MonitorService(config, storage, null, null);
    await monitorService.updateFilters(42, { keywords: ["bitcoin"] });
    await monitorService.updateFilters(7, { enabled: false });

    await monitorService._saveToHistory({
        text: "bitcoin price is up",
        source: "@market",
        sourceId: "123",
        timestamp: new Date().toISOString()
    });

    const historyUser42 = await monitorService.getHistory(42, 10);
    const historyUser7 = await monitorService.getHistory(7, 10);

    assert.equal(historyUser42.length, 1);
    assert.equal(historyUser7.length, 0);

});
