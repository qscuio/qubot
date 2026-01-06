import re
from datetime import datetime
from collections import OrderedDict
from typing import Dict, List, Optional
from telethon import events
from app.core.config import settings
from app.core.logger import Logger
from app.core.bot import telegram_service
from app.core.database import db

logger = Logger("MonitorService")

class MonitorService:
    def __init__(self):
        self.is_running = False
        # Changed from list of strings to dict: channel_id -> {id, name, enabled}
        self.channels: Dict[str, dict] = {}
        self.target_channel = settings.TARGET_CHANNEL
        # Deduplication cache: stores (chat_id, message_id) tuples
        # Using OrderedDict to maintain insertion order for LRU eviction
        self._processed_messages = OrderedDict()
        self._max_cache_size = 1000  # Keep last 1000 messages
    
    @property
    def source_channels(self) -> List[str]:
        """Backward compatibility: return list of channel IDs."""
        return list(self.channels.keys())
    
    @property
    def disabled_sources(self) -> set:
        """Return set of disabled channel IDs."""
        return {cid for cid, info in self.channels.items() if not info.get('enabled', True)}

    def get_channel_info(self, channel_id: str) -> Optional[dict]:
        """Get channel info by ID."""
        return self.channels.get(channel_id)
    
    def get_channel_display_name(self, channel_id: str) -> str:
        """Get display name for channel (name if available, else ID)."""
        info = self.channels.get(channel_id)
        if info and info.get('name') and info['name'] != channel_id:
            return info['name']
        return channel_id

    async def initialize(self):
        logger.info("Initializing MonitorService...")
        
        # Load config channels (just IDs)
        config_channels = settings.source_channels_list
        for cid in config_channels:
            if cid not in self.channels:
                self.channels[cid] = {'id': cid, 'name': cid, 'enabled': True}
        
        # Load db channels with names
        if db.pool:
            try:
                rows = await db.pool.fetch("SELECT channel_id, name, enabled FROM monitor_channels")
                for row in rows:
                    self.channels[row['channel_id']] = {
                        'id': row['channel_id'],
                        'name': row['name'] or row['channel_id'],
                        'enabled': row['enabled']
                    }
                logger.info(f"Loaded {len(rows)} channels from database")
            except Exception as e:
                logger.warn(f"Failed to load channels from database: {e}")
        
        logger.info(f"MonitorService initialized with {len(self.channels)} source channels.")

    async def start(self):
        if self.is_running:
            return
        
        if not telegram_service.connected:
            logger.error("Telegram service not connected!")
            return

        # Register handler
        await telegram_service.add_message_handler(self.handle_message)
        self.is_running = True
        logger.info("✅ MonitorService started.")

    async def stop(self):
        self.is_running = False
        logger.info("MonitorService stopped.")
    
    async def resolve_channel_info(self, channel: str) -> dict:
        """Resolve channel ID and name from Telegram."""
        try:
            if telegram_service.main_client:
                # Try to get entity using different formats
                entity = None
                try:
                    # Try as-is first
                    entity = await telegram_service.main_client.get_entity(channel)
                except:
                    # Try with -100 prefix for channels
                    try:
                        entity = await telegram_service.main_client.get_entity(int(f"-100{channel}"))
                    except:
                        pass
                
                if entity:
                    channel_id = str(entity.id)
                    channel_name = getattr(entity, 'title', None) or getattr(entity, 'username', None) or channel
                    return {'id': channel_id, 'name': channel_name}
        except Exception as e:
            logger.warn(f"Could not resolve channel {channel}: {e}")
        
        # Fallback: use input as both
        return {'id': channel, 'name': channel}
    
    async def refresh_channel_names(self):
        """Refresh names for all channels by resolving from Telegram."""
        if not telegram_service.main_client:
            return
        
        updated = 0
        for ch_id, ch_info in self.channels.items():
            # Skip if already has a different name
            if ch_info.get('name') and ch_info['name'] != ch_id:
                continue
            
            try:
                # Try to resolve the actual name
                entity = None
                try:
                    entity = await telegram_service.main_client.get_entity(int(ch_id))
                except:
                    try:
                        entity = await telegram_service.main_client.get_entity(int(f"-100{ch_id}"))
                    except:
                        pass
                
                if entity:
                    new_name = getattr(entity, 'title', None) or getattr(entity, 'username', None)
                    if new_name and new_name != ch_id:
                        ch_info['name'] = new_name
                        updated += 1
                        # Update in database
                        if db.pool:
                            try:
                                await db.pool.execute(
                                    "UPDATE monitor_channels SET name = $2 WHERE channel_id = $1",
                                    ch_id, new_name
                                )
                            except:
                                pass
            except Exception as e:
                logger.debug(f"Could not refresh name for {ch_id}: {e}")
        
        if updated:
            logger.info(f"Refreshed names for {updated} channels")
    
    async def add_source(self, user_id: str, channel: str) -> dict:
        """Add a source channel dynamically. Returns channel info."""
        # Resolve channel info from Telegram
        info = await self.resolve_channel_info(channel)
        channel_id = info['id']
        channel_name = info['name']
        
        if channel_id not in self.channels:
            self.channels[channel_id] = {
                'id': channel_id,
                'name': channel_name,
                'enabled': True
            }
            # Persist to DB
            if db.pool:
                try:
                    await db.pool.execute("""
                        INSERT INTO monitor_channels (channel_id, name, enabled) 
                        VALUES ($1, $2, TRUE) ON CONFLICT (channel_id) 
                        DO UPDATE SET name = $2
                    """, channel_id, channel_name)
                except Exception as e:
                    logger.warn(f"Failed to persist source: {e}")
            logger.info(f"Added source: {channel_name} ({channel_id})")
        
        return self.channels[channel_id]
    
    async def remove_source(self, user_id: str, channel: str):
        """Remove a source channel."""
        # Try to find by ID or by name
        channel_id = channel
        if channel not in self.channels:
            # Search by name
            for cid, info in self.channels.items():
                if info.get('name') == channel:
                    channel_id = cid
                    break
        
        logger.info(f"remove_source: input={channel}, resolved={channel_id}, found={channel_id in self.channels}")
        
        if channel_id in self.channels:
            info = self.channels.pop(channel_id)
            if db.pool:
                try:
                    result = await db.pool.execute("DELETE FROM monitor_channels WHERE channel_id = $1", channel_id)
                    logger.info(f"DB delete result: {result}")
                except Exception as e:
                    logger.warn(f"Failed to remove source from DB: {e}")
            logger.info(f"Removed source: {info.get('name', channel_id)} ({channel_id})")
    
    async def toggle_source(self, channel_id: str, enabled: bool):
        """Enable or disable a source channel."""
        if channel_id in self.channels:
            self.channels[channel_id]['enabled'] = enabled
            if db.pool:
                try:
                    await db.pool.execute(
                        "UPDATE monitor_channels SET enabled = $2 WHERE channel_id = $1",
                        channel_id, enabled
                    )
                except Exception as e:
                    logger.warn(f"Failed to update source: {e}")

    def _normalize_peer_id(self, value):
        if not value: return ""
        text = str(value).strip()
        if text.startswith("-100"): return text[4:]
        if text.startswith("-"): return text[1:]
        return text

    def matches_source(self, source, chat_username, raw_chat_id):
        if not source: return False
        
        # Check username match
        if chat_username:
            if source == chat_username or source == f"@{chat_username}":
                return True
        
        # Check ID match (normalized)
        norm_source = self._normalize_peer_id(source)
        norm_chat = self._normalize_peer_id(raw_chat_id)
        
        if norm_source and norm_chat and norm_source == norm_chat:
            return True
            
        return source == str(raw_chat_id)

    async def handle_message(self, event):
        if not self.is_running:
            return

        try:
            chat = await event.get_chat()
            if not chat:
                return

            chat_title = getattr(chat, 'title', 'Unknown')
            chat_username = getattr(chat, 'username', None)
            chat_id = str(chat.id)
            message_id = event.message.id
            
            # Deduplication: skip if we already processed this message
            dedup_key = (chat.id, message_id)
            if dedup_key in self._processed_messages:
                logger.debug(f"⏭️ Skipping duplicate message {message_id} from {chat_title}")
                return
            
            # Mark as processed (with LRU eviction)
            self._processed_messages[dedup_key] = True
            if len(self._processed_messages) > self._max_cache_size:
                self._processed_messages.popitem(last=False)  # Remove oldest
            
            # Get sender info
            sender = await event.get_sender()
            sender_name = getattr(sender, 'username', None) or getattr(sender, 'first_name', 'Unknown')
            sender_id = str(sender.id) if sender else 'Unknown'
            
            # Message content (truncated)
            msg_text = (event.message.message or '')[:100]
            
            # Detailed debug logging
            client_id = getattr(event.client, 'me', None) 
            client_info = f" [via {client_id.id}]" if client_id else ""
            logger.info(f"📨 MSG{client_info} | Chat: {chat_title} (@{chat_username or chat_id}) | From: {sender_name} ({sender_id}) | Text: {msg_text[:50]}...")

            # 1. Check Source (if configured, otherwise forward all)
            if self.source_channels:
                is_monitored = False
                matching_source = None
                
                for source in self.source_channels:
                    if self.matches_source(source, chat_username, chat_id):
                        is_monitored = True
                        matching_source = source
                        break
                
                if not is_monitored:
                    logger.debug(f"Message not from monitored source: {chat_username or chat_id}")
                    return
                
                if matching_source in self.disabled_sources:
                    logger.debug(f"Source {matching_source} is disabled")
                    return
                
                logger.info(f"📩 Message from monitored source: {chat_title} ({matching_source})")
            else:
                # No source filter - forward all messages
                logger.debug(f"📩 No source filter configured, forwarding from: {chat_title}")

            # 2. Check From Users (if configured)
            from_users = settings.from_users_list
            if from_users:
                sender = await event.get_sender()
                sender_username = getattr(sender, 'username', None)
                sender_id = str(sender.id) if sender else ""
                
                is_allowed = False
                for u in from_users:
                    if u == sender_username or u == f"@{sender_username}" or u == sender_id:
                        is_allowed = True
                        break
                
                if not is_allowed:
                    return

            # 3. Check Keywords
            keywords = settings.keywords_list
            if keywords:
                text = event.message.message or ""
                lower_text = text.lower()
                has_keyword = any(k.lower() in lower_text for k in keywords)
                
                if not has_keyword:
                    return

            # Log match
            logger.info(f"✅ Matched message from {chat_title}")

            # 4. Forward
            if self.target_channel:
                source_name = chat_username or chat_title or chat_id
                
                # Convert to HTML to preserve formatting (links, bold, etc)
                from telethon.extensions import html
                msg_html = html.unparse(event.message.message, event.message.entities)
                
                formatted_msg = self._format_message(msg_html, source_name)
                logger.info(f"📤 Forwarding to {self.target_channel}")
                try:
                    # Convert target_channel to int if it's a numeric string
                    target = self.target_channel
                    if isinstance(target, str) and (target.isdigit() or target.lstrip('-').isdigit()):
                         target = int(target)
                    
                    # Pass media if present
                    await telegram_service.send_message(
                        target, 
                        formatted_msg, 
                        parse_mode='html', 
                        file=event.message.media
                    )
                    logger.info("✅ Message forwarded successfully")
                except Exception as e:
                    logger.error(f"❌ Failed to forward message: {e}")
            else:
                logger.warn("No TARGET_CHANNEL configured, skipping forward")

            # 5. Save History
            await self._save_to_history(chat_title, chat_id, event.message.message)

        except Exception as e:
            logger.error(f"Error handling message: {e}")
            import traceback
            logger.debug(traceback.format_exc())

    def _format_message(self, html_text, source_name):
        return f"🔔【New Alert】\n\n{html_text}\n\n— Source: {source_name}"

    async def _save_to_history(self, source, source_id, message):
        if not db.pool:
            return
        

        # Logic to save for all interested users (simplified for now)
        # Using a default user 0 (system) or checking settings.allowed_users_list
        # Note: DB schema seems to enforce INTEGER for user_id, so we filter for numeric IDs
        users = settings.allowed_users_list or ["0"]
        
        for user_id in users:
            try:
                # Ensure user_id is numeric if DB requires integer
                if str(user_id).isdigit() or (isinstance(user_id, str) and user_id.lstrip('-').isdigit()):
                    uid_val = int(user_id)
                    await db.pool.execute("""
                        INSERT INTO monitor_history (user_id, source, source_id, message, created_at)
                        VALUES ($1, $2, $3, $4, NOW())
                    """, uid_val, source, str(source_id), message)
            except Exception as e:
                logger.warn(f"Failed to save history for {user_id}: {e}")


monitor_service = MonitorService()
