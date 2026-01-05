/**
 * API module exports.
 */

const ApiServer = require("./ApiServer");
const WebSocketHandler = require("./WebSocketHandler");
const { createAuthMiddleware, validateApiKey } = require("./auth");

module.exports = {
    ApiServer,
    WebSocketHandler,
    createAuthMiddleware,
    validateApiKey
};
