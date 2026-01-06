import asyncio
import feedparser
import hashlib
from typing import List, Dict, Optional
from app.core.logger import Logger
from app.core.database import db
from app.core.config import settings

logger = Logger("RssService")

class RssService:
    def __init__(self):
        self.is_running = False
        self._poll_task = None

    async def start(self):
        if self.is_running or not settings.ENABLE_RSS:
            return
        
        self.is_running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("✅ RSS Service started")

    async def stop(self):
        self.is_running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        logger.info("RSS Service stopped")

    async def validate_feed(self, url: str) -> Dict:
        try:
            # Run sync feedparser in thread to avoid blocking
            feed = await asyncio.to_thread(feedparser.parse, url)
            if feed.bozo:
                raise Exception(feed.bozo_exception)
            
            return {
                "valid": True,
                "title": feed.feed.get("title", url),
                "description": feed.feed.get("description", ""),
                "item_count": len(feed.entries)
            }
        except Exception as e:
            logger.warn(f"Feed validation failed for {url}: {e}")
            return {"valid": False, "error": str(e)}

    async def subscribe(self, user_id: str, url: str, chat_id: str = None) -> Dict:
        if not db.pool:
            raise Exception("Database not connected")
        
        chat_id = chat_id or user_id
        
        # Validate
        validation = await self.validate_feed(url)
        if not validation["valid"]:
            raise ValueError(f"Invalid Feed: {validation.get('error')}")

        async with db.pool.acquire() as conn:
            # Upsert source
            source_id = await conn.fetchval("""
                INSERT INTO rss_sources (link, title) VALUES ($1, $2)
                ON CONFLICT (link) DO UPDATE SET title = EXCLUDED.title
                RETURNING id
            """, url, validation["title"])
            
            # Upsert subscription
            await conn.execute("""
                INSERT INTO rss_subscriptions (user_id, chat_id, rss_source_id)
                VALUES ($1, $2, $3)
                ON CONFLICT DO NOTHING
            """, str(user_id), str(chat_id), source_id)
        
        return {"added": True, "title": validation["title"]}

    async def get_subscriptions(self, user_id: str) -> List[Dict]:
        if not db.pool:
            return []
        
        rows = await db.pool.fetch("""
            SELECT s.id, s.title, s.link 
            FROM rss_subscriptions sub
            JOIN rss_sources s ON sub.rss_source_id = s.id
            WHERE sub.user_id = $1
        """, str(user_id))
        
        return [{"id": r["id"], "title": r["title"], "url": r["link"]} for r in rows]

    async def unsubscribe(self, user_id: str, url_or_id: str) -> Dict:
        if not db.pool:
            return {"removed": False, "error": "Database unavailable"}
            
        try:
            # Try by ID first
            try:
                source_id = int(url_or_id)
                res = await db.pool.fetchval("""
                    DELETE FROM rss_subscriptions 
                    WHERE user_id = $1 AND rss_source_id = $2
                    RETURNING rss_source_id
                """, str(user_id), source_id)
                if res: return {"removed": True, "title": f"Source {source_id}"}
            except ValueError:
                pass

            # Try by URL
            res = await db.pool.fetchrow("""
                DELETE FROM rss_subscriptions sub
                USING rss_sources s
                WHERE sub.rss_source_id = s.id 
                AND sub.user_id = $1 
                AND s.link = $2
                RETURNING s.title
            """, str(user_id), url_or_id)
            
            if res:
                return {"removed": True, "title": res['title']}
            else:
                return {"removed": False, "error": "Subscription not found"}

        except Exception as e:
            return {"removed": False, "error": str(e)}

    async def _poll_loop(self):
        while self.is_running:
            try:
                await self._process_feeds()
            except Exception as e:
                logger.error("Error in RSS poll loop", e)
            
            # Wait using configurable interval
            interval_seconds = settings.RSS_POLL_INTERVAL_MS / 1000
            await asyncio.sleep(interval_seconds)

    async def _process_feeds(self):
        if not db.pool:
            return

        # Get all sources
        rows = await db.pool.fetch("SELECT id, link, title FROM rss_sources")
        for row in rows:
            await self._fetch_and_notify(row)

    async def _fetch_and_notify(self, source_row):
        from app.core.bot import telegram_service 
        if not telegram_service.connected:
            return

        source_id = source_row['id']
        url = source_row['link']
        
        try:
            # Run sync feedparser in thread to avoid blocking
            feed = await asyncio.to_thread(feedparser.parse, url)
            
            # Get subscribers
            subs = await db.pool.fetch("""
                SELECT chat_id FROM rss_subscriptions WHERE rss_source_id = $1
            """, source_id)
            
            if not subs:
                return

            for entry in feed.entries[:5]: # Check last 5 items
                item_id = entry.get("guid", entry.get("link", entry.get("title")))
                if not item_id: continue

                # Deduplication hash
                hash_id = hashlib.md5(f"{source_id}:{item_id}".encode()).hexdigest()
                
                # Check if exists
                exists = await db.pool.fetchval("SELECT 1 FROM rss_history WHERE hash_id = $1", hash_id)
                if exists:
                    continue
                
                # Add to history
                await db.pool.execute("""
                    INSERT INTO rss_history (hash_id, source_id, item_id) VALUES ($1, $2, $3)
                """, hash_id, source_id, item_id)
                
                # Notify subscribers
                msg = f"📰 <b>{source_row['title']}</b>\n\n<a href='{entry.link}'>{entry.title}</a>"
                for sub in subs:
                    await telegram_service.send_message(sub['chat_id'], msg, parse_mode='html')

        except Exception as e:
            logger.warn(f"Failed to process feed {url}: {e}")

rss_service = RssService()
