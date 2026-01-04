const express = require("express");
const http = require("http");
const { randomUUID } = require("crypto");
const Logger = require("../core/Logger");
const { createAuthMiddleware } = require("./auth");
const WebSocketHandler = require("./WebSocketHandler");

const logger = new Logger("ApiServer");

/**
 * ApiServer - REST API server for QuBot.
 * 
 * Provides endpoints for AI chat, RSS subscriptions, and channel monitoring.
 * Also handles WebSocket connections for real-time message streaming.
 */
class ApiServer {
    constructor(config, services) {
        this.config = config;
        this.services = services;
        this.app = express();
        this.server = null;
        this.port = config.get("API_PORT") || 3001;
        this.wsHandler = null;

        this._setupMiddleware();
        this._setupRoutes();
    }

    _setupMiddleware() {
        this.app.use(express.json());

        this.app.use((req, res, next) => {
            req.requestId = req.headers["x-request-id"] || randomUUID();
            res.setHeader("x-request-id", req.requestId);

            const start = Date.now();
            res.on("finish", () => {
                logger.infoMeta("api_request", {
                    requestId: req.requestId,
                    method: req.method,
                    path: req.path,
                    status: res.statusCode,
                    userId: req.userId ?? null,
                    durationMs: Date.now() - start
                });
            });

            next();
        });

        // CORS for browser clients
        this.app.use((req, res, next) => {
            res.header("Access-Control-Allow-Origin", "*");
            res.header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS");
            res.header("Access-Control-Allow-Headers", "Content-Type, Authorization");
            if (req.method === "OPTIONS") {
                return res.sendStatus(200);
            }
            next();
        });

        // Request logging
        this.app.use((req, res, next) => {
            logger.debugMeta("api_request_start", {
                requestId: req.requestId,
                method: req.method,
                path: req.path
            });
            next();
        });
    }

    _setupRoutes() {
        const auth = createAuthMiddleware(this.config);

        // Public routes
        this.app.get("/health", (req, res) => {
            res.json({
                status: "ok",
                timestamp: new Date().toISOString(),
                services: {
                    ai: !!this.services.ai,
                    rss: !!this.services.rss,
                    monitor: !!this.services.monitor
                }
            });
        });

        // Protected API routes
        this.app.use("/api", auth);

        // === AI Routes ===
        this._setupAiRoutes();

        // === RSS Routes ===
        this._setupRssRoutes();

        // === Monitor Routes ===
        this._setupMonitorRoutes();

        // === System Routes ===
        this.app.get("/api/status", (req, res) => {
            res.json({
                userId: req.userId,
                services: {
                    ai: !!this.services.ai,
                    rss: !!this.services.rss,
                    monitor: this.services.monitor?.getStatus() || null
                },
                wsClients: this.wsHandler?.getClientCount() || 0
            });
        });

        // Error handler
        this.app.use((err, req, res, next) => {
            logger.errorMeta("api_error", {
                requestId: req.requestId,
                path: req.path,
                userId: req.userId ?? null
            }, err);
            res.status(500).json({
                error: "Internal Server Error",
                message: err.message
            });
        });
    }

    _setupAiRoutes() {
        const ai = this.services.ai;
        if (!ai) return;

        // Get AI settings
        this.app.get("/api/ai/settings", async (req, res) => {
            try {
                const settings = await ai.getSettings(req.userId);
                res.json(settings);
            } catch (err) {
                res.status(500).json({ error: err.message });
            }
        });

        // Update AI settings
        this.app.put("/api/ai/settings", async (req, res) => {
            try {
                const { provider, model } = req.body;
                const settings = await ai.updateSettings(req.userId, provider, model);
                res.json(settings);
            } catch (err) {
                res.status(500).json({ error: err.message });
            }
        });

        // List providers
        this.app.get("/api/ai/providers", (req, res) => {
            res.json({ providers: ai.listProviders() });
        });

        // Get models
        this.app.get("/api/ai/models", async (req, res) => {
            try {
                const settings = await ai.getSettings(req.userId);
                const models = await ai.getModels(settings.provider);
                res.json({ provider: settings.provider, models });
            } catch (err) {
                res.status(500).json({ error: err.message });
            }
        });

        // Send message
        this.app.post("/api/ai/chat", async (req, res) => {
            try {
                const { message } = req.body;
                if (!message) {
                    return res.status(400).json({ error: "Message is required" });
                }
                const response = await ai.chat(req.userId, message);
                res.json(response);
            } catch (err) {
                res.status(500).json({ error: err.message });
            }
        });

        // List chats
        this.app.get("/api/ai/chats", async (req, res) => {
            try {
                const limit = parseInt(req.query.limit, 10) || 10;
                const chats = await ai.getChats(req.userId, limit);
                res.json({ chats });
            } catch (err) {
                res.status(500).json({ error: err.message });
            }
        });

        // Create chat
        this.app.post("/api/ai/chats", async (req, res) => {
            try {
                const chat = await ai.createChat(req.userId);
                res.json(chat);
            } catch (err) {
                res.status(500).json({ error: err.message });
            }
        });

        // Get chat with messages
        this.app.get("/api/ai/chats/:id", async (req, res) => {
            try {
                const chatId = parseInt(req.params.id, 10);
                const limit = parseInt(req.query.limit, 10) || 50;
                const chat = await ai.getChat(req.userId, chatId, limit);
                if (!chat) {
                    return res.status(404).json({ error: "Chat not found" });
                }
                res.json(chat);
            } catch (err) {
                res.status(500).json({ error: err.message });
            }
        });

        // Update/switch chat
        this.app.put("/api/ai/chats/:id", async (req, res) => {
            try {
                const chatId = parseInt(req.params.id, 10);
                const { title } = req.body;
                const chat = await ai.switchChat(req.userId, chatId, title);
                res.json(chat);
            } catch (err) {
                res.status(500).json({ error: err.message });
            }
        });

        // Clear chat messages
        this.app.delete("/api/ai/chats/:id/messages", async (req, res) => {
            try {
                const chatId = parseInt(req.params.id, 10);
                const result = await ai.clearChat(chatId);
                res.json(result);
            } catch (err) {
                res.status(500).json({ error: err.message });
            }
        });

        // Export chat
        this.app.post("/api/ai/chats/:id/export", async (req, res) => {
            try {
                const chatId = parseInt(req.params.id, 10);
                const result = await ai.exportChat(req.userId, chatId);
                res.json(result);
            } catch (err) {
                res.status(500).json({ error: err.message });
            }
        });

        logger.info("AI routes registered");
    }

    _setupRssRoutes() {
        const rss = this.services.rss;
        if (!rss) return;

        // List subscriptions
        this.app.get("/api/rss/subscriptions", async (req, res) => {
            try {
                const subscriptions = await rss.getSubscriptions(req.userId);
                res.json({ subscriptions });
            } catch (err) {
                res.status(500).json({ error: err.message });
            }
        });

        // Subscribe to feed
        this.app.post("/api/rss/subscriptions", async (req, res) => {
            try {
                const { url } = req.body;
                if (!url) {
                    return res.status(400).json({ error: "URL is required" });
                }
                const result = await rss.subscribe(req.userId, url);
                res.json(result);
            } catch (err) {
                res.status(400).json({ error: err.message });
            }
        });

        // Unsubscribe
        this.app.delete("/api/rss/subscriptions/:id", async (req, res) => {
            try {
                const result = await rss.unsubscribe(req.userId, req.params.id);
                res.json(result);
            } catch (err) {
                res.status(400).json({ error: err.message });
            }
        });

        // Validate feed
        this.app.post("/api/rss/validate", async (req, res) => {
            try {
                const { url } = req.body;
                if (!url) {
                    return res.status(400).json({ error: "URL is required" });
                }
                const result = await rss.validateFeed(url);
                res.json(result);
            } catch (err) {
                res.status(500).json({ error: err.message });
            }
        });

        logger.info("RSS routes registered");
    }

    _setupMonitorRoutes() {
        const monitor = this.services.monitor;
        if (!monitor) return;

        // Get sources
        this.app.get("/api/monitor/sources", async (req, res) => {
            try {
                const sources = await monitor.getSources();
                res.json(sources);
            } catch (err) {
                res.status(500).json({ error: err.message });
            }
        });

        // Add source
        this.app.post("/api/monitor/sources", async (req, res) => {
            try {
                const { channelId } = req.body;
                if (!channelId) {
                    return res.status(400).json({ error: "channelId is required" });
                }
                const result = await monitor.addSource(channelId);
                res.json(result);
            } catch (err) {
                res.status(500).json({ error: err.message });
            }
        });

        // Delete source
        this.app.delete("/api/monitor/sources/:id", async (req, res) => {
            try {
                const result = await monitor.deleteSource(req.params.id);
                res.json(result);
            } catch (err) {
                res.status(500).json({ error: err.message });
            }
        });

        // Get filters
        this.app.get("/api/monitor/filters", async (req, res) => {
            try {
                const filters = await monitor.getFilters(req.userId);
                res.json(filters);
            } catch (err) {
                res.status(500).json({ error: err.message });
            }
        });

        // Update filters
        this.app.put("/api/monitor/filters", async (req, res) => {
            try {
                const filters = await monitor.updateFilters(req.userId, req.body);
                res.json(filters);
            } catch (err) {
                res.status(500).json({ error: err.message });
            }
        });

        // Get history
        this.app.get("/api/monitor/history", async (req, res) => {
            try {
                const limit = parseInt(req.query.limit, 10) || 50;
                const history = await monitor.getHistory(req.userId, limit);
                res.json({ history });
            } catch (err) {
                res.status(500).json({ error: err.message });
            }
        });

        // Start monitoring
        this.app.post("/api/monitor/start", async (req, res) => {
            try {
                const result = await monitor.start();
                res.json(result);
            } catch (err) {
                res.status(500).json({ error: err.message });
            }
        });

        // Stop monitoring
        this.app.post("/api/monitor/stop", async (req, res) => {
            try {
                const result = await monitor.stop();
                res.json(result);
            } catch (err) {
                res.status(500).json({ error: err.message });
            }
        });

        logger.info("Monitor routes registered");
    }

    async start() {
        return new Promise((resolve) => {
            this.server = http.createServer(this.app);

            // Attach WebSocket handler
            if (this.services.monitor) {
                this.wsHandler = new WebSocketHandler(this.config, this.services.monitor);
                this.wsHandler.attach(this.server);
            }

            this.server.listen(this.port, () => {
                logger.info(`🌐 API server running on port ${this.port}`);
                logger.info(`📡 Health check: http://localhost:${this.port}/health`);
                logger.info(`🔌 WebSocket: ws://localhost:${this.port}/ws/monitor`);
                resolve();
            });
        });
    }

    async stop() {
        if (this.wsHandler) {
            this.wsHandler.close();
        }
        if (this.server) {
            return new Promise((resolve) => {
                this.server.close(resolve);
            });
        }
    }

    getApp() {
        return this.app;
    }
}

module.exports = ApiServer;
