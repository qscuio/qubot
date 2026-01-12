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
        """Collect industry sector data from AkShare.
        
        Uses: ak.stock_board_industry_name_em()
        """
        ak = self._get_akshare()
        if not ak:
            return []
        
        target_date = target_date or china_today()
        
        try:
            df = await asyncio.to_thread(ak.stock_board_industry_name_em)
            
            if df is None or df.empty:
                logger.info("No industry sector data available")
                return []
            
            sectors = []
            for _, row in df.iterrows():
                sector = {
                    "code": str(row.get("板块代码", "")),
                    "name": str(row.get("板块名称", "")),
                    "type": "industry",
                    "change_pct": float(row.get("涨跌幅", 0) or 0),
                    "close_price": float(row.get("最新价", 0) or 0),
                    "turnover": float(row.get("成交额", 0) or 0) / 100000000,  # Convert to 亿
                    "leading_stock": str(row.get("领涨股票", "") or ""),
                    "leading_stock_pct": float(row.get("领涨股票-涨跌幅", 0) or 0),
                    "up_count": int(row.get("上涨家数", 0) or 0),
                    "down_count": int(row.get("下跌家数", 0) or 0),
                }
                sectors.append(sector)
            
            logger.info(f"Found {len(sectors)} industry sectors")
            return sectors
            
        except Exception as e:
            logger.error(f"Failed to collect industry sectors: {e}")
            return []
    
    async def collect_concept_sectors(self, target_date: date = None) -> List[Dict]:
        """Collect concept sector data from AkShare.
        
        Uses: ak.stock_board_concept_name_em()
        """
        ak = self._get_akshare()
        if not ak:
            return []
        
        target_date = target_date or china_today()
        
        try:
            df = await asyncio.to_thread(ak.stock_board_concept_name_em)
            
            if df is None or df.empty:
                logger.info("No concept sector data available")
                return []
            
            sectors = []
            for _, row in df.iterrows():
                sector = {
                    "code": str(row.get("板块代码", "")),
                    "name": str(row.get("板块名称", "")),
                    "type": "concept",
                    "change_pct": float(row.get("涨跌幅", 0) or 0),
                    "close_price": float(row.get("最新价", 0) or 0),
                    "turnover": float(row.get("成交额", 0) or 0) / 100000000,  # Convert to 亿
                    "leading_stock": str(row.get("领涨股票", "") or ""),
                    "leading_stock_pct": float(row.get("领涨股票-涨跌幅", 0) or 0),
                    "up_count": int(row.get("上涨家数", 0) or 0),
                    "down_count": int(row.get("下跌家数", 0) or 0),
                }
                sectors.append(sector)
            
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
        """Get real-time sector performance from AkShare."""
        ak = self._get_akshare()
        if not ak:
            return []
        
        sectors = []
        
        try:
            if sector_type in ('all', 'industry'):
                df = await asyncio.to_thread(ak.stock_board_industry_name_em)
                if df is not None and not df.empty:
                    for _, row in df.head(limit if sector_type == 'industry' else limit // 2).iterrows():
                        sectors.append({
                            "code": str(row.get("板块代码", "")),
                            "name": str(row.get("板块名称", "")),
                            "type": "industry",
                            "change_pct": float(row.get("涨跌幅", 0) or 0),
                            "leading_stock": str(row.get("领涨股票", "") or ""),
                            "up_count": int(row.get("上涨家数", 0) or 0),
                            "down_count": int(row.get("下跌家数", 0) or 0),
                        })
            
            if sector_type in ('all', 'concept'):
                df = await asyncio.to_thread(ak.stock_board_concept_name_em)
                if df is not None and not df.empty:
                    for _, row in df.head(limit if sector_type == 'concept' else limit // 2).iterrows():
                        sectors.append({
                            "code": str(row.get("板块代码", "")),
                            "name": str(row.get("板块名称", "")),
                            "type": "concept",
                            "change_pct": float(row.get("涨跌幅", 0) or 0),
                            "leading_stock": str(row.get("领涨股票", "") or ""),
                            "up_count": int(row.get("上涨家数", 0) or 0),
                            "down_count": int(row.get("下跌家数", 0) or 0),
                        })
            
            # Sort by change_pct descending
            sectors.sort(key=lambda x: x["change_pct"], reverse=True)
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
            SELECT name, change_pct, leading_stock, up_count, down_count
            FROM sector_daily
            WHERE date = $1 AND type = 'industry'
            ORDER BY change_pct DESC
        """, target_date)
        
        concept = await db.pool.fetch("""
            SELECT name, change_pct, leading_stock, up_count, down_count
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
                url = get_sector_url(r['name'], 'industry')
                lines.append(f"  • <a href=\"{url}\">{r['name']}</a> {pct}")
            
            # Bottom 3
            lines.append("\n📉 领跌:")
            for r in industry[-3:]:
                pct = f"{r['change_pct']:+.2f}%"
                url = get_sector_url(r['name'], 'industry')
                lines.append(f"  • <a href=\"{url}\">{r['name']}</a> {pct}")
        
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
                url = get_sector_url(r['name'], 'concept')
                lines.append(f"  • <a href=\"{url}\">{r['name']}</a> {pct} {leader}")
            
            # Bottom 3
            lines.append("\n📉 领跌:")
            for r in concept[-3:]:
                pct = f"{r['change_pct']:+.2f}%"
                url = get_sector_url(r['name'], 'concept')
                lines.append(f"  • <a href=\"{url}\">{r['name']}</a> {pct}")
        
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
                url = get_sector_url(s['name'], s['type'])
                lines.append(f"{i}. {type_icon} <a href=\"{url}\">{s['name']}</a> {pct} ({win_rate})")
        
        if weak:
            lines.append("\n📉 <b>本周弱势板块</b>\n")
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
        
        if not settings.STOCK_ALERT_CHANNEL:
            return
        
        # Collect today's data first
        await self.collect_all_sectors()
        
        # Generate and send report
        report = await self.generate_daily_report()
        
        await telegram_service.send_message(
            settings.STOCK_ALERT_CHANNEL, report, 
            parse_mode="html", 
            link_preview=False
        )
        logger.info("Sent daily sector report")
    
    async def send_weekly_report(self):
        """Send weekly sector report to Telegram."""
        from app.core.bot import telegram_service
        
        if not settings.STOCK_ALERT_CHANNEL:
            return
        
        report = await self.generate_weekly_report()
        
        await telegram_service.send_message(
            settings.STOCK_ALERT_CHANNEL, report, 
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


# Singleton
sector_service = SectorService()
