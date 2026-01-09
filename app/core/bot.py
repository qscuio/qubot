from telethon import TelegramClient, events
from telethon.sessions import StringSession
from app.core.config import settings
from app.core.logger import Logger
from app.core.rate_limiter import rate_limiter
from app.core.telegram_utils import chunk_message
import asyncio

logger = Logger("TelegramService")

class TelegramService:
    def __init__(self):
        self.clients = [] # List of TelegramClient
        self.main_client: TelegramClient = None # References the primary client for sending
        self.connected = False
        self._event_handlers = []
        # Store handlers to register on new clients
        self._pending_handlers = []
        # Track our own user IDs (to avoid forwarding our own messages)
        self.own_user_ids: set[int] = set()

    def _normalize_peer_id(self, value):
        if value is None:
            return None
        text = str(value).strip()
        if text.startswith("-100"):
            return text[4:]
        if text.startswith("-"):
            return text[1:]
        return text

    def _extract_peer_identity(self, peer):
        if peer is None:
            return (None, None)

        peer_id = None
        username = None

        for attr in ("id", "channel_id", "user_id", "chat_id"):
            if hasattr(peer, attr):
                peer_id = getattr(peer, attr, None)
                if peer_id is not None:
                    break

        if hasattr(peer, "username"):
            username = getattr(peer, "username", None)

        if peer_id is None:
            if isinstance(peer, int):
                peer_id = peer
            elif isinstance(peer, str):
                cleaned = peer.strip()
                if cleaned.lstrip("-").isdigit():
                    peer_id = cleaned
                else:
                    username = cleaned[1:] if cleaned.startswith("@") else cleaned

        return (self._normalize_peer_id(peer_id), username)

    async def start(self):
        # Collect all session configs from SESSIONS_JSON
        sessions_to_init = []
        
        # Debug: log raw value
        logger.info(f"SESSIONS_JSON raw value present: {bool(settings.SESSIONS_JSON)}")
        logger.info(f"sessions_list parsed: {len(settings.sessions_list)} items")
        
        for sess_cfg in settings.sessions_list:
            if sess_cfg.get("session") and sess_cfg.get("api_id") and sess_cfg.get("api_hash"):
                sessions_to_init.append(sess_cfg)
            else:
                logger.warn(f"Skipping invalid session config (missing keys): {list(sess_cfg.keys())}")

        if not sessions_to_init:
            logger.error("No session configs found. Please set SESSIONS_JSON (or TG_SESSIONS_JSON).")
            return

        logger.info(f"Connecting {len(sessions_to_init)} Telegram clients...")

        for i, config in enumerate(sessions_to_init):
            try:
                # receive_updates=True ensures we get updates even when not using run_until_disconnected
                client = TelegramClient(
                    StringSession(config["session"]),
                    config["api_id"],
                    config["api_hash"],
                    receive_updates=True  # Important for real-time updates
                )
                await client.connect()

                if not await client.is_user_authorized():
                    logger.error(f"Session {i} is NOT authorized. Skipping.")
                    continue

                me = await client.get_me()
                logger.info(f"✅ Connected client {i} as {me.username or me.first_name} (ID: {me.id})")
                
                # Track our own user ID to avoid forwarding our own messages
                self.own_user_ids.add(me.id)
                
                self.clients.append(client)
                
                # First valid client is the main client
                if not self.main_client:
                    self.main_client = client

                # Sync dialogs for proper channel access
                await self._sync_dialogs(client, i)
                
                # Force catch up any pending updates immediately
                try:
                    await client.catch_up()
                    logger.info(f"[{i}] Caught up on pending updates")
                except Exception as e:
                    logger.debug(f"[{i}] catch_up error (usually fine): {e}")
                
            except Exception as e:
                logger.error(f"Failed to connect client {i}", e)

        if self.clients:
            self.connected = True
            logger.info(f"✅ Total {len(self.clients)} clients connected.")
        else:
            logger.error("❌ No clients could be connected.")

    async def _sync_dialogs(self, client, index):
        """
        Sync dialogs for a specific client.
        """
        try:
            logger.info(f"[{index}] Syncing dialogs...")
            dialogs = await client.get_dialogs()
            channels = [d for d in dialogs if d.is_channel or d.is_group]
            logger.info(f"[{index}] Synced {len(dialogs)} dialogs ({len(channels)} channels/groups)")
        except Exception as e:
            logger.warn(f"[{index}] Failed to sync dialogs: {e}")

    async def stop(self):
        for i, client in enumerate(self.clients):
            await client.disconnect()
            logger.info(f"Disconnected client {i}")
        self.clients = []
        self.main_client = None
        self.connected = False

    async def add_message_handler(self, callback):
        """
        Add a generic message handler to ALL clients.
        """
        if not self.clients:
            logger.warn("No clients initialized yet. Handler will be added when clients start (if this is called before start, unexpected).")
            # In current flow, start() matches first. But let's just register on existing.
        
        # Prevent duplicate registration logic is tricky with multiple clients.
        # We'll rely on the caller not calling this multiple times or just add to all.
        if callback in self._pending_handlers:
            return
            
        self._pending_handlers.append(callback)

        for i, client in enumerate(self.clients):
            self._register_handler_on_client(client, callback, i)

    def _register_handler_on_client(self, client, callback, index):
        @client.on(events.NewMessage())
        async def handler(event):
            await callback(event)
        logger.info(f"Registered message handler on client {index}")

    async def send_message(self, peer, message, parse_mode=None, file=None, link_preview=None):
        """Send message using the MAIN client."""
        if not self.connected or not self.main_client:
            logger.warn("Cannot send message, no main client connected")
            return
        
        # Try to resolve the peer entity first
        resolved_peer = peer
        try:
            # For channel IDs (especially with -100 prefix), we need to resolve the entity
            if isinstance(peer, (str, int)):
                resolved_peer = await self.main_client.get_entity(peer)
        except Exception as e:
            logger.warn(f"Could not resolve peer {peer}: {e}")
            # Continue with original peer, might still work for some cases
        
        # Process media types
        sendable_file = None
        enable_link_preview = True  # Default: allow link previews
        if link_preview is not None:
            enable_link_preview = bool(link_preview)
        
        if file:
            from telethon.tl.types import (
                MessageMediaPhoto, MessageMediaDocument,
                MessageMediaWebPage
            )
            # Photos and documents can be sent as files
            if isinstance(file, (MessageMediaPhoto, MessageMediaDocument)):
                sendable_file = file
            elif isinstance(file, MessageMediaWebPage):
                # WebPage previews - Telegram will regenerate from URLs in text
                # Just enable link preview, the URLs in HTML will create the preview
                sendable_file = None
            else:
                logger.debug(f"Skipping unsupported media type: {type(file).__name__}")
        
        # If sending file, don't chunk
        if sendable_file:
            try:
                async with rate_limiter:
                    await self.main_client.send_message(resolved_peer, message, parse_mode=parse_mode, file=sendable_file)
                logger.debug(f"Sent message with media to {peer}")
                return
            except Exception as e:
                logger.error(f"Failed to send media to {peer}: {e}")
                # Fall through to send without media

        # Chunk long messages
        chunks = chunk_message(message, max_length=4096)
        
        for chunk in chunks:
            try:
                async with rate_limiter:
                    await self.main_client.send_message(resolved_peer, chunk, parse_mode=parse_mode, link_preview=enable_link_preview)
                logger.debug(f"Sent message to {peer}")
            except Exception as e:
                logger.error(f"Failed to send message to {peer}: {e}")

    async def forward_messages(self, peer, messages, from_peer=None):
        """Forward messages using the MAIN client."""
        if not self.connected or not self.main_client:
            logger.warn("Cannot forward messages, no main client connected")
            return

        if from_peer is not None:
            peer_id, peer_username = self._extract_peer_identity(peer)
            from_id, from_username = self._extract_peer_identity(from_peer)
            if (peer_id and from_id and peer_id == from_id) or (
                peer_username and from_username and peer_username.lower() == from_username.lower()
            ):
                logger.debug(
                    f"Skipping forward to source peer "
                    f"(peer_id={peer_id}, from_id={from_id}, peer_username={peer_username}, from_username={from_username})"
                )
                return

        try:
            async with rate_limiter:
                await self.main_client.forward_messages(peer, messages, from_peer=from_peer)
            logger.debug(f"Forwarded message(s) to {peer}")
        except Exception as e:
            logger.error(f"Failed to forward message(s) to {peer}: {e}")

    async def resolve_entity(self, peer):
        if not self.connected or not self.main_client:
            return None
        try:
            return await self.main_client.get_entity(peer)
        except Exception as e:
            logger.warn(f"Failed to resolve match {peer}: {e}")
            return None

telegram_service = TelegramService()
