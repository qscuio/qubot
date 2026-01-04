require("dotenv").config();

module.exports = {
    API_ID: parseInt(process.env.API_ID || ""),
    API_HASH: process.env.API_HASH || "",
    SESSION: process.env.TG_SESSION || "",

    // Channels to monitor (cleaned up string array)
    SOURCE_CHANNELS: (process.env.SOURCE_CHANNELS || "")
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),

    // Target channel to forward to
    TARGET_CHANNEL: process.env.TARGET_CHANNEL || "me",

    // Keywords to filter
    KEYWORDS: (process.env.KEYWORDS || "")
        .split(",")
        .map((s) => s.trim().toLowerCase())
        .filter(Boolean),

    // Filter by specific users (optional whitelist)
    // Can be Usernames or IDs
    FROM_USERS: (process.env.FROM_USERS || "")
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
};
