const Logger = require("./Logger");

const logger = new Logger("RateLimiter");

/**
 * RateLimiter - Queue-based rate limiter for outgoing messages.
 */
class RateLimiter {
    constructor(minIntervalMs = 30000) {
        this.minIntervalMs = minIntervalMs;
        this.queue = [];
        this.isProcessing = false;
        this.lastSentTime = 0;
        logger.info(`Initialized with ${minIntervalMs}ms interval.`);
    }

    /**
     * Enqueue a task to be executed with rate limiting.
     * @param {Function} task - Async function to execute.
     * @returns {Promise} - Resolves when the task is executed.
     */
    enqueue(task) {
        return new Promise((resolve, reject) => {
            this.queue.push({ task, resolve, reject });
            this._processQueue();
        });
    }

    async _processQueue() {
        if (this.isProcessing || this.queue.length === 0) {
            return;
        }

        this.isProcessing = true;

        while (this.queue.length > 0) {
            const now = Date.now();
            const elapsed = now - this.lastSentTime;
            const waitTime = Math.max(0, this.minIntervalMs - elapsed);

            if (waitTime > 0) {
                logger.debug(`Waiting ${waitTime}ms before next task.`);
                await this._sleep(waitTime);
            }

            const { task, resolve, reject } = this.queue.shift();

            try {
                const result = await task();
                this.lastSentTime = Date.now();
                resolve(result);
            } catch (err) {
                logger.error("Task failed:", err);
                reject(err);
            }
        }

        this.isProcessing = false;
    }

    _sleep(ms) {
        return new Promise((resolve) => setTimeout(resolve, ms));
    }
}

module.exports = RateLimiter;
