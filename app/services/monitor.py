import re
import time
import asyncio
from datetime import datetime
import pytz
from collections import OrderedDict
from typing import Dict, List, Optional
from telethon import events
from telethon.tl import types
from app.core.config import settings
from app.core.logger import Logger
from app.core.bot import telegram_service
from app.core.database import db
from app.services.message_dedup import get_deduplicator

logger = Logger("MonitorService")

# Shanghai timezone for report scheduling
SHANGHAI_TZ = pytz.timezone('Asia/Shanghai')

def get_shanghai_time():
    """Get current time in Shanghai timezone."""
    return datetime.now(SHANGHAI_TZ)


class MessageBuffer:
    """Buffer messages for summarization."""
    
    def __init__(self, max_messages: int = 10, max_age_seconds: int = 300):
        self.buffers: Dict[str, List[dict]] = {}  # channel_id -> list of messages
        self.last_flush: Dict[str, float] = {}    # channel_id -> timestamp
        self.max_messages = max_messages
        self.max_age_seconds = max_age_seconds
    
    def add(self, channel_id: str, message_data: dict) -> bool:
        """Add message to buffer. Returns True if buffer should be flushed."""
        if channel_id not in self.buffers:
            self.buffers[channel_id] = []
            self.last_flush[channel_id] = time.time()
        
        self.buffers[channel_id].append(message_data)
        
        # Check if we should flush
        count_trigger = len(self.buffers[channel_id]) >= self.max_messages
        time_trigger = (time.time() - self.last_flush.get(channel_id, 0)) >= self.max_age_seconds
        
        return count_trigger or time_trigger
    
    def flush(self, channel_id: str) -> List[dict]:
        """Return and clear buffer for channel."""
        messages = self.buffers.pop(channel_id, [])
        self.last_flush[channel_id] = time.time()
        return messages
    
    def get_stale_channels(self) -> List[str]:
        """Return channels that have pending messages past timeout."""
        now = time.time()
        stale = []
        for channel_id, last_time in self.last_flush.items():
            if channel_id in self.buffers and self.buffers[channel_id]:
                if (now - last_time) >= self.max_age_seconds:
                    stale.append(channel_id)
        return stale


class MonitorService:
    def __init__(self):
        self.is_running = False
        # Changed from list of strings to dict: channel_id -> {id, name, enabled}
        self.channels: Dict[str, dict] = {}
        self.target_channel = settings.TARGET_CHANNEL
        self.vip_target_channel = settings.VIP_TARGET_CHANNEL  # Separate channel for VIP
        self.report_target_channel = settings.REPORT_TARGET_CHANNEL or settings.TARGET_CHANNEL  # For daily reports
        # Deduplication cache: stores (chat_id, message_id) tuples
        # Using OrderedDict to maintain insertion order for LRU eviction
        self._processed_messages = OrderedDict()
        self._max_cache_size = 1000  # Keep last 1000 messages
        
        # VIP users: user_id -> {id, username, name, enabled}
        self.vip_users: Dict[str, dict] = {}
        
        # Blacklist: channel_id -> {id, name} - channels to completely ignore
        self.blacklist: Dict[str, dict] = {}
        
        # Summarization buffer - DISABLED (messages forward immediately now)
        # We still cache messages for daily reports, but don't buffer for 2-hour summaries
        self.summarize_enabled = False  # Was: settings.MONITOR_SUMMARIZE
        self.message_buffer = MessageBuffer(
            max_messages=settings.MONITOR_BUFFER_SIZE,
            max_age_seconds=settings.MONITOR_BUFFER_TIMEOUT
        )
        self._flush_task = None
        self._report_task = None  # Daily report scheduler
    
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
        
        # Load config channels (just IDs, default to 'market' category)
        config_channels = settings.source_channels_list
        for cid in config_channels:
            if cid not in self.channels:
                self.channels[cid] = {'id': cid, 'name': cid, 'enabled': True, 'category': 'market'}
        
        # Load db channels with names and categories
        if db.pool:
            try:
                rows = await db.pool.fetch("SELECT channel_id, name, enabled, category FROM monitor_channels")
                for row in rows:
                    self.channels[row['channel_id']] = {
                        'id': row['channel_id'],
                        'name': row['name'] or row['channel_id'],
                        'enabled': row['enabled'],
                        'category': row['category'] or 'market'
                    }
                logger.info(f"Loaded {len(rows)} channels from database")
            except Exception as e:
                logger.warn(f"Failed to load channels from database: {e}")
            
            # Load VIP users
            try:
                rows = await db.pool.fetch("SELECT user_id, username, name, enabled FROM monitor_vip_users")
                for row in rows:
                    self.vip_users[row['user_id']] = {
                        'id': row['user_id'],
                        'username': row['username'],
                        'name': row['name'] or row['username'] or row['user_id'],
                        'enabled': row['enabled']
                    }
                logger.info(f"Loaded {len(rows)} VIP users from database")
            except Exception as e:
                logger.warn(f"Failed to load VIP users from database: {e}")
            
            # Load blacklist
            try:
                rows = await db.pool.fetch("SELECT channel_id, name FROM monitor_blacklist")
                for row in rows:
                    self.blacklist[row['channel_id']] = {
                        'id': row['channel_id'],
                        'name': row['name'] or row['channel_id']
                    }
                logger.info(f"Loaded {len(rows)} blacklisted channels from database")
            except Exception as e:
                logger.debug(f"Blacklist table may not exist yet: {e}")
        
        # Load config blacklist (from env)
        for bl in settings.blacklist_channels_list:
            if bl not in self.blacklist:
                self.blacklist[bl] = {'id': bl, 'name': bl}
        
        logger.info(f"MonitorService initialized with {len(self.channels)} sources, {len(self.vip_users)} VIPs, {len(self.blacklist)} blocked.")

    async def start(self):
        if self.is_running:
            return
        
        if not telegram_service.connected:
            logger.error("Telegram service not connected!")
            return

        # Register handler
        await telegram_service.add_message_handler(self.handle_message)
        self.is_running = True
        
        # Disabled: 2-hour periodic summarization (too many tokens, low quality)
        # Only keep daily reports at 8:00 and 20:00
        # if self.summarize_enabled:
        #     self._flush_task = asyncio.create_task(self._periodic_flush())
        #     logger.info("📝 Summarization enabled")
        
        # Start daily report scheduler
        self._report_task = asyncio.create_task(self._schedule_reports())
        logger.info("📅 Daily report scheduler started (8:00/20:00)")
        
        logger.info("✅ MonitorService started.")

    async def stop(self):
        self.is_running = False
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        if self._report_task:
            self._report_task.cancel()
            try:
                await self._report_task
            except asyncio.CancelledError:
                pass
        logger.info("MonitorService stopped.")
    
    async def _periodic_flush(self):
        """Background task to flush stale buffers."""
        import random
        while self.is_running:
            try:
                await asyncio.sleep(7200)  # Check every 2 hours
                stale_channels = self.message_buffer.get_stale_channels()
                for channel_id in stale_channels:
                    # Add random delay (1-3 minutes) between each channel to avoid
                    # sending all summaries at the same time
                    if stale_channels.index(channel_id) > 0:
                        delay = random.randint(60, 180)
                        logger.info(f"⏳ Waiting {delay}s before summarizing next channel...")
                        await asyncio.sleep(delay)
                    await self._flush_and_summarize(channel_id)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic flush: {e}")
    
    async def _schedule_reports(self):
        """Schedule daily reports at 8:00 and 20:00."""
        from datetime import timedelta
        
        while self.is_running:
            try:
                now = get_shanghai_time()
                
                # Calculate next report time (8:00 or 20:00)
                today_8am = now.replace(hour=8, minute=0, second=0, microsecond=0)
                today_8pm = now.replace(hour=20, minute=0, second=0, microsecond=0)
                
                if now < today_8am:
                    next_report = today_8am
                elif now < today_8pm:
                    next_report = today_8pm
                else:
                    next_report = today_8am + timedelta(days=1)
                
                wait_seconds = (next_report - now).total_seconds()
                logger.info(f"📅 Next report scheduled at {next_report.strftime('%Y-%m-%d %H:%M')}")
                
                await asyncio.sleep(wait_seconds)
                
                if self.is_running:
                    await self._generate_all_reports()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in report scheduler: {e}")
                await asyncio.sleep(60)  # Wait before retry
    
    async def _generate_all_reports(self):
        """Generate reports for all channels with cached messages."""
        if not db.pool:
            logger.warn("Database not available for report generation")
            return
        
        try:
            # Get all channels with cached messages
            channels = await db.pool.fetch("""
                SELECT DISTINCT channel_id, channel_name 
                FROM monitor_message_cache 
                ORDER BY channel_name
            """)
            
            if not channels:
                logger.info("📊 No cached messages for report generation")
                return
            
            logger.info(f"📊 Generating reports for {len(channels)} channels...")
            
            import random
            for idx, channel in enumerate(channels):
                try:
                    # Add random delay (1-3 minutes) between each channel to avoid
                    # sending all reports at the same time
                    if idx > 0:
                        delay = random.randint(60, 180)
                        logger.info(f"⏳ Waiting {delay}s before generating next report...")
                        await asyncio.sleep(delay)
                    await self._generate_channel_report(
                        channel['channel_id'], 
                        channel['channel_name'] or channel['channel_id']
                    )
                except Exception as e:
                    logger.error(f"Failed to generate report for {channel['channel_name']}: {e}")
            
        except Exception as e:
            logger.error(f"Error generating reports: {e}")
    
    async def _generate_channel_report(self, channel_id: str, channel_name: str):
        """Generate report for a single channel using compression pipeline."""
        if not db.pool:
            return
        
        # ═══════════════════════════════════════════════════════════════
        # Check channel category - different handling for non-market channels
        # ═══════════════════════════════════════════════════════════════
        channel_info = self.channels.get(channel_id, {})
        channel_category = channel_info.get('category', 'market')
        
        # Auto-detect category if still default 'market'
        if channel_category == 'market':
            # Fetch sample messages for detection
            sample_msgs = await db.pool.fetch("""
                SELECT message_text FROM monitor_message_cache 
                WHERE channel_id = $1 LIMIT 50
            """, channel_id)
            
            if sample_msgs:
                from app.services.market_keywords import MarketKeywords
                texts = [m['message_text'] or '' for m in sample_msgs]
                detected = MarketKeywords.detect_channel_category(texts)
                
                if detected != 'market':
                    # Update category in memory and DB
                    channel_category = detected
                    await self.set_channel_category(channel_id, detected)
                    logger.info(f"🔍 Auto-detected {channel_name} as '{detected}'")
        
        # tech/resource channels: just clear cache, no report
        if channel_category in ('tech', 'resource', 'skip'):
            messages_count = await db.pool.fetchval("""
                SELECT COUNT(*) FROM monitor_message_cache WHERE channel_id = $1
            """, channel_id)
            if messages_count:
                await db.pool.execute("""
                    DELETE FROM monitor_message_cache WHERE channel_id = $1
                """, channel_id)
                logger.info(f"⏭️ Skipped {channel_name} ({channel_category}): {messages_count} messages cleared")
            return
        
        # Import compression services
        from app.services.message_compressor import message_compressor
        from app.services.hot_words import hot_words_service
        
        # Fetch cached messages
        messages = await db.pool.fetch("""
            SELECT sender_name, message_text, created_at
            FROM monitor_message_cache
            WHERE channel_id = $1
            ORDER BY created_at ASC
        """, channel_id)
        
        if not messages:
            return
        
        original_count = len(messages)
        logger.info(f"📝 Generating report for {channel_name} ({original_count} messages)")
        
        # ═══════════════════════════════════════════════════════════════
        # Step 1: Compress and structure messages
        # ═══════════════════════════════════════════════════════════════
        compression_result = await message_compressor.compress(
            [dict(m) for m in messages],  # Convert Record to dict
            channel_id,
            channel_name
        )
        
        if compression_result.compressed_count == 0:
            logger.info(f"📊 No valuable messages for {channel_name}, skipping report")
            # Still clear cache
            await db.pool.execute("""
                DELETE FROM monitor_message_cache WHERE channel_id = $1
            """, channel_id)
            return
        
        # ═══════════════════════════════════════════════════════════════
        # Step 2: Persist hot words to database
        # ═══════════════════════════════════════════════════════════════
        try:
            await hot_words_service.persist_to_db()
        except Exception as e:
            logger.warn(f"Failed to persist hot words: {e}")
        
        # ═══════════════════════════════════════════════════════════════
        # Step 3: Format for AI prompt
        # ═══════════════════════════════════════════════════════════════
        now = get_shanghai_time()
        report_type = "早报" if now.hour < 12 else "晚报"
        date_str = now.strftime("%Y年%m月%d日")
        
        # Get hot words report
        hot_words_section = hot_words_service.format_report()
        
        # Format compressed messages
        compressed_info = message_compressor.format_for_prompt(compression_result)
        
        # Category and sentiment stats
        cat_stats = ", ".join([f"{k}: {v}" for k, v in compression_result.category_stats.items()])
        sent_stats = ", ".join([f"{k}: {v}" for k, v in compression_result.sentiment_stats.items()])
        
        prompt = f"""你是一个专业的市场新闻分析师。请为「{channel_name}」生成{report_type}。

📊 数据概览：
- 原始消息: {compression_result.original_count} 条 → 筛选后: {compression_result.compressed_count} 条
- 市场分类: {cat_stats}
- 市场情绪: {sent_stats}

{hot_words_section}

要求：
1. 使用专业、简洁的语言，突出市场价值信息
2. 重点关注价格变动、重大事件、市场情绪
3. 使用 Markdown 格式

格式模板：
# {channel_name} {report_type}
> {date_str} | 原始 {compression_result.original_count} 条 → 精选 {compression_result.compressed_count} 条

## 📰 核心要闻
（列出 3-5 条最重要的市场信息，附带情绪标签 📈/📉）

## 📊 数据亮点
（关键数字、价格变动、涨跌幅等）

## 🔥 热门话题
（根据热词分析今日讨论焦点）

## 💡 研判建议
（基于以上信息的市场研判，1-2 句话）

---

筛选后的消息记录：
{compressed_info[:8000]}
"""
        
        try:
            from app.services.ai import ai_service
            result = await ai_service.quick_chat(prompt)
            report_content = result.get('content', '报告生成失败')
            
            # Check if report generation failed
            if report_content == '报告生成失败' or not report_content.strip():
                logger.error(f"Failed to generate report content for {channel_name}")
                return
            
            # Add footer with compression stats
            report_markdown = f"""{report_content}

---
*由 QuBot 自动生成 | {now.isoformat()}*
*压缩率: {compression_result.compression_ratio:.1%} ({compression_result.original_count} → {compression_result.compressed_count})*
"""
            
            # ═══════════════════════════════════════════════════════════════
            # Step 4: Save to GitHub (Markdown + JSON)
            # ═══════════════════════════════════════════════════════════════
            download_url = None
            json_url = None
            try:
                from app.services.github import github_service
                if github_service.is_ready:
                    # Save markdown report
                    safe_name = channel_name.replace(' ', '_').replace('/', '_')
                    md_filename = f"reports/channels/{safe_name}_{now.strftime('%Y%m%d_%H%M')}.md"
                    download_url = github_service.save_note(
                        md_filename, 
                        report_markdown, 
                        f"Report: {channel_name} {report_type}"
                    )
                    logger.info(f"📎 Report saved: {download_url}")
                    
                    # Save structured JSON data
                    json_filename = f"reports/data/{now.strftime('%Y-%m-%d')}_{safe_name}.json"
                    json_content = compression_result.to_json()
                    json_url = github_service.save_note(
                        json_filename,
                        json_content,
                        f"Data: {channel_name} {now.strftime('%Y-%m-%d')}"
                    )
                    logger.info(f"📦 JSON data saved: {json_url}")
            except Exception as e:
                logger.warn(f"Failed to save report to GitHub: {e}")
            
            # ═══════════════════════════════════════════════════════════════
            # Step 5: Send report to Telegram
            # ═══════════════════════════════════════════════════════════════
            if self.report_target_channel:
                # Truncate for Telegram if too long
                tg_report = report_content
                if len(tg_report) > 4000:
                    tg_report = tg_report[:4000] + "\n\n... (内容已截断)"
                
                formatted = f"📊 <b>{channel_name} {report_type}</b>\n"
                formatted += f"━━━━━━━━━━━━━━━━━━━━━\n"
                formatted += f"📈 原始 {compression_result.original_count} → 精选 {compression_result.compressed_count}\n\n"
                formatted += tg_report.replace("**", "").replace("##", "📌").replace("# ", "📋 ")
                
                if download_url:
                    formatted += f"\n\n📎 <a href='{download_url}'>完整报告</a>"
                if json_url:
                    formatted += f" | <a href='{json_url}'>原始数据</a>"
                
                target = self.report_target_channel
                if isinstance(target, str) and (target.isdigit() or target.lstrip('-').isdigit()):
                    target = int(target)
                
                await telegram_service.send_message(target, formatted, parse_mode='html')
                logger.info(f"✅ Report sent for {channel_name}")
            
            # ═══════════════════════════════════════════════════════════════
            # Step 6: Clear cache
            # ═══════════════════════════════════════════════════════════════
            await db.pool.execute("""
                DELETE FROM monitor_message_cache WHERE channel_id = $1
            """, channel_id)
            logger.info(f"🗑️ Cleared cache for {channel_name}")
            
        except Exception as e:
            logger.error(f"Failed to generate report: {e}")
    
    async def _cache_message(self, channel_id: str, channel_name: str, sender_name: str, message_text: str):
        """Cache a message for daily report with deduplication check."""
        if not db.pool:
            return
        
        # Skip empty or very short messages
        if not message_text or len(message_text) < 20:
            return
        
        # Check for duplicate content before caching
        is_dup, reason = get_deduplicator().is_duplicate(
            message_text,
            channel_id=channel_id,
            check_near_duplicates=True
        )
        
        if is_dup:
            logger.debug(f"🔄 Skipping duplicate message ({reason}): {message_text[:50]}...")
            return
        
        try:
            await db.pool.execute("""
                INSERT INTO monitor_message_cache (channel_id, channel_name, sender_name, message_text)
                VALUES ($1, $2, $3, $4)
            """, channel_id, channel_name, sender_name, message_text)
        except Exception as e:
            logger.warn(f"Failed to cache message: {e}")
    
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

    async def set_channel_category(self, channel_id: str, category: str) -> bool:
        """
        Set channel category for different report handling.
        
        Categories:
        - 'market': Full AI analysis, compression, hot words (default)
        - 'tech': Skip AI analysis, just clear cache
        - 'resource': Skip AI analysis, just clear cache
        - 'skip': Completely skip, don't cache messages
        """
        valid_categories = ('market', 'tech', 'resource', 'skip')
        if category not in valid_categories:
            logger.warn(f"Invalid category: {category}. Valid: {valid_categories}")
            return False
        
        if channel_id in self.channels:
            self.channels[channel_id]['category'] = category
            if db.pool:
                try:
                    await db.pool.execute(
                        "UPDATE monitor_channels SET category = $2 WHERE channel_id = $1",
                        channel_id, category
                    )
                    logger.info(f"📁 Set {self.channels[channel_id].get('name', channel_id)} category to: {category}")
                    return True
                except Exception as e:
                    logger.warn(f"Failed to update channel category: {e}")
        return False
    
    def get_channel_category(self, channel_id: str) -> str:
        """Get channel category."""
        return self.channels.get(channel_id, {}).get('category', 'market')


    # ─────────────────────────────────────────────────────────────────────────
    # VIP User Management
    # ─────────────────────────────────────────────────────────────────────────

    def is_vip_user(self, user_id: str, username: str = None) -> bool:
        """Check if a user is a VIP (enabled)."""
        # Check by user_id first
        if user_id in self.vip_users:
            return self.vip_users[user_id].get('enabled', True)
        # Check by username
        if username:
            for vip in self.vip_users.values():
                if vip.get('username') == username or vip.get('username') == f"@{username}":
                    return vip.get('enabled', True)
        return False

    async def add_vip_user(self, user_id: str, username: str = None, name: str = None) -> dict:
        """Add a VIP user for immediate forwarding."""
        # Normalize
        user_id = str(user_id).lstrip('@')
        if username:
            username = username.lstrip('@')
        
        display_name = name or username or user_id
        
        if user_id not in self.vip_users:
            self.vip_users[user_id] = {
                'id': user_id,
                'username': username,
                'name': display_name,
                'enabled': True
            }
            # Persist to DB
            if db.pool:
                try:
                    await db.pool.execute("""
                        INSERT INTO monitor_vip_users (user_id, username, name, enabled)
                        VALUES ($1, $2, $3, TRUE) ON CONFLICT (user_id)
                        DO UPDATE SET username = $2, name = $3
                    """, user_id, username, display_name)
                except Exception as e:
                    logger.warn(f"Failed to persist VIP user: {e}")
            logger.info(f"⭐ Added VIP user: {display_name} ({user_id})")
        
        return self.vip_users[user_id]

    async def remove_vip_user(self, user_id: str):
        """Remove a VIP user."""
        user_id = str(user_id).lstrip('@')
        
        if user_id in self.vip_users:
            info = self.vip_users.pop(user_id)
            if db.pool:
                try:
                    await db.pool.execute("DELETE FROM monitor_vip_users WHERE user_id = $1", user_id)
                except Exception as e:
                    logger.warn(f"Failed to remove VIP user from DB: {e}")
            logger.info(f"⭐ Removed VIP user: {info.get('name', user_id)} ({user_id})")

    async def toggle_vip_user(self, user_id: str, enabled: bool):
        """Enable or disable a VIP user."""
        if user_id in self.vip_users:
            self.vip_users[user_id]['enabled'] = enabled
            if db.pool:
                try:
                    await db.pool.execute(
                        "UPDATE monitor_vip_users SET enabled = $2 WHERE user_id = $1",
                        user_id, enabled
                    )
                except Exception as e:
                    logger.warn(f"Failed to update VIP user: {e}")

    # ─────────────────────────────────────────────────────────────────────────────
    # Blacklist Management
    # ─────────────────────────────────────────────────────────────────────────────
    
    def is_blacklisted(self, chat_username: str = None, chat_id: str = None) -> bool:
        """Check if a channel is blacklisted."""
        for bl_id, bl_info in self.blacklist.items():
            if self.matches_source(bl_id, chat_username, chat_id):
                return True
        return False
    
    async def add_to_blacklist(self, channel_id: str, name: str = None) -> dict:
        """Add a channel to blacklist."""
        channel_id = str(channel_id).strip()
        display_name = name or channel_id
        
        if channel_id not in self.blacklist:
            self.blacklist[channel_id] = {
                'id': channel_id,
                'name': display_name
            }
            # Persist to DB
            if db.pool:
                try:
                    await db.pool.execute("""
                        INSERT INTO monitor_blacklist (channel_id, name)
                        VALUES ($1, $2) ON CONFLICT (channel_id)
                        DO UPDATE SET name = $2
                    """, channel_id, display_name)
                except Exception as e:
                    logger.warn(f"Failed to persist blacklist entry: {e}")
            logger.info(f"⛔ Added to blacklist: {display_name} ({channel_id})")
        
        return self.blacklist[channel_id]
    
    async def remove_from_blacklist(self, channel_id: str):
        """Remove a channel from blacklist."""
        channel_id = str(channel_id).strip()
        
        if channel_id in self.blacklist:
            info = self.blacklist.pop(channel_id)
            if db.pool:
                try:
                    await db.pool.execute("DELETE FROM monitor_blacklist WHERE channel_id = $1", channel_id)
                except Exception as e:
                    logger.warn(f"Failed to remove blacklist entry from DB: {e}")
            logger.info(f"✅ Removed from blacklist: {info.get('name', channel_id)} ({channel_id})")

    def _normalize_peer_id(self, value):
        if not value: return ""
        text = str(value).strip()
        if text.startswith("-100"): return text[4:]
        if text.startswith("-"): return text[1:]
        return text
    
    def _is_own_target_channel(self, chat_id: str) -> bool:
        """Check if this chat is our own target channel (created by us).
        Messages from these channels should not be summarized."""
        norm_chat_id = self._normalize_peer_id(chat_id)
        
        # Check against TARGET_CHANNEL
        if self.target_channel:
            norm_target = self._normalize_peer_id(self.target_channel)
            if norm_chat_id == norm_target:
                return True
        
        # Check against VIP_TARGET_CHANNEL
        if self.vip_target_channel:
            norm_vip_target = self._normalize_peer_id(self.vip_target_channel)
            if norm_chat_id == norm_vip_target:
                return True
        
        return False
    
    def _build_message_link(self, chat_username: Optional[str], chat_id: str, message_id: int) -> Optional[str]:
        if chat_username:
            return f"https://t.me/{chat_username}/{message_id}"
        if str(chat_id).startswith("-100"):
            return f"https://t.me/c/{str(chat_id)[4:]}/{message_id}"
        return None

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

            chat_title = getattr(chat, 'title', None) or 'Unknown'
            chat_username = getattr(chat, 'username', None)
            chat_id = str(chat.id)
            message_id = event.message.id
            message_time = event.message.date.strftime('%H:%M') if event.message.date else None
            
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
            sender_username = getattr(sender, 'username', None)
            sender_name = sender_username or getattr(sender, 'first_name', 'Unknown')
            sender_id = str(sender.id) if sender else 'Unknown'
            
            # Skip messages sent by our own accounts (don't forward our own messages)
            if sender and sender.id in telegram_service.own_user_ids:
                logger.debug(f"⏭️ Skipping message from our own account: {sender_name} ({sender.id})")
                return
            
            # Message content (truncated)
            msg_text = (event.message.message or '')[:100]
            
            # Detailed debug logging
            client_id = getattr(event.client, 'me', None) 
            client_info = f" [via {client_id.id}]" if client_id else ""
            logger.info(f"📨 MSG{client_info} | Chat: {chat_title} (@{chat_username or chat_id}) | From: {sender_name} ({sender_id}) | Text: {msg_text[:50]}...")
            
            # Skip messages from our own target channels (no need to summarize our own output)
            if self._is_own_target_channel(chat_id):
                logger.debug(f"⏭️ Skipping message from own target channel: {chat_title}")
                return
            
            # Filter out ads, 18+ content, bot admission messages
            from app.services.content_filter import content_filter
            full_text = event.message.message or ''
            should_filter, filter_reason = content_filter.check(full_text)
            if should_filter:
                logger.info(f"🚫 Filtered message ({filter_reason}): {msg_text[:50]}...")
                return
            
            # Check blacklist - skip channels/groups we don't want to process
            # BUT: VIP users have higher priority than blacklist
            is_vip_sender = self.is_vip_user(sender_id, sender_username)
            is_blacklisted = self.is_blacklisted(chat_username, chat_id)
            if is_blacklisted and not is_vip_sender:
                logger.info(f"⛔ Blacklisted channel, skipping: {chat_title}")
                return

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

            # 4. Check for duplicate content (before forwarding)
            full_text = event.message.message or ''
            is_content_dup, dup_reason = get_deduplicator().is_duplicate(
                full_text, 
                channel_id=chat_id,
                check_near_duplicates=True
            )
            if is_content_dup and not is_vip_sender:
                # Allow VIP duplicates (important sources may repeat)
                logger.info(f"🔄 Skipping duplicate content ({dup_reason}): {msg_text[:50]}...")
                return

            # 5. Check if sender is VIP (for direct forwarding)
            is_vip = is_vip_sender
            
            # 5. Forward VIP messages, or any non-blacklisted messages
            should_forward = is_vip or not is_blacklisted
            if should_forward and self.target_channel:
                source_name = chat_title if chat_title != 'Unknown' else (chat_username or chat_id)
                source_handle = f"@{chat_username}" if chat_username else None
                message_link = self._build_message_link(chat_username, chat_id, message_id)
                media = event.message.media
                has_media = bool(media)
                media_supported = isinstance(
                    media,
                    (
                        types.MessageMediaPhoto,
                        types.MessageMediaDocument,
                        types.MessageMediaWebPage,
                    ),
                )
                
                # Convert to HTML to preserve formatting (links, bold, etc)
                from telethon.extensions import html
                msg_html = html.unparse(event.message.message, event.message.entities)
                
                # Check for URLs to convert to Telegraph (if enabled)
                telegraph_url = None
                if len(msg_html) > 500 and "http" in msg_html:
                    try:
                        from app.services.telegraph import telegraph_service
                        page_title = f"{chat_title} - {get_shanghai_time().strftime('%Y-%m-%d')}"
                        telegraph_url = await telegraph_service.create_page(
                            title=page_title,
                            content_html=msg_html,
                            author_name=source_name
                        )
                    except Exception as e:
                        logger.warn(f"Failed to create Telegraph page: {e}")

                formatted_msg = self._format_message(
                    msg_html,
                    source_name,
                    is_vip=is_vip,
                    telegraph_url=telegraph_url,
                    sender_name=sender_name,
                    message_time=message_time,
                    message_link=message_link,
                    source_handle=source_handle,
                    has_media=has_media
                )
                log_prefix = "⭐ VIP " if is_vip else ""
                logger.info(f"📤 {log_prefix}Forwarding from {sender_name}...")
                try:
                    # VIP messages go to VIP channel if configured, else target channel
                    if is_vip:
                        target = self.vip_target_channel or self.target_channel
                    else:
                        target = self.target_channel
                    
                    if isinstance(target, str) and (target.isdigit() or target.lstrip('-').isdigit()):
                         target = int(target)
                    
                    await telegram_service.send_message(
                        target, 
                        formatted_msg, 
                        parse_mode='html', 
                        file=media if media_supported else None,
                        link_preview=False 
                    )
                    if has_media and not media_supported:
                        target_str = str(target)
                        norm_target = self._normalize_peer_id(target_str)
                        norm_chat = self._normalize_peer_id(chat_id)
                        target_is_source = (
                            (chat_username and target_str in (chat_username, f"@{chat_username}"))
                            or (norm_target and norm_target == norm_chat)
                        )
                        if not target_is_source:
                            await telegram_service.forward_messages(
                                target,
                                event.message,
                                from_peer=chat
                            )
                            logger.info(f"📎 Unsupported media forwarded")
                    log_label = "VIP " if is_vip else ""
                    logger.info(f"✅ {log_label}message forwarded to {target}")
                except Exception as e:
                    log_label = "VIP " if is_vip else ""
                    logger.error(f"❌ Failed to forward {log_label}message: {e}")
            else:
                # Not forwarded (blacklisted or no target channel configured)
                logger.info(f"📝 Logged message from {sender_name} (not forwarded)")

            # 7. Cache message for daily reports
            await self._cache_message(chat_id, chat_title, sender_name, event.message.message)
            
            # 8. Save History
            await self._save_to_history(chat_title, chat_id, event.message.message)

        except Exception as e:
            logger.error(f"Error handling message: {e}")
            import traceback
            logger.debug(traceback.format_exc())

    async def _flush_and_summarize(self, channel_id: str):
        """Flush buffer for a channel and send summarized message."""
        messages = self.message_buffer.flush(channel_id)
        if not messages:
            return
        
        channel_info = self.get_channel_info(channel_id)
        source_name = channel_info.get('name', channel_id) if channel_info else channel_id
        
        logger.info(f"📝 Summarizing {len(messages)} messages from {source_name}")
        
        try:
            # Build summary using AI
            from app.services.ai import ai_service
            
            # Format messages for summarization (with sender preserved)
            msg_list = "\n".join([
                f"[{m['time']}] {m['sender']}: {m['text'][:200]}" 
                for m in messages
            ])
            
            # Chinese prompt for group chat summarization
            prompt = f"""你是一个专业的群聊消息分析助手。请用中文对以下群聊消息进行结构化总结。

分析要求：
1. 【讨论主题】：识别主要讨论的话题（1-3个）
2. 【关键信息】：提取重要的数据、链接、资源或结论
3. 【决策与共识】：总结任何达成的决定或共识
4. 【待跟进事项】：列出需要后续关注的行动项

消息记录:
{msg_list}

请直接输出总结内容，不需要严格按照上述格式，保持自然流畅："""
            
            result = await ai_service.quick_chat(prompt)
            summary = result.get('content', '无法生成摘要')
            
            # Format time range
            times = [m.get('time') for m in messages if m.get('time')]
            time_range = None
            if times:
                start_time = min(times)
                end_time = max(times)
                time_range = start_time if start_time == end_time else f"{start_time}-{end_time}"
            
            meta_bits = []
            if time_range:
                meta_bits.append(f"🕒 {time_range}")
            meta_bits.append(f"💬 {len(messages)} 条消息")
            meta_line = " • ".join(meta_bits)
            
            # Build raw history (preserving sender names)
            raw_history = "\n".join([
                f"[{m['time']}] {m['sender']}: {m['text'][:150]}" 
                for m in messages
            ])
            
            # Truncate raw history if too long (Telegram message limit)
            if len(raw_history) > 3000:
                raw_history = raw_history[:3000] + "\n... (更多消息已省略)"
            
            formatted_summary = (
                f"📊 <b>群组消息汇总 - {source_name}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"{meta_line}\n\n"
                f"<b>📝 摘要:</b>\n{summary.strip()}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"<b>📜 原始消息:</b>\n<code>{raw_history}</code>"
            )
            
            target = self.target_channel
            if isinstance(target, str) and (target.isdigit() or target.lstrip('-').isdigit()):
                target = int(target)
            
            await telegram_service.send_message(target, formatted_summary, parse_mode='html')
            logger.info(f"✅ Summary sent to target channel")
            
        except Exception as e:
            logger.error(f"❌ Failed to summarize: {e}")
            # Fallback: send a simple count message
            fallback_msg = f"📊 {len(messages)} 条消息来自 {source_name} (摘要生成失败)"
            try:
                target = self.target_channel
                if isinstance(target, str) and (target.isdigit() or target.lstrip('-').isdigit()):
                    target = int(target)
                await telegram_service.send_message(target, fallback_msg)
            except:
                pass

    def _format_message(
        self,
        html_text,
        source_name,
        is_vip=False,
        telegraph_url=None,
        sender_name=None,
        message_time=None,
        message_link=None,
        source_handle=None,
        has_media=False
    ):
        header_name = source_name
        if message_link:
            header_name = f"<a href='{message_link}'>{source_name}</a>"
        
        meta_bits = []
        if sender_name:
            meta_bits.append(f"👤 <code>{sender_name}</code>")
        if source_handle and source_handle != source_name and source_handle.lstrip("@") != source_name:
            meta_bits.append(f"📍 {source_handle}")
        if message_time:
            meta_bits.append(f"🕒 {message_time}")
        if has_media:
            meta_bits.append("📎 media")
        if is_vip:
            meta_bits.append("⭐ VIP")
        meta_line = " • ".join(meta_bits)
        
        lines = [f"📨 <b>{header_name}</b>", "━━━━━━━━━━━━━━━━━━━━━"]
        if meta_line:
            lines.append(meta_line)
        if telegraph_url:
            clean_text = re.sub('<[^<]+?>', '', html_text or '')  # Strip HTML for preview
            preview = clean_text[:200] + "..." if len(clean_text) > 200 else clean_text
            preview_text = preview or "📰 Article preview"
            lines.extend(["", preview_text, "", f"👉 <b>Instant View</b>: <a href='{telegraph_url}'>Read article</a>"])
            return "\n".join(lines)
        
        body = html_text or ("📎 <i>Media-only message</i>" if has_media else "")
        if body:
            lines.extend(["", body])
        return "\n".join(lines)

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
