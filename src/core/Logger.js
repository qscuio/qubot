/**
 * Logger - Simple logging utility with levels.
 */
class Logger {
    constructor(name = "App") {
        this.name = name;
        this.level = process.env.LOG_LEVEL || "info";
        this.levels = { debug: 0, info: 1, warn: 2, error: 3 };
    }

    _shouldLog(level) {
        return this.levels[level] >= this.levels[this.level];
    }

    _format(level, message) {
        const timestamp = new Date().toISOString();
        return `[${timestamp}] [${level.toUpperCase()}] [${this.name}] ${message}`;
    }

    _formatMeta(level, message, meta) {
        const timestamp = new Date().toISOString();
        return JSON.stringify({
            timestamp,
            level,
            logger: this.name,
            message,
            ...meta
        });
    }

    debug(message) {
        if (this._shouldLog("debug")) {
            console.log(this._format("debug", message));
        }
    }

    debugMeta(message, meta = {}) {
        if (this._shouldLog("debug")) {
            console.log(this._formatMeta("debug", message, meta));
        }
    }

    info(message) {
        if (this._shouldLog("info")) {
            console.log(this._format("info", message));
        }
    }

    infoMeta(message, meta = {}) {
        if (this._shouldLog("info")) {
            console.log(this._formatMeta("info", message, meta));
        }
    }

    warn(message) {
        if (this._shouldLog("warn")) {
            console.warn(this._format("warn", message));
        }
    }

    warnMeta(message, meta = {}) {
        if (this._shouldLog("warn")) {
            console.warn(this._formatMeta("warn", message, meta));
        }
    }

    error(message, err = null) {
        if (this._shouldLog("error")) {
            console.error(this._format("error", message));
            if (err) console.error(err);
        }
    }

    errorMeta(message, meta = {}, err = null) {
        if (this._shouldLog("error")) {
            console.error(this._formatMeta("error", message, meta));
            if (err) console.error(err);
        }
    }

    child(name) {
        return new Logger(`${this.name}:${name}`);
    }
}

module.exports = Logger;
