const { TelegramClient } = require("telegram");
const { StringSession } = require("telegram/sessions");
const { NewMessage } = require("telegram/events");
const config = require("./config");
const { shouldKeep, rewrite } = require("./monitor");

(async () => {
    // 1. Validation
    if (!config.API_ID || !config.API_HASH || !config.SESSION) {
        console.error("❌ Missing API_ID, API_HASH, or TG_SESSION in environment.");
        process.exit(1);
    }

    // 2. Initialize Client
    console.log("Connecting to Telegram..."); // User-friendly log
    const client = new TelegramClient(
        new StringSession(config.SESSION),
        config.API_ID,
        config.API_HASH,
        {
            connectionRetries: 5,
        }
    );

    // 3. Connect (session must be valid)
    await client.connect();
    console.log("✅ Userbot connected!");

    // 4. Setup Event Handler
    client.addEventHandler(async (event) => {
        try {
            const message = event.message;

            // Determine source
            const chat = await message.getChat();
            const chatUsername = chat?.username || chat?.title || "Unknown";

            // Filter check
            // We only care about messages from SOURCE_CHANNELS
            // Note: event listener is global, so we must filter by chat.
            const isMonitored = config.SOURCE_CHANNELS.includes(chatUsername) || config.SOURCE_CHANNELS.includes("@" + chatUsername);

            // Currently, gramjs NewMessage with chats: [...] option is more efficient 
            // but let's see if we can use it, or filter manually.
            // If we use `chats` option in event builder, gramjs handles it.

        } catch (err) {
            console.error("Handler Error:", err);
        }
    }, new NewMessage({ chats: config.SOURCE_CHANNELS })); // Filter by source channels effectively

    // Better handler definition to include logic
    client.addEventHandler(async (event) => {
        const msg = event.message;
        if (!msg || !msg.message) return;

        // Log for debugging
        const chat = await msg.getChat().catch(() => null);
        const sourceName = chat?.username || chat?.title || "unknown";
        console.log(`Received message from ${sourceName}: ${msg.message.substring(0, 50)}...`);

        if (shouldKeep(msg.message)) {
            console.log(" -> Matched keyword, forwarding...");
            const out = rewrite(msg.message, sourceName);

            await client.sendMessage(config.TARGET_CHANNEL, {
                message: out,
                // Optional: include original media? User request said "summarize and sent", implies text processing.
                // But preventing link previews etc might be good.
            });
            console.log(" -> Sent.");
        } else {
            console.log(" -> Ignored (no keyword match)");
        }
    }, new NewMessage({ chats: config.SOURCE_CHANNELS }));

    console.log("🚀 Userbot is running and monitoring:", config.SOURCE_CHANNELS);

}, new NewMessage({ incoming: true })); // Wait, I already added event handler above. 

// The generic error handling for the process
process.on("unhandledRejection", (reason, promise) => {
    console.error("Unhandled Rejection at:", promise, "reason:", reason);
});
