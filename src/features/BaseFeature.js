const Logger = require("../core/Logger");

/**
 * BaseFeature - Abstract base class for all features.
 * Features should extend this class and implement lifecycle methods.
 */
class BaseFeature {
    /**
     * @param {object} services - { config, telegram }
     */
    constructor(services) {
        this.services = services;
        this.config = services.config;
        this.telegram = services.telegram;
        this.name = this.constructor.name;
        this.logger = new Logger(this.name);
    }

    /**
     * Called when the feature is loaded.
     * Use for setup tasks.
     */
    async onInit() {
        this.logger.debug("onInit called (default implementation).");
    }

    /**
     * Called when the feature is enabled.
     * Use for registering handlers, starting timers, etc.
     */
    async onEnable() {
        this.logger.debug("onEnable called (default implementation).");
    }

    /**
     * Called when the feature is disabled.
     * Use for cleanup tasks.
     */
    async onDisable() {
        this.logger.debug("onDisable called (default implementation).");
    }
}

module.exports = BaseFeature;
