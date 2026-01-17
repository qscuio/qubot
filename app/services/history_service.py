import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from telethon import TelegramClient
from telethon.tl.types import Message, MessageMediaPhoto, MessageMediaDocument, PeerChannel, PeerChat, PeerUser

from app.core.config import settings
from app.core.database import db
from app.core.logger import Logger
from app.core.bot import telegram_service

logger = Logger("HistoryService")

class HistoryService:
    def __init__(self):
        self._processed_files = set()

    async def _get_client(self) -> Optional[TelegramClient]:
        """Get the main Telegram client."""
        if not telegram_service.connected or not telegram_service.main_client:
            logger.warn("Telegram client not connected")
            return None
        return telegram_service.main_client

    async def _find_client_for_entity(self, peer_id: str) -> tuple[Optional[TelegramClient], Any]:
        """
        Find a client that can access the given entity.
        Returns (client, entity) or (None, None).
        """
        # Normalize ID
        check_id = peer_id
        if isinstance(check_id, str):
            check_id = check_id.strip()
            if check_id.lstrip('-').isdigit():
                check_id = int(check_id)

        # Try all connected clients
        for i, client in enumerate(telegram_service.clients):
            try:
                # Try direct resolution first
                entity = await client.get_entity(check_id)
                logger.info(f"✅ Found entity {check_id} using client {i}")
                return client, entity
            except Exception:
                # If not found, try refreshing dialogs for this client
                try:
                    await client.get_dialogs()
                    entity = await client.get_entity(check_id)
                    logger.info(f"✅ Found entity {check_id} using client {i} (after dialog refresh)")
                    return client, entity
                except Exception:
                    continue
        
        logger.warn(f"❌ Entity {peer_id} NOT found in any of {len(telegram_service.clients)} clients")
        return None, None

    async def _resolve_entity(self, client: TelegramClient, peer_id: str):
        """
        Legacy method, kept for compatibility but now just wraps get_entity with logging.
        """
        try:
            # Normalize ID
            if isinstance(peer_id, str):
                peer_id = peer_id.strip()
                if peer_id.lstrip('-').isdigit():
                    peer_id = int(peer_id)
            
            # Try direct resolution
            try:
                return await client.get_entity(peer_id)
            except Exception as e:
                if "Could not find the input entity" in str(e):
                    logger.info(f"Entity {peer_id} not in cache, fetching dialogs...")
                    dialogs = await client.get_dialogs()
                    logger.info(f"Fetched {len(dialogs)} dialogs")
                    
                    # Debug: Check if peer is in dialogs
                    found = False
                    check_id = peer_id
                    if isinstance(check_id, int) and str(check_id).startswith('-100'):
                        check_id = int(str(check_id)[4:])
                        
                    debug_lines = []
                    for d in dialogs:
                        e_id = d.entity.id
                        debug_lines.append(f"  - Dialog: {d.name} ({e_id})")
                        
                        if e_id == peer_id or e_id == check_id:
                            logger.info(f"✅ Found entity in dialogs: {d.name} ({e_id})")
                            found = True
                            # We found it, no need to log the rest unless we want to be very verbose
                            break
                    
                    if not found:
                        logger.warn(f"❌ Entity {peer_id} NOT found in {len(dialogs)} dialogs. Is the bot a member?")
                        logger.info("Available dialogs:\n" + "\n".join(debug_lines))
                        
                    return await client.get_entity(peer_id)
                raise e
        except Exception as e:
            logger.error(f"Failed to resolve entity {peer_id}: {e}")
            raise e

    async def forward_history_videos(self, source_id: str, limit: int = 1000) -> Dict[str, Any]:
        """
        Forward all video files from source to FILE_TARGET_GROUP.
        """
        target_group = settings.FILE_TARGET_GROUP
        if not target_group:
            return {"status": "error", "message": "FILE_TARGET_GROUP not configured"}

        try:
            # Find a client that can see the source
            client, entity = await self._find_client_for_entity(source_id)
            
            if not client or not entity:
                return {"status": "error", "message": f"Could not find source {source_id} in any connected session"}

            # Log identity of the successful client
            try:
                me = await client.get_me()
                logger.info(f"Using Client: {me.first_name} (ID: {me.id}, Bot: {me.bot})")
            except Exception:
                pass

            logger.info(f"Resolved source: {getattr(entity, 'title', source_id)} ({entity.id})")

            # Resolve target entity using the SAME client
            try:
                target_entity = await client.get_entity(int(target_group) if target_group.lstrip('-').isdigit() else target_group)
                logger.info(f"Resolved target: {getattr(target_entity, 'title', target_group)} ({target_entity.id})")
            except Exception as e:
                return {"status": "error", "message": f"Failed to resolve target {target_group} with selected client: {e}"}

            count = 0
            forwarded = 0
            
            logger.info(f"Starting video forward from {source_id} to {target_group} (limit={limit})")
            
            # Iterate from oldest to newest (reverse=True)
            async for message in client.iter_messages(entity, limit=limit, reverse=True):
                if not message.file:
                    continue
                
                # Check if it's a video
                is_video = False
                if message.video:
                    is_video = True
                elif isinstance(message.media, MessageMediaDocument):
                    # Check mime type
                    if hasattr(message.media.document, 'mime_type') and message.media.document.mime_type.startswith('video/'):
                        is_video = True
                
                if is_video:
                    # Deduplication check
                    file_id = None
                    if hasattr(message, 'file') and hasattr(message.file, 'id'):
                        file_id = message.file.id
                    
                    # Use message ID + source ID as fallback unique key if file ID not available
                    unique_key = f"{source_id}_{message.id}"
                    if file_id:
                        unique_key = f"file_{file_id}"
                    
                    if unique_key in self._processed_files:
                        logger.info(f"Skipping duplicate file: {unique_key}")
                        continue

                    try:
                        # Send file directly to strip caption and forward tag
                        await client.send_message(target_entity, file=message.media)
                        forwarded += 1
                        self._processed_files.add(unique_key)
                        logger.info(f"Forwarded video message {message.id} (clean)")
                        # Random delay to avoid flood wait (4-8 seconds)
                        import random
                        delay = random.uniform(4, 8)
                        logger.info(f"Sleeping for {delay:.2f}s...")
                        await asyncio.sleep(delay) 
                    except Exception as e:
                        logger.error(f"Failed to forward message {message.id}: {e}")
                
                count += 1
                if count % 50 == 0:
                    logger.info(f"Scanned {count} messages, forwarded {forwarded} videos")

            logger.info(f"Forwarding complete. Scanned {count}, Forwarded {forwarded}")

            return {
                "status": "ok",
                "scanned": count,
                "forwarded": forwarded,
                "target": target_group
            }

        except Exception as e:
            logger.error(f"Error in forward_history_videos: {e}", e)
            return {"status": "error", "message": str(e)}

    async def fetch_and_save_history(self, source_id: str, limit: int = 2000) -> Dict[str, Any]:
        """
        Fetch chat history and save to database.
        """
        if not db.pool:
            return {"status": "error", "message": "Database not connected"}

        try:
            # Find a client that can see the source
            client, entity = await self._find_client_for_entity(source_id)
            
            if not client or not entity:
                return {"status": "error", "message": f"Could not find source {source_id} in any connected session"}

            # Log identity
            try:
                me = await client.get_me()
                logger.info(f"Using Client: {me.first_name} (ID: {me.id}, Bot: {me.bot})")
            except Exception:
                pass

            count = 0
            saved = 0
            
            logger.info(f"Starting history fetch from {source_id}")
            
            async for message in client.iter_messages(entity, limit=limit):
                try:
                    msg_id = message.id
                    sender_id = str(message.sender_id) if message.sender_id else None
                    sender_name = None
                    if message.sender:
                        sender_name = getattr(message.sender, 'username', None) or \
                                      getattr(message.sender, 'first_name', None) or \
                                      getattr(message.sender, 'title', None)
                    
                    text = message.text or ""
                    media_type = None
                    file_id = None
                    
                    if message.photo:
                        media_type = "photo"
                    elif message.video:
                        media_type = "video"
                    elif message.document:
                        media_type = "document"
                    
                    # Save to DB
                    await db.pool.execute("""
                        INSERT INTO chat_history (
                            source_id, message_id, sender_id, sender_name, text, media_type, created_at
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                        ON CONFLICT (source_id, message_id) DO NOTHING
                    """, str(source_id), msg_id, sender_id, sender_name, text, media_type, message.date)
                    
                    saved += 1
                except Exception as e:
                    logger.error(f"Failed to save message {message.id}: {e}")
                
                count += 1
                if count % 100 == 0:
                    logger.info(f"Scanned {count} messages, saved {saved}")

            return {
                "status": "ok",
                "scanned": count,
                "saved": saved
            }

        except Exception as e:
            logger.error(f"Error in fetch_and_save_history: {e}", e)
            return {"status": "error", "message": str(e)}

    async def get_chat_history(self, source_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Query chat history from database.
        """
        if not db.pool:
            return []
        
        try:
            rows = await db.pool.fetch("""
                SELECT * FROM chat_history 
                WHERE source_id = $1 
                ORDER BY created_at DESC 
                LIMIT $2
            """, str(source_id), limit)
            
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to query history: {e}")
            return []

    async def cleanup_old_history(self, days: int = 7):
        """
        Delete history older than N days.
        """
        if not db.pool:
            return
        
        try:
            cutoff = datetime.now() - timedelta(days=days)
            result = await db.pool.execute("""
                DELETE FROM chat_history 
                WHERE created_at < $1
            """, cutoff)
            logger.info(f"Cleaned up old history: {result}")
        except Exception as e:
            logger.error(f"Failed to cleanup history: {e}")

history_service = HistoryService()
