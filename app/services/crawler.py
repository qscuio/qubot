"""
Web Crawler Service

Crawls configured websites, extracts content, and stores structured data.
"""

import asyncio
import hashlib
from datetime import datetime
from typing import List, Dict, Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.core.logger import Logger
from app.core.database import db
from app.core.config import settings
from app.core.timezone import china_now
from app.core.stock_links import get_chart_url, get_sector_url

logger = Logger("CrawlerService")


class CrawlerService:
    """Web crawler service for information gathering."""
    
    def __init__(self):
        self.is_running = False
        self._poll_task = None
        self._report_task = None
        self._http_client: Optional[httpx.AsyncClient] = None
    
    async def start(self):
        """Start the crawler service."""
        if self.is_running or not settings.ENABLE_CRAWLER:
            return
        
        self.is_running = True
        self._http_client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )
        self._poll_task = asyncio.create_task(self._poll_loop())
        self._report_task = asyncio.create_task(self._report_scheduler_loop())
        logger.info("✅ Crawler Service started")
    
    async def stop(self):
        """Stop the crawler service."""
        self.is_running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        if self._report_task:
            self._report_task.cancel()
            try:
                await self._report_task
            except asyncio.CancelledError:
                pass
        if self._http_client:
            await self._http_client.aclose()
        logger.info("Crawler Service stopped")
    
    async def initialize(self):
        """Initialize default sources if none exist."""
        if not db.pool:
            return
        
        sources = await self.get_sources()
        if sources:
            return  # Already has sources
        
        # Default sources
        defaults = [
            ("https://finance.sina.com.cn/", "新浪财经"),
            ("https://finance.eastmoney.com/", "东方财富-财经"),
            ("https://www.10jqka.com.cn/", "同花顺"),
            ("https://www.cls.cn/", "财联社"),
            ("https://wallstreetcn.com/", "华尔街见闻"),
            ("https://www.caixin.com/", "财新"),
            ("https://www.yicai.com/", "第一财经"),
            ("https://www.jiemian.com/", "界面新闻"),
            ("https://www.21jingji.com/", "21世纪经济报道"),
            ("https://www.zqrb.cn/", "证券日报"),
            ("https://www.cs.com.cn/", "中国证券报"),
            ("https://www.cnstock.com/", "上海证券报"),
            ("https://finance.ifeng.com/", "凤凰财经"),
        ]
        
        for url, name in defaults:
            try:
                await self.add_source(url, name)
                logger.info(f"Added default source: {name}")
            except Exception as e:
                logger.warn(f"Failed to add default source {name}: {e}")
    
    # ─────────────────────────────────────────────────────────────────────────
    # Source Management
    # ─────────────────────────────────────────────────────────────────────────
    
    async def add_source(self, url: str, name: str = None) -> Dict:
        """Add a new source to crawl."""
        if not db.pool:
            raise Exception("Database not connected")
        
        # Validate URL
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("Invalid URL")
        
        # Use domain as default name
        if not name:
            name = parsed.netloc
        
        try:
            async with db.pool.acquire() as conn:
                source_id = await conn.fetchval("""
                    INSERT INTO crawler_sources (url, name) 
                    VALUES ($1, $2)
                    ON CONFLICT (url) DO UPDATE SET name = EXCLUDED.name
                    RETURNING id
                """, url, name)
            
            return {"added": True, "id": source_id, "name": name, "url": url}
        except Exception as e:
            logger.error(f"Failed to add source: {e}")
            raise
    
    async def remove_source(self, source_id: int) -> bool:
        """Remove a source by ID."""
        if not db.pool:
            return False
        
        result = await db.pool.execute("""
            DELETE FROM crawler_sources WHERE id = $1
        """, source_id)
        return "DELETE 1" in result
    
    async def get_sources(self) -> List[Dict]:
        """Get all crawler sources."""
        if not db.pool:
            return []
        
        rows = await db.pool.fetch("""
            SELECT id, url, name, enabled, last_crawled_at, created_at
            FROM crawler_sources
            ORDER BY created_at DESC
        """)
        return [dict(r) for r in rows]
    
    async def toggle_source(self, source_id: int, enabled: bool) -> bool:
        """Enable or disable a source."""
        if not db.pool:
            return False
        
        await db.pool.execute("""
            UPDATE crawler_sources SET enabled = $2 WHERE id = $1
        """, source_id, enabled)
        return True
    
    # ─────────────────────────────────────────────────────────────────────────
    # Crawling
    # ─────────────────────────────────────────────────────────────────────────
    
    async def crawl_source(self, source: Dict) -> List[Dict]:
        """Crawl a single source and extract items."""
        url = source["url"]
        source_id = source["id"]
        items_added = []
        
        try:
            # Fetch the page
            response = await self._http_client.get(url)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.text, "lxml")
            
            # Extract articles/items
            items = self._extract_items(soup, url)
            
            # Save to database
            for item in items:
                saved = await self._save_item(source_id, item)
                if saved:
                    items_added.append(item)
            
            # Update last crawled time
            await db.pool.execute("""
                UPDATE crawler_sources SET last_crawled_at = NOW() WHERE id = $1
            """, source_id)
            
            logger.info(f"Crawled {source['name']}: {len(items_added)} new items")
            return items_added
            
        except Exception as e:
            logger.error(f"Failed to crawl {url}: {e}")
            return []
    
    async def crawl_all(self) -> Dict:
        """Crawl all enabled sources."""
        sources = await self.get_sources()
        enabled = [s for s in sources if s.get("enabled", True)]
        
        total_items = 0
        for source in enabled:
            items = await self.crawl_source(source)
            total_items += len(items)
            # Small delay between sources
            await asyncio.sleep(2)
        
        return {"sources": len(enabled), "items": total_items}
    
    def _extract_items(self, soup: BeautifulSoup, base_url: str) -> List[Dict]:
        """Extract news items from parsed HTML."""
        items = []
        
        # Try common patterns for news/article links
        # Pattern 1: <article> tags
        for article in soup.find_all("article")[:20]:
            item = self._parse_article_element(article, base_url)
            if item:
                items.append(item)
        
        # Pattern 2: Headlines with links (h1, h2, h3)
        if not items:
            for heading in soup.find_all(["h1", "h2", "h3"])[:30]:
                link = heading.find("a")
                if link and link.get("href"):
                    item = {
                        "title": link.get_text(strip=True),
                        "url": urljoin(base_url, link["href"]),
                        "content": "",
                    }
                    if item["title"] and len(item["title"]) > 5:
                        items.append(item)
        
        # Pattern 3: List items with links
        if not items:
            for li in soup.find_all("li")[:50]:
                link = li.find("a")
                if link and link.get("href"):
                    title = link.get_text(strip=True)
                    if title and len(title) > 10:
                        items.append({
                            "title": title,
                            "url": urljoin(base_url, link["href"]),
                            "content": "",
                        })
        
        # Deduplicate by URL
        seen = set()
        unique = []
        for item in items:
            if item["url"] not in seen:
                seen.add(item["url"])
                unique.append(item)
        
        return unique[:30]  # Limit to 30 items per crawl
    
    def _parse_article_element(self, article, base_url: str) -> Optional[Dict]:
        """Parse an article element."""
        # Find title
        title_el = article.find(["h1", "h2", "h3", "h4"])
        if not title_el:
            return None
        
        title = title_el.get_text(strip=True)
        if not title or len(title) < 5:
            return None
        
        # Find link
        link = title_el.find("a") or article.find("a")
        url = urljoin(base_url, link["href"]) if link and link.get("href") else base_url
        
        # Find content/summary
        content = ""
        p = article.find("p")
        if p:
            content = p.get_text(strip=True)[:500]
        
        return {"title": title, "url": url, "content": content}
    
    async def _save_item(self, source_id: int, item: Dict) -> bool:
        """Save a crawled item to database."""
        if not db.pool:
            return False
        
        try:
            # Check if URL already exists
            exists = await db.pool.fetchval("""
                SELECT 1 FROM crawler_items WHERE url = $1
            """, item["url"])
            
            if exists:
                return False
            
            # Generate summary using AI (optional, can be async)
            summary = item.get("content", "")[:200] if item.get("content") else ""
            
            await db.pool.execute("""
                INSERT INTO crawler_items (source_id, url, title, content, summary)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (url) DO NOTHING
            """, source_id, item["url"], item["title"], item.get("content", ""), summary)
            
            return True
        except Exception as e:
            logger.warn(f"Failed to save item: {e}")
            return False
    
    # ─────────────────────────────────────────────────────────────────────────
    # Data Access
    # ─────────────────────────────────────────────────────────────────────────
    
    async def get_recent_items(self, limit: int = 20, source_id: int = None) -> List[Dict]:
        """Get recent crawled items."""
        if not db.pool:
            return []
        
        if source_id:
            rows = await db.pool.fetch("""
                SELECT i.*, s.name as source_name
                FROM crawler_items i
                JOIN crawler_sources s ON i.source_id = s.id
                WHERE i.source_id = $1
                ORDER BY i.created_at DESC
                LIMIT $2
            """, source_id, limit)
        else:
            rows = await db.pool.fetch("""
                SELECT i.*, s.name as source_name
                FROM crawler_items i
                JOIN crawler_sources s ON i.source_id = s.id
                ORDER BY i.created_at DESC
                LIMIT $1
            """, limit)
        
        return [dict(r) for r in rows]
    
    async def get_items_for_report(self, hours: int = 24) -> Dict[str, List[Dict]]:
        """Get items grouped by source for report generation."""
        if not db.pool:
            return {}
        
        rows = await db.pool.fetch("""
            SELECT i.*, s.name as source_name, s.url as source_url
            FROM crawler_items i
            JOIN crawler_sources s ON i.source_id = s.id
            WHERE i.created_at > NOW() - INTERVAL '%s hours'
            ORDER BY s.name, i.created_at DESC
        """ % hours)
        
        # Group by source
        result = {}
        for row in rows:
            source_name = row["source_name"]
            if source_name not in result:
                result[source_name] = []
            result[source_name].append(dict(row))
        
        return result

    async def get_recent_items_flat(self, hours: int = 12, limit: int = 15) -> List[Dict]:
        """Get recent items in a flat list for reports."""
        if not db.pool:
            return []
        rows = await db.pool.fetch("""
            SELECT i.*, s.name as source_name
            FROM crawler_items i
            JOIN crawler_sources s ON i.source_id = s.id
            WHERE i.created_at > NOW() - INTERVAL '%s hours'
            ORDER BY i.created_at DESC
            LIMIT $1
        """ % hours, limit)
        return [dict(r) for r in rows]
    
    # ─────────────────────────────────────────────────────────────────────────
    # Background Polling
    # ─────────────────────────────────────────────────────────────────────────
    
    async def _poll_loop(self):
        """Background polling loop."""
        while self.is_running:
            try:
                await self.crawl_all()
            except Exception as e:
                logger.error(f"Error in crawler poll loop: {e}")
            
            # Wait using configurable interval
            interval_seconds = settings.CRAWLER_INTERVAL_MS / 1000
            await asyncio.sleep(interval_seconds)

    # ─────────────────────────────────────────────────────────────────────────
    # Hot Report Scheduler
    # ─────────────────────────────────────────────────────────────────────────

    async def _report_scheduler_loop(self):
        """Send crawler hot report at 08:00 and 20:00 China time."""
        report_times = {"08:00": "早间", "20:00": "晚间"}
        triggered = set()

        while self.is_running:
            try:
                now = china_now()
                time_str = now.strftime("%H:%M")
                date_str = now.strftime("%Y-%m-%d")

                if time_str == "00:00":
                    triggered.clear()

                if time_str in report_times:
                    key = f"{date_str}_{time_str}"
                    if key not in triggered:
                        triggered.add(key)
                        label = report_times[time_str]
                        asyncio.create_task(self.send_hot_report(label, hours=12))
            except Exception as e:
                logger.error(f"Crawler report scheduler error: {e}")

            await asyncio.sleep(30)

    async def send_hot_report(self, label: str, hours: int = 12):
        """Send hot news/sector/stock report to report channel."""
        from app.core.bot import telegram_service

        report_target = settings.REPORT_TARGET_GROUP or settings.REPORT_TARGET_CHANNEL
        if not report_target:
            logger.warn("REPORT_TARGET_GROUP/REPORT_TARGET_CHANNEL not configured, crawler report disabled")
            return

        # Crawl latest pages before reporting
        try:
            await self.crawl_all()
        except Exception as e:
            logger.warn(f"Crawl before report failed: {e}")

        news_items = await self.get_recent_items_flat(hours=hours, limit=12)
        hot_sectors = await self._get_hot_sectors(limit=8)
        hot_stocks = await self._get_hot_stocks(limit=8)

        now_str = china_now().strftime("%Y-%m-%d %H:%M")
        text_lines = [
            f"📰 <b>{label}热点快报</b>",
            "━━━━━━━━━━━━━━━━━━━━━",
            f"🕒 时间: {now_str}",
            "",
            "🔥 <b>热门消息</b>",
        ]

        if news_items:
            for i, item in enumerate(news_items, 1):
                title = item.get("title") or "未命名"
                url = item.get("url") or ""
                source = item.get("source_name") or ""
                if url:
                    text_lines.append(f"{i}. <a href=\"{url}\">{title}</a> <i>({source})</i>")
                else:
                    text_lines.append(f"{i}. {title} <i>({source})</i>")
        else:
            text_lines.append("暂无近期新闻")

        text_lines.append("")
        text_lines.append("🚀 <b>热门板块</b>")
        if hot_sectors:
            for i, s in enumerate(hot_sectors, 1):
                name = s.get("name") or "-"
                change = float(s.get("change_pct") or 0)
                lead = s.get("leading_stock") or ""
                url = get_sector_url(name, s.get("type") or "concept")
                lead_part = f" · 领涨: {lead}" if lead else ""
                text_lines.append(f"{i}. <a href=\"{url}\">{name}</a> {change:+.2f}%{lead_part}")
        else:
            text_lines.append("暂无板块数据")

        text_lines.append("")
        text_lines.append("📈 <b>热门个股</b>")
        if hot_stocks:
            for i, s in enumerate(hot_stocks, 1):
                code = s.get("code") or ""
                name = s.get("name") or code
                change = float(s.get("change_pct") or 0)
                chart_url = get_chart_url(code, name, context="crawler_hot")
                streak = s.get("limit_times")
                streak_part = f" · {streak}板" if streak else ""
                text_lines.append(f"{i}. <a href=\"{chart_url}\">{name}</a> {change:+.2f}%{streak_part}")
        else:
            text_lines.append("暂无个股数据")

        report_text = "\n".join(text_lines)
        await telegram_service.send_message(
            report_target,
            report_text,
            parse_mode="html",
            link_preview=False
        )
        logger.info(f"Sent crawler hot report ({label})")

    async def _get_hot_sectors(self, limit: int = 8) -> List[Dict]:
        """Get hottest sectors from local DB."""
        if not db.pool:
            return []
        rows = await db.pool.fetch("""
            SELECT code, name, type, change_pct, leading_stock
            FROM sector_daily
            WHERE date = (SELECT MAX(date) FROM sector_daily)
            ORDER BY change_pct DESC
            LIMIT $1
        """, limit)
        return [dict(r) for r in rows]

    async def _get_hot_stocks(self, limit: int = 8) -> List[Dict]:
        """Get hottest stocks from local DB (limit-up list)."""
        if not db.pool:
            return []
        rows = await db.pool.fetch("""
            SELECT code, name, change_pct, limit_times
            FROM limit_up_stocks
            WHERE date = (SELECT MAX(date) FROM limit_up_stocks)
              AND is_sealed = TRUE
            ORDER BY limit_times DESC, change_pct DESC
            LIMIT $1
        """, limit)
        return [dict(r) for r in rows]


# Singleton instance
crawler_service = CrawlerService()
