const App = require("./core/App");

const app = new App();

app.start().catch((err) => {
    console.error("Fatal error during startup:", err);
    process.exit(1);
});

// Graceful shutdown
process.on("SIGINT", async () => {
    await app.stop();
    process.exit(0);
});

process.on("SIGTERM", async () => {
    await app.stop();
    process.exit(0);
});

process.on("unhandledRejection", (reason, promise) => {
    console.error("Unhandled Rejection at:", promise, "reason:", reason);
});
