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

    async def send_message(self, peer, message, parse_mode=None, file=None):
        """Send message using the MAIN client."""
        if not self.connected or not self.main_client:
            logger.warn("Cannot send message, no main client connected")
            return
        
        # Filter out non-sendable media types (like WebPage previews)
        sendable_file = None
        if file:
            from telethon.tl.types import (
                MessageMediaPhoto, MessageMediaDocument,
                MessageMediaWebPage
            )
            # Only send actual media, not web page previews
            if isinstance(file, (MessageMediaPhoto, MessageMediaDocument)):
                sendable_file = file
            elif isinstance(file, MessageMediaWebPage):
                # WebPage previews can't be sent as files, skip
                sendable_file = None
            elif hasattr(file, 'photo') or hasattr(file, 'document'):
                sendable_file = file
        
        # If sending file, don't chunk
        if sendable_file:
            try:
                async with rate_limiter:
                    await self.main_client.send_message(peer, message, parse_mode=parse_mode, file=sendable_file)
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
                    await self.main_client.send_message(peer, chunk, parse_mode=parse_mode)
                logger.debug(f"Sent message to {peer}")
            except Exception as e:
                logger.error(f"Failed to send message to {peer}: {e}")

    async def resolve_entity(self, peer):
        if not self.connected or not self.main_client:
            return None
        try:
            return await self.main_client.get_entity(peer)
        except Exception as e:
            logger.warn(f"Failed to resolve match {peer}: {e}")
            return None

telegram_service = TelegramService()
