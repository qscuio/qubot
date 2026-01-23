"""
A-Stock Sector Analysis Tracking Service (板块分析追踪)

Tracks daily sector performance, generates reports,
and provides strong sector analysis based on different time periods.
"""

import asyncio
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional

from app.core.logger import Logger
from app.core.database import db
from app.core.config import settings
from app.core.stock_links import get_sector_url
from app.core.timezone import CHINA_TZ, china_now, china_today
from app.services.data_provider.service import data_provider

logger = Logger("SectorService")


class SectorService:
    """Service for tracking A-stock sector performance."""
    
    def __init__(self):
        self.is_running = False
        self._scheduler_task = None
        self._ak = None  # AkShare module (lazy load)
    
    def _get_akshare(self):
        """Lazy load akshare module."""
        if self._ak is None:
            try:
                import akshare as ak
                self._ak = ak
            except ImportError:
                logger.error("AkShare not installed. Run: pip install akshare")
                return None
        return self._ak
    
    async def start(self):
        """Start the sector tracker service."""
        if self.is_running:
            return
        
        if not settings.STOCK_ALERT_CHANNEL:
            logger.warn("STOCK_ALERT_CHANNEL not configured, sector alerts disabled")
            return
        
        self.is_running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("✅ Sector Tracker started")
    
    async def stop(self):
        """Stop the service."""
        self.is_running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        logger.info("Sector Tracker stopped")
    
    async def initialize(self):
        """Initialize service - backfill recent history if needed."""
        # Delay initialization to allow other services to start and avoid OOM during deployment
        await asyncio.sleep(60)
        
        if not db.pool:
            return
        
        # Get distinct dates we already have
        existing_dates = await db.pool.fetch("""
            SELECT DISTINCT date FROM sector_daily 
            ORDER BY date DESC LIMIT 7
        """)
        existing_set = {row['date'] for row in existing_dates}
        
        if len(existing_set) >= 5:
            logger.info(f"Found {len(existing_set)} days of sector history, sufficient")
            return
        
        needed = 5 - len(existing_set)
        logger.info(f"Have {len(existing_set)} days, need {needed} more, backfilling...")
        
        today = china_today()
        days_collected = 0
        days_checked = 0
        
        while days_collected < needed and days_checked < 10:
            target_date = today - timedelta(days=days_checked)
            days_checked += 1
            
            # Skip weekends
            if target_date.weekday() >= 5:
                continue
            
            # Skip dates we already have
            if target_date in existing_set:
                continue
            
            try:
                result = await self.collect_all_sectors(target_date)
                if result.get("total", 0) > 0:
                    logger.info(f"Backfilled {target_date}: {result['total']} sectors")
                    days_collected += 1
                else:
                    logger.info(f"No sector data for {target_date}")
                
                # Small delay to avoid rate limiting
                await asyncio.sleep(1)
            except Exception as e:
                logger.warn(f"Failed to backfill {target_date}: {e}")
        
        logger.info(f"Sector backfill complete: added {days_collected} days")
    
    # ─────────────────────────────────────────────────────────────────────────
    # Data Collection
    # ─────────────────────────────────────────────────────────────────────────
    
    async def collect_industry_sectors(self, target_date: date = None) -> List[Dict]:
        """Collect industry sector data from providers with fallback."""
        target_date = target_date or china_today()
        _ = target_date  # reserved for future provider support

        try:
            sectors = await data_provider.get_sector_list("industry")
            if not sectors:
                logger.info("No industry sector data available")
                return []
            logger.info(f"Found {len(sectors)} industry sectors")
            return sectors
        except Exception as e:
            logger.error(f"Failed to collect industry sectors: {e}")
            return []
    
    async def collect_concept_sectors(self, target_date: date = None) -> List[Dict]:
        """Collect concept sector data from providers with fallback."""
        target_date = target_date or china_today()
        _ = target_date  # reserved for future provider support

        try:
            sectors = await data_provider.get_sector_list("concept")
            if not sectors:
                logger.info("No concept sector data available")
                return []
            logger.info(f"Found {len(sectors)} concept sectors")
            return sectors
        except Exception as e:
            logger.error(f"Failed to collect concept sectors: {e}")
            return []
    
    async def collect_all_sectors(self, target_date: date = None) -> Dict:
        """Collect all sector data (industry + concept)."""
        target_date = target_date or china_today()
        
        industry = await self.collect_industry_sectors(target_date)
        concept = await self.collect_concept_sectors(target_date)
        
        all_sectors = industry + concept
        
        if all_sectors:
            await self._save_sectors(target_date, all_sectors)
        
        return {
            "industry": len(industry),
            "concept": len(concept),
            "total": len(all_sectors),
        }
    
    async def _save_sectors(self, target_date: date, sectors: List[Dict]):
        """Save sector data to database."""
        if not db.pool:
            return
        
        for sector in sectors:
            try:
                await db.pool.execute("""
                    INSERT INTO sector_daily 
                    (code, name, type, date, change_pct, close_price, turnover, 
                     leading_stock, leading_stock_pct, up_count, down_count)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    ON CONFLICT (code, date) DO UPDATE SET
                        change_pct = EXCLUDED.change_pct,
                        close_price = EXCLUDED.close_price,
                        turnover = EXCLUDED.turnover,
                        leading_stock = EXCLUDED.leading_stock,
                        leading_stock_pct = EXCLUDED.leading_stock_pct,
                        up_count = EXCLUDED.up_count,
                        down_count = EXCLUDED.down_count
                """, 
                    sector["code"], sector["name"], sector["type"], target_date,
                    sector["change_pct"], sector["close_price"], sector["turnover"],
                    sector["leading_stock"], sector["leading_stock_pct"],
                    sector["up_count"], sector["down_count"]
                )
            except Exception as e:
                logger.warn(f"Failed to save sector {sector['code']}: {e}")
    
    # ─────────────────────────────────────────────────────────────────────────
    # Real-time Queries
    # ─────────────────────────────────────────────────────────────────────────
    
    async def get_realtime_sectors(self, sector_type: str = 'all', limit: int = 20) -> List[Dict]:
        """Get real-time sector performance from providers with fallback."""
        sectors = []
        half_limit = max(1, limit // 2)

        try:
            if sector_type in ("all", "industry"):
                industry = await data_provider.get_sector_list("industry")
                if industry:
                    sectors.extend(industry if sector_type == "industry" else industry[:half_limit])

            if sector_type in ("all", "concept"):
                concept = await data_provider.get_sector_list("concept")
                if concept:
                    sectors.extend(concept if sector_type == "concept" else concept[:half_limit])

            if not sectors:
                return await self.get_today_sectors(sector_type=sector_type, limit=limit)

            sectors.sort(key=lambda x: x.get("change_pct", 0), reverse=True)
            return sectors[:limit]
        except Exception as e:
            logger.error(f"Failed to get realtime sectors: {e}")
            return []
    
    async def get_today_sectors(self, sector_type: str = 'all', limit: int = 20) -> List[Dict]:
        """Get today's sector data from database."""
        if not db.pool:
            return []
        
        today = china_today()
        type_filter = "AND type = $2" if sector_type != 'all' else ""
        
        query = f"""
            SELECT code, name, type, change_pct, leading_stock, up_count, down_count
            FROM sector_daily
            WHERE date = $1 {type_filter}
            ORDER BY change_pct DESC
            LIMIT {limit}
        """
        
        if sector_type != 'all':
            rows = await db.pool.fetch(query, today, sector_type)
        else:
            rows = await db.pool.fetch(query, today)
        
        return [dict(r) for r in rows]
    
    # ─────────────────────────────────────────────────────────────────────────
    # Strong Sector Analysis
    # ─────────────────────────────────────────────────────────────────────────
    
    async def get_strong_sectors(self, days: int = 7, sector_type: str = 'all', limit: int = 20) -> List[Dict]:
        """Get strong sectors based on cumulative performance.
        
        Args:
            days: Analysis period (7, 14, or 30)
            sector_type: 'all', 'industry', or 'concept'
            limit: Max results
            
        Returns:
            List of sectors with cumulative stats
        """
        if not db.pool:
            return []
        
        type_filter = "AND type = $2" if sector_type != 'all' else ""
        
        query = f"""
            SELECT 
                code, 
                name,
                type,
                SUM(change_pct) as total_change,
                AVG(change_pct) as avg_change,
                COUNT(CASE WHEN change_pct > 0 THEN 1 END) as up_days,
                COUNT(*) as total_days,
                MAX(change_pct) as max_change,
                MIN(change_pct) as min_change
            FROM sector_daily
            WHERE date >= CURRENT_DATE - INTERVAL '{days} days'
            {type_filter}
            GROUP BY code, name, type
            HAVING COUNT(*) >= {max(1, days // 3)}
            ORDER BY total_change DESC
            LIMIT {limit}
        """
        
        if sector_type != 'all':
            rows = await db.pool.fetch(query, sector_type)
        else:
            # Remove the type filter parameter
            query = f"""
                SELECT 
                    code, 
                    name,
                    type,
                    SUM(change_pct) as total_change,
                    AVG(change_pct) as avg_change,
                    COUNT(CASE WHEN change_pct > 0 THEN 1 END) as up_days,
                    COUNT(*) as total_days,
                    MAX(change_pct) as max_change,
                    MIN(change_pct) as min_change
                FROM sector_daily
                WHERE date >= CURRENT_DATE - INTERVAL '{days} days'
                GROUP BY code, name, type
                HAVING COUNT(*) >= {max(1, days // 3)}
                ORDER BY total_change DESC
                LIMIT {limit}
            """
            rows = await db.pool.fetch(query)
        
        return [dict(r) for r in rows]
    
    async def get_weak_sectors(self, days: int = 7, sector_type: str = 'all', limit: int = 20) -> List[Dict]:
        """Get weakest sectors based on cumulative performance."""
        if not db.pool:
            return []
        
        query = f"""
            SELECT 
                code, 
                name,
                type,
                SUM(change_pct) as total_change,
                AVG(change_pct) as avg_change,
                COUNT(CASE WHEN change_pct < 0 THEN 1 END) as down_days,
                COUNT(*) as total_days
            FROM sector_daily
            WHERE date >= CURRENT_DATE - INTERVAL '{days} days'
            GROUP BY code, name, type
            HAVING COUNT(*) >= {max(1, days // 3)}
            ORDER BY total_change ASC
            LIMIT {limit}
        """
        
        rows = await db.pool.fetch(query)
        return [dict(r) for r in rows]
    
    # ─────────────────────────────────────────────────────────────────────────
    # Reports
    # ─────────────────────────────────────────────────────────────────────────
    
    async def generate_daily_report(self, target_date: date = None) -> str:
        """Generate daily sector report."""
        target_date = target_date or china_today()
        
        if not db.pool:
            return "❌ 数据库未连接"
        
        # Get today's data
        industry = await db.pool.fetch("""
            SELECT code, name, change_pct, leading_stock, up_count, down_count
            FROM sector_daily
            WHERE date = $1 AND type = 'industry'
            ORDER BY change_pct DESC
        """, target_date)
        
        concept = await db.pool.fetch("""
            SELECT code, name, change_pct, leading_stock, up_count, down_count
            FROM sector_daily
            WHERE date = $1 AND type = 'concept'
            ORDER BY change_pct DESC
        """, target_date)
        
        if not industry and not concept:
            return f"📊 {target_date} 无板块数据"
        
        lines = [
            f"📊 <b>板块日报</b> {target_date.strftime('%Y-%m-%d')}",
            "━━━━━━━━━━━━━━━━━━━━━",
        ]
        
        # Industry summary
        if industry:
            up_count = sum(1 for r in industry if r['change_pct'] > 0)
            down_count = len(industry) - up_count
            lines.append(f"\n🏭 <b>行业板块</b> (涨{up_count}/跌{down_count})\n")
            
            # Top 5
            lines.append("📈 领涨:")
            for r in industry[:5]:
                pct = f"{r['change_pct']:+.2f}%"
                lines.append(f"  • {r['name']} {pct}")
            
            # Bottom 3
            lines.append("\n📉 领跌:")
            for r in industry[-3:]:
                pct = f"{r['change_pct']:+.2f}%"
                lines.append(f"  • {r['name']} {pct}")
        
        # Concept summary
        if concept:
            up_count = sum(1 for r in concept if r['change_pct'] > 0)
            down_count = len(concept) - up_count
            lines.append(f"\n💡 <b>概念板块</b> (涨{up_count}/跌{down_count})\n")
            
            # Top 5
            lines.append("📈 领涨:")
            for r in concept[:5]:
                pct = f"{r['change_pct']:+.2f}%"
                leader = f"({r['leading_stock']})" if r['leading_stock'] else ""
                lines.append(f"  • {r['name']} {pct} {leader}")
            
            # Bottom 3
            lines.append("\n📉 领跌:")
            for r in concept[-3:]:
                pct = f"{r['change_pct']:+.2f}%"
                lines.append(f"  • {r['name']} {pct}")
        
        report = "\n".join(lines)
        
        # Save report
        try:
            await db.pool.execute("""
                INSERT INTO sector_reports (report_type, report_date, content)
                VALUES ('daily', $1, $2)
                ON CONFLICT (report_type, report_date) DO UPDATE SET
                    content = EXCLUDED.content
            """, target_date, report)
        except Exception as e:
            logger.warn(f"Failed to save daily report: {e}")
        
        return report
    
    async def generate_weekly_report(self, week_end: date = None) -> str:
        """Generate weekly sector report."""
        week_end = week_end or china_today()
        week_start = week_end - timedelta(days=6)
        
        if not db.pool:
            return "❌ 数据库未连接"
        
        # Get weekly aggregates
        strong = await self.get_strong_sectors(days=7, limit=10)
        weak = await self.get_weak_sectors(days=7, limit=5)
        
        lines = [
            f"📊 <b>板块周报</b> {week_start.strftime('%m/%d')}-{week_end.strftime('%m/%d')}",
            "━━━━━━━━━━━━━━━━━━━━━",
        ]
        
        if strong:
            lines.append("\n🔥 <b>本周强势板块</b>\n")
            for i, s in enumerate(strong, 1):
                type_icon = "🏭" if s['type'] == 'industry' else "💡"
                pct = f"{s['total_change']:+.2f}%"
                win_rate = f"{s['up_days']}/{s['total_days']}天上涨"
                lines.append(f"{i}. {type_icon} {s['name']} {pct} ({win_rate})")
        
        if weak:
            lines.append("\n📉 <b>本周弱势板块</b>\n")
            for i, s in enumerate(weak, 1):
                type_icon = "🏭" if s['type'] == 'industry' else "💡"
                pct = f"{s['total_change']:+.2f}%"
                lines.append(f"{i}. {type_icon} {s['name']} {pct}")
        
        report = "\n".join(lines)
        
        # Save report
        try:
            await db.pool.execute("""
                INSERT INTO sector_reports (report_type, report_date, content)
                VALUES ('weekly', $1, $2)
                ON CONFLICT (report_type, report_date) DO UPDATE SET
                    content = EXCLUDED.content
            """, week_end, report)
        except Exception as e:
            logger.warn(f"Failed to save weekly report: {e}")
        
        return report
    
    async def generate_monthly_report(self, month_end: date = None) -> str:
        """Generate monthly sector report."""
        month_end = month_end or china_today()
        month_start = month_end.replace(day=1)
        
        if not db.pool:
            return "❌ 数据库未连接"
        
        # Get monthly aggregates
        strong = await self.get_strong_sectors(days=30, limit=10)
        weak = await self.get_weak_sectors(days=30, limit=5)
        
        lines = [
            f"📊 <b>板块月报</b> {month_start.strftime('%Y年%m月')}",
            "━━━━━━━━━━━━━━━━━━━━━",
        ]
        
        if strong:
            lines.append("\n🏆 <b>月度强势板块 TOP10</b>\n")
            for i, s in enumerate(strong, 1):
                type_icon = "🏭" if s['type'] == 'industry' else "💡"
                pct = f"{s['total_change']:+.2f}%"
                avg = f"日均{s['avg_change']:+.2f}%"
                url = get_sector_url(s['name'], s['type'])
                lines.append(f"{i}. {type_icon} <a href=\"{url}\">{s['name']}</a> {pct} ({avg})")
        
        if weak:
            lines.append("\n📉 <b>月度弱势板块</b>\n")
            for i, s in enumerate(weak, 1):
                type_icon = "🏭" if s['type'] == 'industry' else "💡"
                pct = f"{s['total_change']:+.2f}%"
                url = get_sector_url(s['name'], s['type'])
                lines.append(f"{i}. {type_icon} <a href=\"{url}\">{s['name']}</a> {pct}")
        
        report = "\n".join(lines)
        
        # Save report
        try:
            await db.pool.execute("""
                INSERT INTO sector_reports (report_type, report_date, content)
                VALUES ('monthly', $1, $2)
                ON CONFLICT (report_type, report_date) DO UPDATE SET
                    content = EXCLUDED.content
            """, month_end, report)
        except Exception as e:
            logger.warn(f"Failed to save monthly report: {e}")
        
        return report
    
    async def send_daily_report(self):
        """Send daily sector report to Telegram."""
        from app.core.bot import telegram_service
        from app.bots.registry import get_bot
        from aiogram.utils.keyboard import InlineKeyboardBuilder

        report_target = settings.REPORT_TARGET_GROUP
        if not report_target:
            return
        
        # Collect today's data first
        await self.collect_all_sectors()
        
        # Generate and send report
        report = await self.generate_daily_report()

        # Build buttons for top/bottom industry & concept
        buttons = []
        try:
            industry = await db.pool.fetch("""
                SELECT code, name, change_pct, 'industry' as type
                FROM sector_daily
                WHERE date = CURRENT_DATE AND type = 'industry'
                ORDER BY change_pct DESC
            """)
            concept = await db.pool.fetch("""
                SELECT code, name, change_pct, 'concept' as type
                FROM sector_daily
                WHERE date = CURRENT_DATE AND type = 'concept'
                ORDER BY change_pct DESC
            """)
            buttons = list(industry[:5]) + list(industry[-3:]) + list(concept[:5]) + list(concept[-3:])
        except Exception:
            buttons = []

        bot = get_bot("crawler")
        if bot and buttons:
            builder = InlineKeyboardBuilder()
            seen = set()
            for s in buttons:
                code = s.get("code")
                name = s.get("name") or ""
                sector_type = s.get("type") or "concept"
                if not code or not name:
                    continue
                key = f"{sector_type}:{code}"
                if key in seen:
                    continue
                seen.add(key)
                icon = "🏭" if sector_type == "industry" else "💡"
                builder.button(
                    text=f"{icon} {name}",
                    callback_data=f"sector:stocks:{sector_type}:{code}:1"
                )
            builder.adjust(2)
            await bot.send_message(
                report_target,
                report,
                parse_mode="HTML",
                reply_markup=builder.as_markup(),
                disable_web_page_preview=True
            )
        else:
            await telegram_service.send_message(
                report_target, report, 
                parse_mode="html", 
                link_preview=False
            )
        logger.info("Sent daily sector report")
    
    async def send_weekly_report(self):
        """Send weekly sector report to Telegram."""
        from app.core.bot import telegram_service
        from app.bots.registry import get_bot
        from aiogram.utils.keyboard import InlineKeyboardBuilder

        report_target = settings.REPORT_TARGET_GROUP
        if not report_target:
            return
        
        report = await self.generate_weekly_report()

        # Build buttons for strong/weak sectors
        bot = get_bot("crawler")
        builder = InlineKeyboardBuilder()
        buttons = []
        try:
            strong = await self.get_strong_sectors(days=7, limit=10)
            weak = await self.get_weak_sectors(days=7, limit=5)
            buttons = strong + weak
        except Exception:
            buttons = []

        if bot and buttons:
            seen = set()
            for s in buttons:
                code = s.get("code")
                name = s.get("name") or ""
                sector_type = s.get("type") or "concept"
                if not code or not name:
                    continue
                key = f"{sector_type}:{code}"
                if key in seen:
                    continue
                seen.add(key)
                icon = "🏭" if sector_type == "industry" else "💡"
                builder.button(
                    text=f"{icon} {name}",
                    callback_data=f"sector:stocks:{sector_type}:{code}:1"
                )
            builder.adjust(2)
            await bot.send_message(
                report_target,
                report,
                parse_mode="HTML",
                reply_markup=builder.as_markup(),
                disable_web_page_preview=True
            )
        else:
            await telegram_service.send_message(
                report_target, report, 
                parse_mode="html", 
                link_preview=False
            )
        logger.info("Sent weekly sector report")
    
    # ─────────────────────────────────────────────────────────────────────────
    # Scheduler
    # ─────────────────────────────────────────────────────────────────────────
    
    async def _scheduler_loop(self):
        """Background scheduler for timed tasks.
        
        - 16:05 Daily: Collect data + send daily report
        - 16:30 Friday: Send weekly report
        - 17:00 Last trading day of month: Send monthly report
        """
        daily_time = "16:05"
        weekly_time = "16:30"
        monthly_time = "17:00"
        
        triggered_today = set()
        
        while self.is_running:
            try:
                now = datetime.now(CHINA_TZ)
                time_str = now.strftime("%H:%M")
                date_str = now.strftime("%Y-%m-%d")
                
                # Reset triggered set at midnight
                if time_str == "00:00":
                    triggered_today.clear()
                
                key = f"{date_str}_{time_str}"
                
                # Skip weekends
                if now.weekday() < 5:
                    # Daily report
                    if time_str == daily_time and key not in triggered_today:
                        triggered_today.add(key)
                        asyncio.create_task(self.send_daily_report())
                    
                    # Weekly report (Friday)
                    if now.weekday() == 4 and time_str == weekly_time and key not in triggered_today:
                        triggered_today.add(key)
                        asyncio.create_task(self.send_weekly_report())
                    
                    # Monthly report (last trading day - simplified: last weekday)
                    next_day = now.date() + timedelta(days=1)
                    if next_day.month != now.month and time_str == monthly_time and key not in triggered_today:
                        triggered_today.add(key)
                        from app.core.bot import telegram_service
                        report = await self.generate_monthly_report()
                        await telegram_service.send_message(
                            settings.STOCK_ALERT_CHANNEL, report,
                            parse_mode="html", link_preview=False
                        )
                        logger.info("Sent monthly sector report")
                
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
            
            # Check every 30 seconds
            await asyncio.sleep(30)

    # ─────────────────────────────────────────────────────────────────────────
    # Stock Sector Info (Individual Stock)
    # ─────────────────────────────────────────────────────────────────────────

    async def get_stock_sector_info(self, code: str) -> Dict:
        """Get industry and concept info for a stock, including performance.
        
        Returns:
            {
                "industry": {
                    "name": "银行",
                    "performance": {
                        "day": 1.2, "week": 3.4, "month": 5.6
                    }
                },
                "concepts": [
                    {
                        "name": "互联金融",
                        "performance": {...}
                    },
                    ...
                ]
            }
        """
        if not db.pool:
            return {}
            
        # 1. Try to get from stock_info cache first
        row = await db.pool.fetchrow("""
            SELECT industry, concepts, updated_at 
            FROM stock_info WHERE code = $1
        """, code)
        
        industry = None
        concepts = []
        
        # Check if cache is valid (e.g., < 7 days old for static info)
        # But for new columns, they might be NULL even if row exists
        need_fetch = True
        if row and row['industry']:
            # We have data. Check if it's too old? Sector info changes rarely.
            # Let's refresh if older than 30 days or if empty
            updated_at = row['updated_at']
            if updated_at and (datetime.now() - updated_at).days < 30:
                need_fetch = False
                industry = row['industry']
                if row['concepts']:
                    concepts = row['concepts'].split(',')

        if need_fetch:
            s_data = await self._fetch_stock_sectors_akshare(code)
            if s_data:
                industry = s_data.get('industry')
                concepts = s_data.get('concepts', [])
                
                # Update cache
                concepts_str = ",".join(concepts) if concepts else ""
                try:
                    await db.pool.execute("""
                        INSERT INTO stock_info (code, industry, concepts, updated_at)
                        VALUES ($1, $2, $3, NOW())
                        ON CONFLICT (code) DO UPDATE SET
                            industry = EXCLUDED.industry,
                            concepts = EXCLUDED.concepts,
                            updated_at = NOW()
                    """, code, industry, concepts_str)
                except Exception as e:
                    logger.warn(f"Failed to cache stock sectors for {code}: {e}")
        
        # 2. Get performance for industry and concepts
        result = {
            "industry": None,
            "concepts": []
        }
        
        if industry:
            perf = await self._get_sectors_performance([industry], 'industry')
            result["industry"] = {
                "name": industry,
                "performance": perf.get(industry, {})
            }
            
        if concepts:
            # Limit to top 20 concepts to avoid huge queries if many
            perf = await self._get_sectors_performance(concepts[:20], 'concept')
            for c in concepts:
                if c in perf:
                    result["concepts"].append({
                        "name": c,
                        "performance": perf[c]
                    })
        
        return result

    async def get_sector_stock_list(self, sector_code: str, sector_type: str, limit: int = 200) -> Dict:
        """Get sector stock list sorted by change_pct.

        Returns:
            {
                "name": "半导体",
                "type": "industry",
                "stocks": [{"code": "...", "name": "...", "change_pct": 1.23}, ...]
            }
        """
        if not db.pool:
            return {"name": None, "type": sector_type, "stocks": []}

        sector_code = str(sector_code)
        row = await db.pool.fetchrow("""
            SELECT name
            FROM sector_daily
            WHERE code = $1 AND type = $2
            ORDER BY date DESC
            LIMIT 1
        """, sector_code, sector_type)
        sector_name = row["name"] if row else None
        if not sector_name:
            return {"name": None, "type": sector_type, "stocks": []}

        try:
            stocks = await data_provider.get_sector_constituents(sector_code, sector_name, sector_type)
        except Exception as e:
            logger.warn(f"Failed to fetch sector constituents for {sector_name}: {e}")
            return {"name": sector_name, "type": sector_type, "stocks": []}

        if not stocks:
            return {"name": sector_name, "type": sector_type, "stocks": []}

        codes = [s.get("code") for s in stocks if s.get("code")]

        # Override change_pct from local DB (latest close)
        if codes:
            rows = await db.pool.fetch("""
                SELECT DISTINCT ON (code) code, change_pct
                FROM stock_history
                WHERE code = ANY($1)
                ORDER BY code, date DESC
            """, codes)
            latest_map = {r["code"]: float(r["change_pct"] or 0) for r in rows}
            for s in stocks:
                if s["code"] in latest_map:
                    s["change_pct"] = latest_map[s["code"]]

        for s in stocks:
            if s.get("change_pct") is None:
                s["change_pct"] = 0.0

        stocks.sort(key=lambda x: x.get("change_pct", 0), reverse=True)
        if limit and len(stocks) > limit:
            stocks = stocks[:limit]

        return {"name": sector_name, "type": sector_type, "stocks": stocks}

    async def _fetch_stock_sectors_akshare(self, code: str) -> Optional[Dict]:
        """Fetch stock sector info from AkShare."""
        ak = self._get_akshare()
        if not ak:
            return None
            
        try:
            # Use stock_individual_info_em
            df = await asyncio.to_thread(ak.stock_individual_info_em, symbol=code)
            if df is None or df.empty:
                return None
                
            info = {}
            # DF columns: item, value
            # Example rows: 
            # item='所属行业', value='专用设备'
            # item='所属概念', value='融资融券,深股通...'
            
            for _, row in df.iterrows():
                key = str(row.get('item', ''))
                val = str(row.get('value', ''))
                
                # AkShare output keys can vary (e.g. '行业' vs '所属行业')
                if key in ['所属行业', '行业']:
                    info['industry'] = val
                elif key in ['所属概念', '概念', '核心概念']:
                     # Split by comma or similar
                    info['concepts'] = [c.strip() for c in val.split(',') if c.strip()]
            
            return info
            
        except Exception as e:
            logger.warn(f"Failed to fetch sectors for {code}: {e}")
            return None

    async def _get_sectors_performance(self, names: List[str], sector_type: str) -> Dict[str, Dict]:
        """Get performance stats for a list of sectors.
        
        Returns:
            {
                "SectorName": {
                    "day": 1.2,
                    "week": 5.0,
                    "month": 10.0
                }
            }
        """
        if not names or not db.pool:
            return {}
            
        # 1. Get today's change (Daily) from sector_daily
        # 2. To get Weekly (5d) and Monthly (20d), we need valid trading days.
        #    Simplified: Sum change_pct for last N records in sector_daily?
        #    Or (Latest - Oldest) / Oldest?
        #    Let's use (Close - Close_Prev) / Close_Prev logic if we can.
        #    But for sectors we only store daily Change%, Close, etc.
        #    Calculating cumulative return: Product(1 + pct/100) - 1
        
        # Pull last 30 days of data for these sectors
        days_needed = 30
        
        query = """
            SELECT name, date, change_pct 
            FROM sector_daily 
            WHERE name = ANY($1) 
              AND type = $2
              AND date >= CURRENT_DATE - INTERVAL '45 days'
            ORDER BY date DESC
        """
        
        rows = await db.pool.fetch(query, names, sector_type)
        
        by_sector = {}
        for r in rows:
            name = r['name']
            if name not in by_sector:
                by_sector[name] = []
            by_sector[name].append(r)
            
        results = {}
        for name in names:
            data = by_sector.get(name, [])
            if not data:
                continue
                
            # Limit to recent 20 trading days roughly
            # data is sorted date DESC
            
            # Daily: first item (if today) or yesterday?
            # Ideally assume data includes latest available.
            day_val = float(data[0]['change_pct']) if data else 0
            
            # Helper for cumulative return
            def calc_return(items):
                res = 1.0
                for item in items:
                    pct = float(item['change_pct'])
                    res *= (1 + pct / 100)
                return (res - 1) * 100
            
            # Week: last 5 records
            week_val = calc_return(data[:5]) if len(data) >= 1 else 0
            
            # Month: last 20 records
            month_val = calc_return(data[:20]) if len(data) >= 1 else 0
            
            results[name] = {
                "day": round(day_val, 2),
                "week": round(week_val, 2),
                "month": round(month_val, 2)
            }
            
        return results
# Singleton
sector_service = SectorService()
