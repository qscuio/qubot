const { WebSocketServer } = require("ws");
const { randomUUID } = require("crypto");
const { validateApiKey } = require("./auth");
const Logger = require("../core/Logger");

const logger = new Logger("WebSocket");

/**
 * WebSocketHandler - Handles real-time message streaming.
 * 
 * Clients connect to ws://host:port/ws/monitor?token=<API_KEY>
 * and receive real-time messages from MonitorService.
 */
class WebSocketHandler {
    constructor(config, monitorService) {
        this.config = config;
        this.monitorService = monitorService;
        this.wss = null;
        this.clients = new Map(); // ws -> { userId, filters }
    }

    /**
     * Attach WebSocket server to HTTP server.
     */
    attach(server) {
        this.wss = new WebSocketServer({
            server,
            path: "/ws/monitor"
        });

        this.wss.on("connection", (ws, req) => {
            this._handleConnection(ws, req);
        });

        // Subscribe to MonitorService events
        if (this.monitorService) {
            this.monitorService.on("message", (message) => {
                this._broadcastMessage(message);
            });
        }

        logger.info("WebSocket handler attached at /ws/monitor");
    }

    /**
     * Handle new WebSocket connection.
     */
    async _handleConnection(ws, req) {
        try {
            // Extract token from query string
            const url = new URL(req.url, `http://${req.headers.host}`);
            const token = url.searchParams.get("token");

            if (!token) {
                ws.close(4001, "Missing token");
                return;
            }

            // Validate API key
            const userId = validateApiKey(this.config, token);
            if (!userId) {
                ws.close(4003, "Invalid token");
                return;
            }

            // Get user's filter policies
            let filters = { channels: [], keywords: [], users: [], enabled: true };
            if (this.monitorService) {
                filters = await this.monitorService.getFilters(userId);
            }

            const connectionId = randomUUID();

            // Store client info
            this.clients.set(ws, { userId, filters, connectionId });
            logger.infoMeta("ws_connected", {
                connectionId,
                userId,
                ip: req.socket?.remoteAddress || null
            });

            // Send welcome message
            ws.send(JSON.stringify({
                type: "connected",
                userId,
                filters
            }));

            // Handle messages from client
            ws.on("message", async (data) => {
                await this._handleClientMessage(ws, data);
            });

            // Handle disconnect
            ws.on("close", () => {
                this.clients.delete(ws);
                logger.debugMeta("ws_disconnected", {
                    connectionId,
                    userId
                });
            });

            ws.on("error", (err) => {
                logger.warnMeta("ws_error", {
                    connectionId,
                    userId,
                    error: err.message
                });
                this.clients.delete(ws);
            });

        } catch (err) {
            logger.error("WebSocket connection error", err);
            ws.close(4000, "Internal error");
        }
    }

    /**
     * Handle messages from WebSocket client.
     */
    async _handleClientMessage(ws, data) {
        try {
            const message = JSON.parse(data.toString());
            const clientInfo = this.clients.get(ws);

            if (!clientInfo) return;

            switch (message.type) {
                case "update_filters":
                    // Update user's filter policies
                    if (this.monitorService && message.filters) {
                        const newFilters = await this.monitorService.updateFilters(
                            clientInfo.userId,
                            message.filters
                        );
                        clientInfo.filters = newFilters;
                        logger.infoMeta("ws_filters_updated", {
                            connectionId: clientInfo.connectionId,
                            userId: clientInfo.userId
                        });
                        ws.send(JSON.stringify({
                            type: "filters_updated",
                            filters: newFilters
                        }));
                    }
                    break;

                case "ping":
                    ws.send(JSON.stringify({ type: "pong" }));
                    break;

                default:
                    ws.send(JSON.stringify({
                        type: "error",
                        message: `Unknown message type: ${message.type}`
                    }));
            }
        } catch (err) {
            logger.warn("Failed to parse WebSocket message", err.message);
        }
    }

    /**
     * Broadcast message to connected clients based on their filters.
     */
    _broadcastMessage(message) {
        for (const [ws, clientInfo] of this.clients) {
            if (ws.readyState !== 1) continue; // WebSocket.OPEN

            const { filters } = clientInfo;

            // Skip if user has disabled their stream
            if (!filters.enabled) continue;

            // Apply channel filter
            if (filters.channels?.length > 0) {
                const matchesChannel = filters.channels.some(ch =>
                    ch === message.source ||
                    ch === message.sourceId ||
                    ch === `@${message.source}`
                );
                if (!matchesChannel) continue;
            }

            // Apply keyword filter
            if (filters.keywords?.length > 0) {
                const lowerText = message.text.toLowerCase();
                const hasKeyword = filters.keywords.some(k =>
                    lowerText.includes(k.toLowerCase())
                );
                if (!hasKeyword) continue;
            }

            // Send message to client
            ws.send(JSON.stringify({
                type: "message",
                data: message
            }));
        }
    }

    /**
     * Get connected client count.
     */
    getClientCount() {
        return this.clients.size;
    }

    /**
     * Close all connections.
     */
    close() {
        if (this.wss) {
            this.wss.close();
        }
    }
}

module.exports = WebSocketHandler;
