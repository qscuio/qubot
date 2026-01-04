/**
 * TelegramUtils - Utilities for Telegram message handling.
 */

const MAX_MESSAGE_LENGTH = 3500;
const CHUNK_DELAY_MS = 800;

/**
 * Escape HTML special characters.
 */
function escapeHtml(str) {
    if (!str) return "";
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
}

/**
 * Convert Markdown to Telegram HTML.
 */
function markdownToHtml(str) {
    if (!str) return "";
    return escapeHtml(str)
        // Bold: **text** or __text__
        .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
        .replace(/__(.+?)__/g, "<b>$1</b>")
        // Italic: *text* or _text_
        .replace(/\*(.+?)\*/g, "<i>$1</i>")
        .replace(/_(.+?)_/g, "<i>$1</i>")
        // Code blocks: ```code```
        .replace(/```[\w]*\n?([\s\S]+?)```/g, "<pre>$1</pre>")
        // Inline code: `code`
        .replace(/`(.+?)`/g, "<code>$1</code>")
        // Headers: # text
        .replace(/^#{1,6}\s+(.+)$/gm, "<b>$1</b>")
        // Lists: * or - at start of line
        .replace(/^\s*[\*\-]\s+(.+)$/gm, "• $1");
}

/**
 * Split text into chunks, preferring newlines, then spaces.
 */
function splitIntoChunks(text, maxLength = MAX_MESSAGE_LENGTH) {
    const chunks = [];
    let remaining = text;

    while (remaining.length > 0) {
        if (remaining.length <= maxLength) {
            chunks.push(remaining);
            break;
        }

        // Find best split point
        let splitAt = remaining.lastIndexOf("\n", maxLength);
        if (splitAt < maxLength * 0.3) {
            splitAt = remaining.lastIndexOf(" ", maxLength);
        }
        if (splitAt < maxLength * 0.3) {
            splitAt = maxLength;
        }

        chunks.push(remaining.substring(0, splitAt));
        remaining = remaining.substring(splitAt).trimStart();
    }

    return chunks;
}

/**
 * Sleep for specified milliseconds.
 */
function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Send a long HTML message, split into chunks with delays.
 * @param {Context} ctx - Telegraf context
 * @param {string} text - Text to send (HTML formatted)
 */
async function sendLongHtmlMessage(ctx, text) {
    const chunks = splitIntoChunks(text);

    for (let i = 0; i < chunks.length; i++) {
        try {
            await ctx.reply(chunks[i], { parse_mode: "HTML" });
        } catch (err) {
            // If HTML parsing fails, send as plain text
            if (err.message?.includes("parse")) {
                const plainText = chunks[i].replace(/<[^>]*>/g, "");
                await ctx.reply(plainText);
            } else {
                throw err;
            }
        }

        // Delay between chunks for rate limiting
        if (i < chunks.length - 1) {
            await sleep(CHUNK_DELAY_MS);
        }
    }
}

/**
 * Send a long message with markdown conversion.
 * @param {Context} ctx - Telegraf context
 * @param {string} text - Text in markdown format
 * @param {string} prefix - Optional prefix (e.g., "💬 *Provider:*\n\n")
 */
async function sendLongMessage(ctx, text, prefix = "") {
    const htmlText = prefix + markdownToHtml(text);
    await sendLongHtmlMessage(ctx, htmlText);
}

module.exports = {
    escapeHtml,
    markdownToHtml,
    splitIntoChunks,
    sendLongHtmlMessage,
    sendLongMessage,
    sleep,
    MAX_MESSAGE_LENGTH,
    CHUNK_DELAY_MS,
};
