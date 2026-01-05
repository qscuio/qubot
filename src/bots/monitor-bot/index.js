const BotInstance = require("../../core/BotInstance");
const { escapeHtml } = require("../../core/TelegramUtils");

/**
 * MonitorBot - Telegram interface for channel monitoring.
 * Uses MonitorService for business logic.
 * Provides commands to control and configure monitoring.
 */
class MonitorBot extends BotInstance {
    constructor(token, config, allowedUsers, monitorService = null) {
        super("monitor-bot", token, allowedUsers);
        this.config = config;
        this.monitorService = monitorService;
    }

    /**
     * Set the monitor service (allows injection after construction).
     */
    setService(monitorService) {
        this.monitorService = monitorService;
    }

    async setup() {
        if (!this.isEnabled()) {
            this.logger.warn("Monitor Bot token not configured.");
            return;
        }

        // Register commands
        this.command("start", "Welcome and status", (ctx) => this._handleStart(ctx));
        this.command("status", "Monitor status", (ctx) => this._handleStatus(ctx));
        this.command("sources", "List source channels", (ctx) => this._handleSources(ctx));
        this.command("add", "Add source channel", (ctx) => this._handleAdd(ctx));
        this.command("remove", "Remove source channel", (ctx) => this._handleRemove(ctx));
        this.command("enable", "Enable source channel", (ctx) => this._handleEnable(ctx));
        this.command("disable", "Disable source channel", (ctx) => this._handleDisable(ctx));
        this.command("target", "Set target channel", (ctx) => this._handleTarget(ctx));
        this.command("forward", "Toggle forwarding", (ctx) => this._handleForward(ctx));
        this.command("history", "Recent messages", (ctx) => this._handleHistory(ctx));
        this.command("filters", "Show user filters", (ctx) => this._handleFilters(ctx));
        this.command("monitor", "Start/stop monitoring", (ctx) => this._handleMonitor(ctx));
        this.command("help", "Show help", (ctx) => this._handleHelp(ctx));

        // Callback actions
        this.action("cmd_start", (ctx) => this._handleMonitorStart(ctx));
        this.action("cmd_stop", (ctx) => this._handleMonitorStop(ctx));
        this.action("cmd_status", (ctx) => this._handleStatus(ctx));
        this.action("cmd_sources", (ctx) => this._handleSources(ctx));
        this.action("cmd_history", (ctx) => this._handleHistory(ctx));
        this.action(/^remove:(.+)$/, (ctx) => this._handleRemoveSource(ctx));
        this.action(/^enable:(.+)$/, (ctx) => this._handleEnableSource(ctx));
        this.action(/^disable:(.+)$/, (ctx) => this._handleDisableSource(ctx));
        this.action("cmd_forward_on", (ctx) => this._handleForwardOn(ctx));
        this.action("cmd_forward_off", (ctx) => this._handleForwardOff(ctx));

        this.logger.info("MonitorBot commands registered.");
    }

    _quickActionsKeyboard() {
        const status = this.monitorService?.getStatus() || {};
        const forwardBtn = status.forwarding
            ? { text: "⏸️ Pause", callback_data: "cmd_forward_off" }
            : { text: "▶️ Resume", callback_data: "cmd_forward_on" };
        return {
            inline_keyboard: [
                [{ text: "▶️ Start", callback_data: "cmd_start" }, { text: "⏹️ Stop", callback_data: "cmd_stop" }],
                [forwardBtn, { text: "📋 Sources", callback_data: "cmd_sources" }],
                [{ text: "📜 History", callback_data: "cmd_history" }],
            ]
        };
    }

    async _handleStart(ctx) {
        if (!this.monitorService) {
            return ctx.reply("❌ Monitor service not available.");
        }

        const status = this.monitorService.getStatus();
        const statusIcon = status.running ? "🟢" : "🔴";

        await ctx.reply(
            `🔔 <b>Channel Monitor Bot</b>\n\n` +
            `<b>Status:</b> ${statusIcon} ${status.running ? "Running" : "Stopped"}\n` +
            `<b>Source channels:</b> ${status.sourceChannels}\n` +
            `<b>Target:</b> ${status.targetChannel || "Not set"}\n\n` +
            `<i>Use the buttons below to control monitoring.</i>`,
            { parse_mode: "HTML", reply_markup: this._quickActionsKeyboard() }
        );
    }

    async _handleStatus(ctx) {
        if (!this.monitorService) {
            return ctx.reply("❌ Monitor service not available.");
        }

        const status = this.monitorService.getStatus();
        const runningIcon = status.running ? "🟢" : "🔴";
        const forwardIcon = status.forwarding ? "✅" : "⏸️";

        await ctx.reply(
            `📊 <b>Monitor Status</b>\n\n` +
            `<b>Monitoring:</b> ${runningIcon} ${status.running ? "Running" : "Stopped"}\n` +
            `<b>Forwarding:</b> ${forwardIcon} ${status.forwarding ? "Active" : "Paused"}\n` +
            `<b>Source channels:</b> ${status.enabledSources}/${status.sourceChannels} enabled\n` +
            `<b>Target channel:</b> <code>${status.targetChannel || "Not set"}</code>`,
            { parse_mode: "HTML", reply_markup: this._quickActionsKeyboard() }
        );

        if (ctx.callbackQuery) {
            await ctx.answerCbQuery();
        }
    }

    async _handleSources(ctx) {
        if (!this.monitorService) {
            return ctx.reply("❌ Monitor service not available.");
        }

        const sources = await this.monitorService.getSources();

        if (sources.channels.length === 0) {
            return ctx.reply(
                "📋 <b>No source channels configured.</b>\n\n" +
                "Use /add <channel> to add a source.\n" +
                "Example: /add @channel_name or /add -1001234567890",
                { parse_mode: "HTML" }
            );
        }

        const channelList = sources.channels.map((c, i) => {
            const icon = c.enabled ? "✅" : "⏸️";
            return `${i + 1}. ${icon} <code>${escapeHtml(String(c.id))}</code>`;
        }).join("\n");
        const keywordList = sources.keywords.length > 0
            ? sources.keywords.join(", ")
            : "(none - forward all)";
        const userList = sources.users.length > 0
            ? sources.users.join(", ")
            : "(none - allow all)";

        // Build buttons for toggle/remove
        const buttons = sources.channels.map((c) => {
            const toggleBtn = c.enabled
                ? { text: `⏸️ Disable`, callback_data: `disable:${c.id}` }
                : { text: `✅ Enable`, callback_data: `enable:${c.id}` };
            return [
                toggleBtn,
                { text: `🗑️ Remove`, callback_data: `remove:${c.id}` }
            ];
        });
        buttons.push([{ text: "🏠 Home", callback_data: "cmd_status" }]);

        await ctx.reply(
            `📋 <b>Source Channels (${sources.channels.length})</b>\n\n` +
            `${channelList}\n\n` +
            `<b>Keywords:</b> ${escapeHtml(keywordList)}\n` +
            `<b>Users:</b> ${escapeHtml(userList)}\n` +
            `<b>Target:</b> <code>${escapeHtml(sources.targetChannel || "Not set")}</code>`,
            { parse_mode: "HTML", reply_markup: { inline_keyboard: buttons } }
        );

        if (ctx.callbackQuery) {
            await ctx.answerCbQuery();
        }
    }

    async _handleAdd(ctx) {
        const channelId = (ctx.message.text || "").replace(/^\/add\s*/i, "").trim();

        if (!channelId) {
            return ctx.reply(
                "📌 Usage: /add <channel>\n\n" +
                "Examples:\n" +
                "• /add @channel_name\n" +
                "• /add -1001234567890"
            );
        }

        if (!this.monitorService) {
            return ctx.reply("❌ Monitor service not available.");
        }

        try {
            const result = await this.monitorService.addSource(channelId);
            await ctx.reply(
                `✅ <b>Source added!</b>\n\n` +
                `Channel: <code>${escapeHtml(channelId)}</code>\n` +
                `Total sources: ${result.channels.length}`,
                { parse_mode: "HTML", reply_markup: this._quickActionsKeyboard() }
            );
        } catch (err) {
            await ctx.reply(`❌ Failed to add source: ${err.message}`);
        }
    }

    async _handleRemove(ctx) {
        const channelId = (ctx.message.text || "").replace(/^\/remove\s*/i, "").trim();

        if (!channelId) {
            return ctx.reply(
                "📌 Usage: /remove <channel>\n\n" +
                "Use /sources to see the list of channels."
            );
        }

        if (!this.monitorService) {
            return ctx.reply("❌ Monitor service not available.");
        }

        try {
            const result = await this.monitorService.deleteSource(channelId);
            await ctx.reply(
                `✅ <b>Source removed!</b>\n\n` +
                `Channel: <code>${escapeHtml(channelId)}</code>\n` +
                `Remaining sources: ${result.channels.length}`,
                { parse_mode: "HTML", reply_markup: this._quickActionsKeyboard() }
            );
        } catch (err) {
            await ctx.reply(`❌ Failed to remove source: ${err.message}`);
        }
    }

    async _handleRemoveSource(ctx) {
        const channelId = ctx.match[1];

        if (!this.monitorService) {
            return ctx.answerCbQuery("Service not available");
        }

        try {
            const result = await this.monitorService.deleteSource(channelId);
            await ctx.answerCbQuery(`Removed: ${channelId}`);
            await ctx.editMessageText(
                `✅ Removed: <code>${escapeHtml(channelId)}</code>\n\n` +
                `Remaining sources: ${result.channels.length}`,
                { parse_mode: "HTML" }
            );
        } catch (err) {
            await ctx.answerCbQuery(`Error: ${err.message}`);
        }
    }

    async _handleHistory(ctx) {
        const userId = ctx.from?.id;

        if (!this.monitorService) {
            return ctx.reply("❌ Monitor service not available.");
        }

        try {
            const history = await this.monitorService.getHistory(userId, 10);

            if (history.length === 0) {
                return ctx.reply("📜 No messages in history yet.", {
                    reply_markup: this._quickActionsKeyboard()
                });
            }

            const lines = history.map((msg, i) => {
                const preview = (msg.message || "").substring(0, 80);
                return `${i + 1}. <b>${escapeHtml(msg.source)}</b>\n   ${escapeHtml(preview)}...`;
            });

            await ctx.reply(
                `📜 <b>Recent Messages (${history.length})</b>\n\n${lines.join("\n\n")}`,
                { parse_mode: "HTML", reply_markup: this._quickActionsKeyboard() }
            );
        } catch (err) {
            await ctx.reply(`❌ Failed to get history: ${err.message}`);
        }

        if (ctx.callbackQuery) {
            await ctx.answerCbQuery();
        }
    }

    async _handleFilters(ctx) {
        const userId = ctx.from?.id;

        if (!this.monitorService) {
            return ctx.reply("❌ Monitor service not available.");
        }

        try {
            const filters = await this.monitorService.getFilters(userId);

            await ctx.reply(
                `🔧 <b>Your Filter Policies</b>\n\n` +
                `<b>Channels:</b> ${filters.channels?.length > 0 ? filters.channels.join(", ") : "(all)"}\n` +
                `<b>Keywords:</b> ${filters.keywords?.length > 0 ? filters.keywords.join(", ") : "(all)"}\n` +
                `<b>Users:</b> ${filters.users?.length > 0 ? filters.users.join(", ") : "(all)"}\n` +
                `<b>Enabled:</b> ${filters.enabled ? "Yes" : "No"}\n\n` +
                `<i>These filters apply to your WebSocket stream (REST API).</i>`,
                { parse_mode: "HTML" }
            );
        } catch (err) {
            await ctx.reply(`❌ Failed to get filters: ${err.message}`);
        }
    }

    async _handleMonitor(ctx) {
        await ctx.reply(
            "🔧 <b>Monitor Control</b>\n\n" +
            "Select an action:",
            {
                parse_mode: "HTML",
                reply_markup: {
                    inline_keyboard: [
                        [{ text: "▶️ Start Monitoring", callback_data: "cmd_start" }],
                        [{ text: "⏹️ Stop Monitoring", callback_data: "cmd_stop" }],
                        [{ text: "📊 Status", callback_data: "cmd_status" }],
                    ]
                }
            }
        );
    }

    async _handleMonitorStart(ctx) {
        if (!this.monitorService) {
            return ctx.answerCbQuery("Service not available");
        }

        try {
            const result = await this.monitorService.start();
            await ctx.answerCbQuery(result.status === "started" ? "Monitoring started!" : "Already running");
            await ctx.editMessageText(
                `▶️ <b>Monitoring ${result.status === "started" ? "Started" : "Already Running"}</b>\n\n` +
                `Watching ${result.channels || "?"} channels.`,
                { parse_mode: "HTML" }
            );
        } catch (err) {
            await ctx.answerCbQuery(`Error: ${err.message}`);
        }
    }

    async _handleMonitorStop(ctx) {
        if (!this.monitorService) {
            return ctx.answerCbQuery("Service not available");
        }

        try {
            const result = await this.monitorService.stop();
            await ctx.answerCbQuery("Monitoring stopped");
            await ctx.editMessageText(
                `⏹️ <b>Monitoring Stopped</b>\n\n` +
                `Use /monitor to start again.`,
                { parse_mode: "HTML" }
            );
        } catch (err) {
            await ctx.answerCbQuery(`Error: ${err.message}`);
        }
    }

    async _handleHelp(ctx) {
        await ctx.reply(
            `🔔 <b>Monitor Bot Help</b>\n\n` +
            `<b>Status & Control:</b>\n` +
            `/start - Welcome and status\n` +
            `/status - Current monitor status\n` +
            `/monitor - Start/stop monitoring\n` +
            `/forward - Pause/resume forwarding\n\n` +
            `<b>Source Management:</b>\n` +
            `/sources - List source channels\n` +
            `/add <channel> - Add source\n` +
            `/remove <channel> - Remove source\n` +
            `/enable <channel> - Enable source\n` +
            `/disable <channel> - Disable source\n\n` +
            `<b>Target Channel:</b>\n` +
            `/target - Show current target\n` +
            `/target <channel> - Set target\n` +
            `/target reset - Reset to default\n\n` +
            `<b>History & Filters:</b>\n` +
            `/history - Recent forwarded messages\n` +
            `/filters - Your filter policies\n\n` +
            `<i>Messages from enabled sources are forwarded to target channel.</i>`,
            { parse_mode: "HTML" }
        );
    }

    // ============================================================
    // NEW RUNTIME MANAGEMENT COMMANDS
    // ============================================================

    async _handleTarget(ctx) {
        const channelId = (ctx.message.text || "").replace(/^\/target\s*/i, "").trim();

        if (!this.monitorService) {
            return ctx.reply("❌ Monitor service not available.");
        }

        if (!channelId) {
            const status = this.monitorService.getStatus();
            return ctx.reply(
                `🎯 <b>Target Channel</b>\n\n` +
                `<b>Current:</b> <code>${escapeHtml(status.targetChannel || "Not set")}</code>\n\n` +
                `<b>Usage:</b>\n` +
                `/target @channel_name - Set target\n` +
                `/target -1001234567890 - Set by ID\n` +
                `/target reset - Reset to config default`,
                { parse_mode: "HTML" }
            );
        }

        try {
            if (channelId.toLowerCase() === "reset") {
                const result = await this.monitorService.resetTargetChannel();
                return ctx.reply(
                    `✅ Target channel reset to config default:\n<code>${escapeHtml(result.targetChannel)}</code>`,
                    { parse_mode: "HTML" }
                );
            }

            const result = await this.monitorService.setTargetChannel(channelId);
            await ctx.reply(
                `✅ <b>Target channel set!</b>\n\n` +
                `New target: <code>${escapeHtml(result.targetChannel)}</code>`,
                { parse_mode: "HTML", reply_markup: this._quickActionsKeyboard() }
            );
        } catch (err) {
            await ctx.reply(`❌ Failed to set target: ${err.message}`);
        }
    }

    async _handleForward(ctx) {
        if (!this.monitorService) {
            return ctx.reply("❌ Monitor service not available.");
        }

        const status = this.monitorService.getStatus();
        const forwardIcon = status.forwarding ? "✅" : "⏸️";

        await ctx.reply(
            `📤 <b>Forwarding Control</b>\n\n` +
            `<b>Status:</b> ${forwardIcon} ${status.forwarding ? "Active" : "Paused"}\n\n` +
            `<i>Toggle forwarding without stopping monitoring.</i>`,
            {
                parse_mode: "HTML",
                reply_markup: {
                    inline_keyboard: [
                        [
                            { text: "✅ Enable", callback_data: "cmd_forward_on" },
                            { text: "⏸️ Pause", callback_data: "cmd_forward_off" }
                        ],
                        [{ text: "🏠 Home", callback_data: "cmd_status" }]
                    ]
                }
            }
        );
    }

    async _handleForwardOn(ctx) {
        if (!this.monitorService) {
            return ctx.answerCbQuery("Service not available");
        }

        try {
            await this.monitorService.setForwarding(true);
            await ctx.answerCbQuery("Forwarding enabled!");
            await ctx.editMessageText(
                `✅ <b>Forwarding Enabled</b>\n\nMessages will now be forwarded to target channel.`,
                { parse_mode: "HTML" }
            );
        } catch (err) {
            await ctx.answerCbQuery(`Error: ${err.message}`);
        }
    }

    async _handleForwardOff(ctx) {
        if (!this.monitorService) {
            return ctx.answerCbQuery("Service not available");
        }

        try {
            await this.monitorService.setForwarding(false);
            await ctx.answerCbQuery("Forwarding paused!");
            await ctx.editMessageText(
                `⏸️ <b>Forwarding Paused</b>\n\nMonitoring continues, but messages won't be forwarded.`,
                { parse_mode: "HTML" }
            );
        } catch (err) {
            await ctx.answerCbQuery(`Error: ${err.message}`);
        }
    }

    async _handleEnable(ctx) {
        const channelId = (ctx.message.text || "").replace(/^\/enable\s*/i, "").trim();

        if (!channelId) {
            return ctx.reply(
                "📌 Usage: /enable <channel>\n\n" +
                "Example: /enable -1001234567890\n\n" +
                "Use /sources to see the list of channels."
            );
        }

        if (!this.monitorService) {
            return ctx.reply("❌ Monitor service not available.");
        }

        try {
            const result = await this.monitorService.enableSource(channelId);
            await ctx.reply(
                `✅ <b>Source enabled!</b>\n\n` +
                `Channel: <code>${escapeHtml(result.channel)}</code>`,
                { parse_mode: "HTML", reply_markup: this._quickActionsKeyboard() }
            );
        } catch (err) {
            await ctx.reply(`❌ Failed to enable source: ${err.message}`);
        }
    }

    async _handleDisable(ctx) {
        const channelId = (ctx.message.text || "").replace(/^\/disable\s*/i, "").trim();

        if (!channelId) {
            return ctx.reply(
                "📌 Usage: /disable <channel>\n\n" +
                "Example: /disable -1001234567890\n\n" +
                "Use /sources to see the list of channels."
            );
        }

        if (!this.monitorService) {
            return ctx.reply("❌ Monitor service not available.");
        }

        try {
            const result = await this.monitorService.disableSource(channelId);
            await ctx.reply(
                `⏸️ <b>Source disabled!</b>\n\n` +
                `Channel: <code>${escapeHtml(result.channel)}</code>\n` +
                `<i>Still monitored but not forwarded.</i>`,
                { parse_mode: "HTML", reply_markup: this._quickActionsKeyboard() }
            );
        } catch (err) {
            await ctx.reply(`❌ Failed to disable source: ${err.message}`);
        }
    }

    async _handleEnableSource(ctx) {
        const channelId = ctx.match[1];

        if (!this.monitorService) {
            return ctx.answerCbQuery("Service not available");
        }

        try {
            await this.monitorService.enableSource(channelId);
            await ctx.answerCbQuery(`Enabled: ${channelId.substring(0, 15)}`);
            // Refresh the sources view
            await this._handleSources(ctx);
        } catch (err) {
            await ctx.answerCbQuery(`Error: ${err.message}`);
        }
    }

    async _handleDisableSource(ctx) {
        const channelId = ctx.match[1];

        if (!this.monitorService) {
            return ctx.answerCbQuery("Service not available");
        }

        try {
            await this.monitorService.disableSource(channelId);
            await ctx.answerCbQuery(`Disabled: ${channelId.substring(0, 15)}`);
            // Refresh the sources view
            await this._handleSources(ctx);
        } catch (err) {
            await ctx.answerCbQuery(`Error: ${err.message}`);
        }
    }
}

module.exports = MonitorBot;
