const fs = require("fs");
const path = require("path");
const Logger = require("./Logger");

const logger = new Logger("FeatureManager");

/**
 * FeatureManager - Discovers, loads, and manages features.
 */
class FeatureManager {
    constructor(services) {
        this.services = services; // { config, storage, botManager, telegram }
        this.features = new Map();
    }

    /**
     * Load all features from the features directory.
     */
    async loadFeatures() {
        const featuresDir = path.join(__dirname, "..", "features");

        if (!fs.existsSync(featuresDir)) {
            logger.warn("Features directory does not exist. No features loaded.");
            return;
        }

        const entries = fs.readdirSync(featuresDir, { withFileTypes: true });

        for (const entry of entries) {
            // Skip BaseFeature.js
            if (entry.name === "BaseFeature.js") continue;

            let featurePath;
            if (entry.isDirectory()) {
                // Look for <name>Feature.js inside the directory
                const files = fs.readdirSync(path.join(featuresDir, entry.name));
                const featureFile = files.find((f) => f.endsWith("Feature.js"));
                if (featureFile) {
                    featurePath = path.join(featuresDir, entry.name, featureFile);
                }
            } else if (entry.isFile() && entry.name.endsWith("Feature.js")) {
                featurePath = path.join(featuresDir, entry.name);
            }

            if (featurePath) {
                await this._loadFeature(featurePath);
            }
        }
    }

    async _loadFeature(featurePath) {
        try {
            const FeatureClass = require(featurePath);
            const feature = new FeatureClass(this.services);

            await feature.onInit();
            this.features.set(feature.name, feature);
            logger.info(`✅ Loaded feature: ${feature.name}`);
        } catch (err) {
            logger.error(`Failed to load feature from ${featurePath}`, err);
        }
    }

    /**
     * Enable all loaded features.
     */
    async enableAll() {
        for (const [name, feature] of this.features) {
            try {
                await feature.onEnable();
                logger.info(`▶️ Enabled feature: ${name}`);
            } catch (err) {
                logger.error(`Failed to enable feature: ${name}`, err);
            }
        }
    }

    /**
     * Disable all loaded features.
     */
    async disableAll() {
        for (const [name, feature] of this.features) {
            try {
                await feature.onDisable();
                logger.info(`⏹️ Disabled feature: ${name}`);
            } catch (err) {
                logger.error(`Failed to disable feature: ${name}`, err);
            }
        }
    }

    getFeature(name) {
        return this.features.get(name);
    }
}

module.exports = FeatureManager;
