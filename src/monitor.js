const config = require("./config");

/**
 * Checks if the message text contains any of the keywords.
 * @param {string} text - The message text.
 * @returns {boolean} - True if it should be kept.
 */
function shouldKeep(text = "") {
    if (!text) return false;
    if (config.KEYWORDS.length === 0) return true; // If no keywords defined, keep everything? Or nothing? usually keep everything if filter is empty, or maybe nothing. 
    // User request implies filtering. Let's assume if keywords are present, we filter.

    const lowerText = text.toLowerCase();
    return config.KEYWORDS.some((k) => lowerText.includes(k));
}

/**
 * Rewrites the message for the target channel.
 * @param {string} text - Original message text.
 * @param {string} sourceName - Name/Username of the source channel.
 * @returns {string} - Formatted message.
 */
function rewrite(text = "", sourceName = "Source") {
    const cleanText = text.replace(/\s+/g, " ").trim();
    const header = "🔔【New Alert】";

    return `${header}\n\n${cleanText}\n\n— Source: ${sourceName}`;
}

module.exports = {
    shouldKeep,
    rewrite,
};
