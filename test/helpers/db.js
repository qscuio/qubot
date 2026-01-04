const { Client } = require("pg");
const { randomUUID } = require("crypto");

function getDatabaseUrl() {
    return process.env.TEST_DATABASE_URL || process.env.DATABASE_URL || "";
}

function buildAdminUrl(databaseUrl) {
    const url = new URL(databaseUrl);
    url.pathname = "/postgres";
    return url.toString();
}

function buildDatabaseUrl(databaseUrl, databaseName) {
    const url = new URL(databaseUrl);
    url.pathname = `/${databaseName}`;
    return url.toString();
}

async function createTestDatabase() {
    const baseUrl = getDatabaseUrl();
    if (!baseUrl) {
        return { databaseUrl: "", cleanup: async () => {}, available: false };
    }

    const dbName = `qubot_test_${randomUUID().replace(/-/g, "")}`;
    const adminUrl = buildAdminUrl(baseUrl);
    const client = new Client({ connectionString: adminUrl });

    await client.connect();
    await client.query(`CREATE DATABASE "${dbName}"`);
    await client.end();

    return {
        databaseUrl: buildDatabaseUrl(baseUrl, dbName),
        available: true,
        cleanup: async () => {
            const cleanupClient = new Client({ connectionString: adminUrl });
            await cleanupClient.connect();
            await cleanupClient.query(
                `SELECT pg_terminate_backend(pid)
                 FROM pg_stat_activity
                 WHERE datname = $1 AND pid <> pg_backend_pid()`,
                [dbName]
            );
            await cleanupClient.query(`DROP DATABASE IF EXISTS "${dbName}"`);
            await cleanupClient.end();
        }
    };
}

module.exports = {
    createTestDatabase
};
