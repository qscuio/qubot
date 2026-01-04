const { TelegramClient } = require("telegram");
const { StringSession } = require("telegram/sessions");
const input = require("input");
const fs = require("fs");
const path = require("path");

const API_ID = parseInt(process.env.API_ID || "");
const API_HASH = process.env.API_HASH || "";

if (isNaN(API_ID) || !API_HASH) {
    console.log("Please provide API_ID and API_HASH environment variables or enter them now.");
}

(async () => {
    let apiId = API_ID;
    let apiHash = API_HASH;

    if (!apiId) {
        apiId = parseInt(await input.text("Enter API ID: "));
    }
    if (!apiHash) {
        apiHash = await input.text("Enter API Hash: ");
    }

    const client = new TelegramClient(new StringSession(""), apiId, apiHash, {
        connectionRetries: 5,
    });

    await client.start({
        phoneNumber: async () => await input.text("Phone number (international format): "),
        phoneCode: async () => await input.text("Code: "),
        password: async () => await input.text("2FA Password (if any): "),
        onError: (err) => console.log(err),
    });

    const sessionString = client.session.save();
    console.log("\n✅ Session generated successfully!");
    console.log("\nSESSION STRING (save this to your .env file as TG_SESSION):");
    console.log("---------------------------------------------------");
    console.log(sessionString);
    console.log("---------------------------------------------------");

    // Optional: save to .env if user wants (simple append, careful with duplicates)
    // For now, just printing it is safer.

    await client.disconnect();
    process.exit(0);
})();
