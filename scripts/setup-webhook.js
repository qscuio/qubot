#!/usr/bin/env node
/**
 * Setup webhook for all configured bots.
 * Usage: npm run setup-webhook
 */

require("dotenv").config();

const https = require("https");

const WEBHOOK_URL = process.env.WEBHOOK_URL;
const BOT_SECRET = process.env.BOT_SECRET;

const bots = [
    { name: "rss-bot", token: process.env.RSS_BOT_TOKEN },
    { name: "ai-bot", token: process.env.AI_BOT_TOKEN },
    { name: "agent-bot", token: process.env.AGENT_BOT_TOKEN },
    { name: "monitor-bot", token: process.env.MONITOR_BOT_TOKEN },
].filter((b) => b.token);

if (!WEBHOOK_URL) {
    console.error("❌ WEBHOOK_URL is not set");
    process.exit(1);
}

async function setWebhook(botName, token) {
    const webhookUrl = `${WEBHOOK_URL}/webhook/${botName}`;
    const apiUrl = `https://api.telegram.org/bot${token}/setWebhook`;

    const params = new URLSearchParams({
        url: webhookUrl,
        allowed_updates: JSON.stringify(["message", "callback_query", "inline_query"]),
    });

    if (BOT_SECRET) {
        params.append("secret_token", BOT_SECRET);
    }

    return new Promise((resolve, reject) => {
        const req = https.request(`${apiUrl}?${params}`, { method: "POST" }, (res) => {
            let data = "";
            res.on("data", (chunk) => (data += chunk));
            res.on("end", () => {
                try {
                    const result = JSON.parse(data);
                    if (result.ok) {
                        console.log(`✅ ${botName}: Webhook set to ${webhookUrl}`);
                        resolve(result);
                    } else {
                        console.error(`❌ ${botName}: ${result.description}`);
                        reject(new Error(result.description));
                    }
                } catch (e) {
                    reject(e);
                }
            });
        });
        req.on("error", reject);
        req.end();
    });
}

async function main() {
    console.log("🔗 Setting up webhooks...\n");

    for (const bot of bots) {
        try {
            await setWebhook(bot.name, bot.token);
        } catch (err) {
            console.error(`Failed to set webhook for ${bot.name}:`, err.message);
        }
    }

    console.log("\n✅ Done!");
}

main();
