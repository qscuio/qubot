"""
A-Share Market Report Service (A股市场分析报告)

Generates weekly and monthly market reports with:
- Strongest/weakest stocks analysis
- Sector performance analysis  
- AI-powered market insights and predictions

Schedule:
- Weekly: Every Friday at 20:00 (8 PM China time)
- Monthly: Last trading day of month at 20:00
"""

import asyncio
import json
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional
import pytz

from app.core.logger import Logger
from app.core.database import db
from app.core.config import settings

logger = Logger("MarketReportService")

# China timezone
CHINA_TZ = pytz.timezone("Asia/Shanghai")


class MarketReportService:
    """Service for generating A-share market analysis reports."""
    
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
        """Start the market report service."""
        if self.is_running:
            return
        
        if not settings.REPORT_TARGET_CHANNEL:
            logger.warn("REPORT_TARGET_CHANNEL not configured, market reports disabled")
            return
        
        self.is_running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("✅ Market Report Service started")
    
    async def stop(self):
        """Stop the service."""
        self.is_running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        logger.info("Market Report Service stopped")
    
    async def initialize(self):
        """Initialize service - nothing special needed."""
        logger.info("Market Report Service initialized")
    
    # ─────────────────────────────────────────────────────────────────────────
    # Data Collection
    # ─────────────────────────────────────────────────────────────────────────
    
    async def get_strongest_stocks(self, days: int = 7, limit: int = 20) -> List[Dict]:
        """Get strongest performing stocks based on cumulative gains.
        
        Uses limit_up_stocks data for stocks that had limit-ups,
        then calculates performance over the period.
        """
        if not db.pool:
            return []
        
        # Get stocks with most limit-ups in the period (strongest performers)
        rows = await db.pool.fetch("""
            SELECT 
                code, 
                name,
                COUNT(*) as limit_count,
                MAX(limit_times) as max_streak,
                SUM(change_pct) as total_change,
                AVG(change_pct) as avg_change
            FROM limit_up_stocks
            WHERE date >= CURRENT_DATE - INTERVAL '%s days'
              AND is_sealed = TRUE
            GROUP BY code, name
            ORDER BY limit_count DESC, total_change DESC
            LIMIT %s
        """ % (days, limit))
        
        return [dict(r) for r in rows]
    
    async def get_weakest_stocks(self, days: int = 7, limit: int = 20) -> List[Dict]:
        """Get weakest performing stocks.
        
        Uses AkShare to get stocks with worst performance.
        """
        ak = self._get_akshare()
        if not ak:
            return []
        
        try:
            # Get stocks ranked by performance (ascending = weakest first)
            df = await asyncio.to_thread(ak.stock_zh_a_spot_em)
            
            if df is None or df.empty:
                return []
            
            # Sort by change percentage ascending (worst first)
            df = df.sort_values(by='涨跌幅', ascending=True)
            
            result = []
            for _, row in df.head(limit).iterrows():
                change_pct = row.get('涨跌幅', 0)
                if change_pct is None or (isinstance(change_pct, str) and change_pct == '--'):
                    continue
                result.append({
                    "code": str(row.get("代码", "")),
                    "name": str(row.get("名称", "")),
                    "change_pct": float(change_pct) if change_pct else 0,
                    "close_price": float(row.get("最新价", 0) or 0),
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get weakest stocks: {e}")
            return []
    
    async def get_strongest_sectors(self, days: int = 7, limit: int = 10) -> List[Dict]:
        """Get strongest sectors from sector_daily table."""
        if not db.pool:
            return []
        
        rows = await db.pool.fetch("""
            SELECT 
                code, 
                name,
                type,
                SUM(change_pct) as total_change,
                AVG(change_pct) as avg_change,
                COUNT(CASE WHEN change_pct > 0 THEN 1 END) as up_days,
                COUNT(*) as total_days
            FROM sector_daily
            WHERE date >= CURRENT_DATE - INTERVAL '%s days'
            GROUP BY code, name, type
            HAVING COUNT(*) >= %s
            ORDER BY total_change DESC
            LIMIT %s
        """ % (days, max(1, days // 3), limit))
        
        return [dict(r) for r in rows]
    
    async def get_weakest_sectors(self, days: int = 7, limit: int = 10) -> List[Dict]:
        """Get weakest sectors from sector_daily table."""
        if not db.pool:
            return []
        
        rows = await db.pool.fetch("""
            SELECT 
                code, 
                name,
                type,
                SUM(change_pct) as total_change,
                AVG(change_pct) as avg_change,
                COUNT(CASE WHEN change_pct < 0 THEN 1 END) as down_days,
                COUNT(*) as total_days
            FROM sector_daily
            WHERE date >= CURRENT_DATE - INTERVAL '%s days'
            GROUP BY code, name, type
            HAVING COUNT(*) >= %s
            ORDER BY total_change ASC
            LIMIT %s
        """ % (days, max(1, days // 3), limit))
        
        return [dict(r) for r in rows]
    
    # ─────────────────────────────────────────────────────────────────────────
    # AI Analysis
    # ─────────────────────────────────────────────────────────────────────────
    
    async def generate_ai_analysis(self, data: Dict, report_type: str = "weekly") -> str:
        """Generate AI-powered market analysis and prediction."""
        from app.services.ai import ai_service
        
        if not ai_service.is_available():
            return "AI分析暂不可用"
        
        # Build data summary for AI
        period_name = {
            "weekly": "本周",
            "monthly": "本月"
        }.get(report_type, "近期")
        
        strongest_stocks = data.get("strongest_stocks", [])
        weakest_stocks = data.get("weakest_stocks", [])
        strongest_sectors = data.get("strongest_sectors", [])
        weakest_sectors = data.get("weakest_sectors", [])
        
        # Format data for AI
        stock_summary = f"""
强势股（{period_name}涨停次数最多）:
{self._format_stock_list(strongest_stocks[:10])}

弱势股（跌幅最大）:
{self._format_stock_list(weakest_stocks[:10])}
"""
        
        sector_summary = f"""
强势板块:
{self._format_sector_list(strongest_sectors[:10])}

弱势板块:
{self._format_sector_list(weakest_sectors[:10])}
"""
        
        prompt = f"""你是一位专业的A股市场分析师。请根据以下{period_name}市场数据，提供专业的市场分析和展望。

{stock_summary}

{sector_summary}

请提供：
1. 市场整体态势分析（2-3句话）
2. 热点板块分析（重点分析强势板块的逻辑和持续性）
3. 风险提示（关注弱势板块和个股）
4. 下{period_name.replace('本', '')}展望和投资建议

要求：
- 语言专业简洁
- 分析要有逻辑支撑
- 观点要客观中立
- 总字数控制在500字以内
"""
        
        try:
            result = await ai_service.analyze(prompt)
            return result.get("content", "分析生成失败")
        except Exception as e:
            logger.error(f"AI analysis failed: {e}")
            return f"AI分析生成失败: {e}"
    
    def _format_stock_list(self, stocks: List[Dict]) -> str:
        """Format stock list for AI prompt."""
        if not stocks:
            return "暂无数据"
        
        lines = []
        for s in stocks:
            if 'limit_count' in s:
                lines.append(f"- {s['name']}({s['code']}): {s.get('limit_count', 0)}次涨停, 累计涨幅{s.get('total_change', 0):.1f}%")
            else:
                lines.append(f"- {s['name']}({s['code']}): {s.get('change_pct', 0):.2f}%")
        return "\n".join(lines)
    
    def _format_sector_list(self, sectors: List[Dict]) -> str:
        """Format sector list for AI prompt."""
        if not sectors:
            return "暂无数据"
        
        lines = []
        for s in sectors:
            type_name = "行业" if s.get('type') == 'industry' else "概念"
            lines.append(f"- {s['name']}({type_name}): 累计{s.get('total_change', 0):+.2f}%, {s.get('up_days', 0)}/{s.get('total_days', 0)}天上涨")
        return "\n".join(lines)
    
    # ─────────────────────────────────────────────────────────────────────────
    # Report Generation
    # ─────────────────────────────────────────────────────────────────────────
    
    async def generate_weekly_report(self, end_date: date = None) -> str:
        """Generate weekly market report (Friday 8 PM)."""
        end_date = end_date or date.today()
        start_date = end_date - timedelta(days=6)
        
        # Collect data
        strongest_stocks = await self.get_strongest_stocks(days=7, limit=20)
        weakest_stocks = await self.get_weakest_stocks(days=7, limit=20)
        strongest_sectors = await self.get_strongest_sectors(days=7, limit=10)
        weakest_sectors = await self.get_weakest_sectors(days=7, limit=10)
        
        data = {
            "strongest_stocks": strongest_stocks,
            "weakest_stocks": weakest_stocks,
            "strongest_sectors": strongest_sectors,
            "weakest_sectors": weakest_sectors,
        }
        
        # Generate AI analysis
        ai_analysis = await self.generate_ai_analysis(data, "weekly")
        
        # Build report
        report = self._build_report(
            title=f"A股周度市场报告 {start_date.strftime('%m/%d')}-{end_date.strftime('%m/%d')}",
            data=data,
            ai_analysis=ai_analysis,
            period_name="本周"
        )
        
        # Save to database
        await self._save_report("weekly", end_date, start_date, end_date, data, ai_analysis, report)
        
        return report
    
    async def generate_monthly_report(self, end_date: date = None) -> str:
        """Generate monthly market report."""
        end_date = end_date or date.today()
        start_date = end_date.replace(day=1)
        
        # Collect data
        days = (end_date - start_date).days + 1
        strongest_stocks = await self.get_strongest_stocks(days=days, limit=20)
        weakest_stocks = await self.get_weakest_stocks(days=days, limit=20)
        strongest_sectors = await self.get_strongest_sectors(days=days, limit=10)
        weakest_sectors = await self.get_weakest_sectors(days=days, limit=10)
        
        data = {
            "strongest_stocks": strongest_stocks,
            "weakest_stocks": weakest_stocks,
            "strongest_sectors": strongest_sectors,
            "weakest_sectors": weakest_sectors,
        }
        
        # Generate AI analysis
        ai_analysis = await self.generate_ai_analysis(data, "monthly")
        
        # Build report
        report = self._build_report(
            title=f"A股月度市场报告 {start_date.strftime('%Y年%m月')}",
            data=data,
            ai_analysis=ai_analysis,
            period_name="本月"
        )
        
        # Save to database
        await self._save_report("monthly", end_date, start_date, end_date, data, ai_analysis, report)
        
        return report
    
    async def generate_on_demand_report(self, until_date: datetime = None, days: int = 7) -> str:
        """Generate report on-demand with data up to specified time.
        
        Args:
            until_date: End datetime for the report (defaults to now)
            days: Number of days to analyze (default 7)
        """
        if until_date is None:
            until_date = datetime.now(CHINA_TZ)
        
        end_date = until_date.date()
        start_date = end_date - timedelta(days=days-1)
        
        # Collect data
        strongest_stocks = await self.get_strongest_stocks(days=days, limit=20)
        weakest_stocks = await self.get_weakest_stocks(days=days, limit=20)
        strongest_sectors = await self.get_strongest_sectors(days=days, limit=10)
        weakest_sectors = await self.get_weakest_sectors(days=days, limit=10)
        
        data = {
            "strongest_stocks": strongest_stocks,
            "weakest_stocks": weakest_stocks,
            "strongest_sectors": strongest_sectors,
            "weakest_sectors": weakest_sectors,
        }
        
        # Generate AI analysis
        ai_analysis = await self.generate_ai_analysis(data, "weekly")
        
        # Build report
        report = self._build_report(
            title=f"A股市场分析 {start_date.strftime('%m/%d')}-{end_date.strftime('%m/%d')} (即时)",
            data=data,
            ai_analysis=ai_analysis,
            period_name=f"近{days}日"
        )
        
        return report
    
    def _build_report(self, title: str, data: Dict, ai_analysis: str, period_name: str) -> str:
        """Build formatted report content."""
        lines = [
            f"📊 <b>{title}</b>",
            "━━━━━━━━━━━━━━━━━━━━━",
        ]
        
        # Strongest stocks
        strongest_stocks = data.get("strongest_stocks", [])
        if strongest_stocks:
            lines.append(f"\n📈 <b>{period_name}强势股 TOP10</b>\n")
            for i, s in enumerate(strongest_stocks[:10], 1):
                limit_info = f"[{s.get('limit_count', 0)}次涨停]" if s.get('limit_count', 0) > 0 else ""
                change = f"{s.get('total_change', 0):+.1f}%" if s.get('total_change') else ""
                lines.append(f"{i}. {s['name']} ({s['code']}) {limit_info} {change}")
        
        # Weakest stocks
        weakest_stocks = data.get("weakest_stocks", [])
        if weakest_stocks:
            lines.append(f"\n📉 <b>{period_name}弱势股 TOP10</b>\n")
            for i, s in enumerate(weakest_stocks[:10], 1):
                change = f"{s.get('change_pct', 0):+.2f}%"
                lines.append(f"{i}. {s['name']} ({s['code']}) {change}")
        
        # Strongest sectors
        strongest_sectors = data.get("strongest_sectors", [])
        if strongest_sectors:
            lines.append(f"\n🔥 <b>{period_name}强势板块</b>\n")
            for i, s in enumerate(strongest_sectors[:10], 1):
                type_icon = "🏭" if s.get('type') == 'industry' else "💡"
                pct = f"{s.get('total_change', 0):+.2f}%"
                win_rate = f"({s.get('up_days', 0)}/{s.get('total_days', 0)}天涨)"
                lines.append(f"{i}. {type_icon} {s['name']} {pct} {win_rate}")
        
        # Weakest sectors
        weakest_sectors = data.get("weakest_sectors", [])
        if weakest_sectors:
            lines.append(f"\n📉 <b>{period_name}弱势板块</b>\n")
            for i, s in enumerate(weakest_sectors[:5], 1):
                type_icon = "🏭" if s.get('type') == 'industry' else "💡"
                pct = f"{s.get('total_change', 0):+.2f}%"
                lines.append(f"{i}. {type_icon} {s['name']} {pct}")
        
        # AI Analysis
        if ai_analysis:
            lines.append("\n🤖 <b>AI市场分析</b>\n")
            lines.append(ai_analysis)
        
        lines.append("\n━━━━━━━━━━━━━━━━━━━━━")
        
        return "\n".join(lines)
    
    async def _save_report(self, report_type: str, report_date: date, 
                          period_start: date, period_end: date,
                          data: Dict, ai_analysis: str, content: str):
        """Save report to database."""
        if not db.pool:
            return
        
        try:
            await db.pool.execute("""
                INSERT INTO market_reports 
                (report_type, report_date, period_start, period_end, 
                 strongest_stocks, weakest_stocks, strongest_sectors, weakest_sectors,
                 ai_analysis, content)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (report_type, report_date) DO UPDATE SET
                    period_start = EXCLUDED.period_start,
                    period_end = EXCLUDED.period_end,
                    strongest_stocks = EXCLUDED.strongest_stocks,
                    weakest_stocks = EXCLUDED.weakest_stocks,
                    strongest_sectors = EXCLUDED.strongest_sectors,
                    weakest_sectors = EXCLUDED.weakest_sectors,
                    ai_analysis = EXCLUDED.ai_analysis,
                    content = EXCLUDED.content
            """, 
                report_type, report_date, period_start, period_end,
                json.dumps(data.get("strongest_stocks", [])),
                json.dumps(data.get("weakest_stocks", [])),
                json.dumps(data.get("strongest_sectors", [])),
                json.dumps(data.get("weakest_sectors", [])),
                ai_analysis, content
            )
            logger.info(f"Saved {report_type} report for {report_date}")
        except Exception as e:
            logger.error(f"Failed to save report: {e}")
    
    async def get_latest_report(self, report_type: str = None) -> Optional[Dict]:
        """Get the latest report from database."""
        if not db.pool:
            return None
        
        type_filter = "WHERE report_type = $1" if report_type else ""
        
        query = f"""
            SELECT * FROM market_reports 
            {type_filter}
            ORDER BY report_date DESC 
            LIMIT 1
        """
        
        if report_type:
            row = await db.pool.fetchrow(query, report_type)
        else:
            row = await db.pool.fetchrow(query)
        
        return dict(row) if row else None
    
    # ─────────────────────────────────────────────────────────────────────────
    # Sending Reports
    # ─────────────────────────────────────────────────────────────────────────
    
    async def send_weekly_report(self):
        """Send weekly report to Telegram."""
        from app.core.bot import telegram_service
        
        if not settings.REPORT_TARGET_CHANNEL:
            return
        
        report = await self.generate_weekly_report()
        
        await telegram_service.send_message(
            settings.REPORT_TARGET_CHANNEL, report,
            parse_mode="html",
            link_preview=False
        )
        logger.info("Sent weekly market report")
    
    async def send_monthly_report(self):
        """Send monthly report to Telegram."""
        from app.core.bot import telegram_service
        
        if not settings.REPORT_TARGET_CHANNEL:
            return
        
        report = await self.generate_monthly_report()
        
        await telegram_service.send_message(
            settings.REPORT_TARGET_CHANNEL, report,
            parse_mode="html",
            link_preview=False
        )
        logger.info("Sent monthly market report")
    
    # ─────────────────────────────────────────────────────────────────────────
    # Scheduler
    # ─────────────────────────────────────────────────────────────────────────
    
    async def _scheduler_loop(self):
        """Background scheduler for timed reports.
        
        - 20:00 Friday: Weekly report
        - 20:00 Last trading day of month: Monthly report
        """
        report_time = "20:00"
        
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
                if now.weekday() < 5 and time_str == report_time:
                    # Weekly report (Friday)
                    if now.weekday() == 4 and f"weekly_{date_str}" not in triggered_today:
                        triggered_today.add(f"weekly_{date_str}")
                        asyncio.create_task(self.send_weekly_report())
                    
                    # Monthly report (last trading day - simplified: last weekday)
                    next_day = now.date() + timedelta(days=1)
                    if next_day.month != now.month and f"monthly_{date_str}" not in triggered_today:
                        triggered_today.add(f"monthly_{date_str}")
                        asyncio.create_task(self.send_monthly_report())
                
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
            
            # Check every 30 seconds
            await asyncio.sleep(30)


# Singleton
market_report_service = MarketReportService()
