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
    // 4. Setup Event Handler


    // Better handler definition to include logic
    client.addEventHandler(async (event) => {
        const msg = event.message;
        if (!msg || !msg.message) return;

        // Determine source
        const chat = await msg.getChat().catch(() => null); // Added .catch(() => null) for robustness
        const chatUsername = chat?.username;
        const chatTitle = chat?.title || "Unknown";
        const chatId = chat?.id?.toString();

        // Filter check
        // We only care about messages from SOURCE_CHANNELS
        // Check Username, @Username, or ID
        const isMonitored = config.SOURCE_CHANNELS.some(source => {
            return source === chatUsername ||
                source === "@" + chatUsername ||
                source === chatId ||
                source === "-100" + chatId; // Handle common ID variations if needed, though exact string match is safer
        });

        if (!isMonitored) return;

        // Log for debugging
        const sourceName = chatUsername || chatTitle || chatId || "unknown"; // Updated sourceName derivation

        // --- NEW: Sender Filter ---
        // If FROM_USERS is defined, we must check the sender
        if (config.FROM_USERS.length > 0) {
            const sender = await msg.getSender().catch(() => null);
            const senderUsername = sender?.username;
            const senderId = sender?.id?.toString();

            const isAllowedUser = config.FROM_USERS.some(u =>
                u === senderUsername ||
                u === "@" + senderUsername ||
                u === senderId
            );

            if (!isAllowedUser) {
                console.log(` -> Ignored (sender ${senderUsername || senderId} not in whitelist)`);
                return;
            }
        }
        // --------------------------

        console.log(`Received message from ${sourceName} (ID: ${chatId}): ${msg.message.substring(0, 50)}...`);

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

})();

// The generic error handling for the process
process.on("unhandledRejection", (reason, promise) => {
    console.error("Unhandled Rejection at:", promise, "reason:", reason);
});
