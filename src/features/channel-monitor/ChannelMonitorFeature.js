const BaseFeature = require("../BaseFeature");

/**
 * ChannelMonitorFeature - Monitors channels for keywords and forwards messages.
 */
class ChannelMonitorFeature extends BaseFeature {
    constructor(services) {
        super(services);
        this.sourceChannels = [];
        this.targetChannel = "";
        this.keywords = [];
        this.fromUsers = [];
    }

    async onInit() {
        this.sourceChannels = this.config.get("SOURCE_CHANNELS");
        this.targetChannel = this.config.get("TARGET_CHANNEL");
        this.keywords = this.config.get("KEYWORDS");
        this.fromUsers = this.config.get("FROM_USERS");

        this.logger.info(`Monitoring ${this.sourceChannels.length} channels.`);
        this.logger.info(`Keywords: ${this.keywords.length > 0 ? this.keywords.join(", ") : "(none - forward all)"}`);
        this.logger.info(`User whitelist: ${this.fromUsers.length > 0 ? this.fromUsers.join(", ") : "(none - allow all)"}`);
    }

    async onEnable() {
        if (this.sourceChannels.length === 0) {
            this.logger.warn("No SOURCE_CHANNELS configured. Feature disabled.");
            return;
        }

        this.telegram.addMessageHandler(
            this._handleMessage.bind(this),
            this.sourceChannels
        );

        this.logger.info("Message handler registered.");
    }

    async _handleMessage(event) {
        try {
            const msg = event.message;
            if (!msg || !msg.message) return;

            const chat = await msg.getChat().catch(() => null);
            const chatUsername = chat?.username;
            const chatTitle = chat?.title || "Unknown";
            const rawChatId = chat?.id?.toString() || "";

            // Normalize chatId: strip -100 prefix if present for comparison
            const normalizedChatId = rawChatId.startsWith("-100")
                ? rawChatId.slice(4)
                : rawChatId;

            // Check if from monitored source
            const isMonitored = this.sourceChannels.some((source) => {
                // Normalize source ID the same way
                const normalizedSource = source.startsWith("-100")
                    ? source.slice(4)
                    : source.replace(/^@/, "");

                return (
                    source === chatUsername ||
                    source === "@" + chatUsername ||
                    normalizedSource === normalizedChatId ||
                    source === rawChatId
                );
            });

            if (!isMonitored) return;

            const sourceName = chatUsername || chatTitle || rawChatId || "unknown";

            // User filter
            if (this.fromUsers.length > 0) {
                const sender = await msg.getSender().catch(() => null);
                const senderUsername = sender?.username;
                const senderId = sender?.id?.toString();

                const isAllowedUser = this.fromUsers.some(
                    (u) =>
                        u === senderUsername ||
                        u === "@" + senderUsername ||
                        u === senderId
                );

                if (!isAllowedUser) {
                    this.logger.debug(`Ignored (sender ${senderUsername || senderId} not in whitelist)`);
                    return;
                }
            }

            // Keyword filter
            if (!this._shouldKeep(msg.message)) {
                this.logger.debug(`Ignored (no keyword match): ${msg.message.substring(0, 30)}...`);
                return;
            }

            // Forward message
            this.logger.info(`Matched keyword from ${sourceName}. Forwarding...`);
            const formattedMessage = this._rewrite(msg.message, sourceName);

            await this.telegram.sendMessage(this.targetChannel, {
                message: formattedMessage,
            });

            this.logger.info("Message forwarded.");
        } catch (err) {
            this.logger.error("Error handling message", err);
        }
    }

    _shouldKeep(text) {
        if (!text) return false;
        if (this.keywords.length === 0) return true; // No keywords = forward all

        const lowerText = text.toLowerCase();
        return this.keywords.some((k) => lowerText.includes(k));
    }

    _rewrite(text, sourceName) {
        const cleanText = text.replace(/\s+/g, " ").trim();
        return `🔔【New Alert】\n\n${cleanText}\n\n— Source: ${sourceName}`;
    }
}

module.exports = ChannelMonitorFeature;
