"""
打板 (Limit-Up Board) 盘后复盘服务

Post-close review of limit-up stocks with scoring.
NOT for intraday trading decisions - uses post-close data snapshot.

Scoring factors:
- Seal strength (封单强度)
- Limit-up timing (涨停时间)
- Board type with market context (板型+情绪)
- Turnover rate (换手率)
- Market cap (流通市值)
- Executability filters (可执行性过滤)
"""

import asyncio
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Tuple
from decimal import Decimal
from collections import defaultdict

from app.core.logger import Logger
from app.core.database import db
from app.core.config import settings
from app.core.timezone import CHINA_TZ, china_now, china_today

logger = Logger("DabanService")


# Scoring weights (sector_heat removed - was fake data)
SCORE_WEIGHTS = {
    'seal_strength': 30,    # 封单强度 (封单额/成交额)
    'limit_time': 25,       # 涨停时间 (交易时段)
    'board_type': 20,       # 板型 (相对市场高度)
    'turnover': 15,         # 换手率 (适中为佳)
    'market_cap': 10,       # 市值 (中小市值加分)
}

# Executability flags
class ExecutabilityFlag:
    OK = "ok"                    # 可打
    YIZI_BOARD = "yizi"          # 一字板，无法买入
    WEAK_TAIL = "weak_tail"      # 尾盘弱封
    HIGH_RISK = "high_risk"      # 高风险高位
    BURST_MANY = "burst_many"    # 多次炸板
    OBSERVE = "observe"          # 观望


class DabanService:
    """打板 盘后复盘 + 盘中实时信号服务."""
    
    def __init__(self):
        self.is_running = False
        self._scheduler_task = None
        self._intraday_task = None  # Phase 3: intraday polling
        self._ak = None
        self._last_date = None  # For date change detection
        self._triggered_today = set()
        
        # Stats for observability
        self._stats = defaultdict(int)
        
        # Phase 3: Intraday state tracking
        self._intraday_state = {}  # {code: {seal, limit_since, burst_count, ...}}
        self._signal_history = []  # Recent signals for display
        self._notify_callback = None

    
    def _get_akshare(self):
        """Lazy load akshare module."""
        if self._ak is None:
            try:
                import akshare as ak
                self._ak = ak
            except ImportError:
                logger.error("AkShare not installed")
                return None
        return self._ak
    
    async def start(self):
        """Start the 打板 service."""
        if self.is_running:
            return
        # Initialize Phase 2 tables
        await self.ensure_phase2_tables()
        self.is_running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        self._intraday_task = asyncio.create_task(self._intraday_loop())  # Phase 3
        logger.info("✅ 打板 盘后复盘 + 实时监控 started")
    
    async def stop(self):
        """Stop the service."""
        self.is_running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        if self._intraday_task:
            self._intraday_task.cancel()
            try:
                await self._intraday_task
            except asyncio.CancelledError:
                pass
        logger.info("打板 service stopped")
    
    def _get_limit_percent(self, code: str, name: str) -> float:
        """Get limit percent based on stock type."""
        # 北交所 8x = 30%
        if code.startswith('8') and len(code) == 6:
            return 30.0
        # 科创板 68x, 创业板 30x = 20%
        if code.startswith('68') or code.startswith('30'):
            return 20.0
        # ST股 = 5% (should be filtered, but just in case)
        if 'ST' in name or '*ST' in name:
            return 5.0
        # 主板 = 10%
        return 10.0
    
    def _score_time(self, first_limit_time: str) -> Tuple[int, str]:
        """
        Score limit-up time by trading sessions.
        Returns (score, session_label).
        
        Trading hours:
        - 09:30-09:45: 强势开盘板 (100)
        - 09:45-10:30: 早盘强板 (85)
        - 10:30-11:30: 早盘板 (70)
        - 13:00-14:00: 午盘板 (55)
        - 14:00-14:30: 午后板 (40)
        - 14:30-15:00: 尾盘板 (20, 风险)
        - Invalid/Other: (30, 异常)
        """
        if not first_limit_time or len(first_limit_time) < 4:
            return 30, "异常"
        
        try:
            parts = first_limit_time.replace(":", "")
            if len(parts) >= 4:
                hour = int(parts[:2])
                minute = int(parts[2:4])
            else:
                return 30, "异常"
            
            # Convert to minutes from midnight for easier comparison
            time_mins = hour * 60 + minute
            
            # Before market open
            if time_mins < 570:  # Before 09:30
                return 30, "异常"
            
            # 09:30-09:45 (570-585)
            if time_mins < 585:
                return 100, "开盘强板"
            
            # 09:45-10:30 (585-630)
            if time_mins < 630:
                return 85, "早盘强板"
            
            # 10:30-11:30 (630-690)
            if time_mins < 690:
                return 70, "早盘板"
            
            # 11:30-13:00 is lunch break - shouldn't happen
            if time_mins < 780:  # Before 13:00
                return 30, "午休异常"
            
            # 13:00-14:00 (780-840)
            if time_mins < 840:
                return 55, "午盘板"
            
            # 14:00-14:30 (840-870)
            if time_mins < 870:
                return 40, "午后板"
            
            # 14:30-15:00 (870-900)
            if time_mins <= 900:
                return 20, "尾盘板"
            
            # After close
            return 30, "异常"
            
        except (ValueError, IndexError):
            self._stats['time_parse_error'] += 1
            return 30, "解析失败"
    
    def _check_executability(self, stock: Dict) -> Tuple[str, str]:
        """
        Check if stock is executable for 打板.
        Returns (flag, reason).
        """
        turnover = stock.get('turnover_rate', 0)
        seal_ratio = stock.get('seal_ratio', 0)
        limit_times = stock.get('limit_times', 1)
        first_limit_time = stock.get('first_limit_time', '')
        time_score, _ = self._score_time(first_limit_time)
        
        # 一字板: Very low turnover with high seal = can't buy
        if turnover < 0.5 and seal_ratio > 10:
            return ExecutabilityFlag.YIZI_BOARD, "一字板(无法买入)"
        
        # 尾盘弱封: Late time + weak seal
        if time_score <= 20 and seal_ratio < 2:
            return ExecutabilityFlag.WEAK_TAIL, "尾盘弱封(骗炮风险)"
        
        # 高风险高位: 4+ boards with high turnover
        if limit_times >= 4 and turnover > 20:
            return ExecutabilityFlag.HIGH_RISK, "高位放量(核按钮风险)"
        
        # Low turnover one-line board (even if not extreme)
        if turnover < 1.0 and limit_times >= 2:
            return ExecutabilityFlag.YIZI_BOARD, "缩量一字(难买入)"
        
        # 尾盘板 (after 14:30) - mark as observe
        if time_score <= 20:
            return ExecutabilityFlag.OBSERVE, "尾盘板(观望)"
        
        return ExecutabilityFlag.OK, ""
    
    async def get_market_context(self, target_date: date = None) -> Dict:
        """
        Get market context for adaptive scoring.
        Returns: max_streak, total_limit_ups, promotion_rate_2b, etc.
        """
        ak = self._get_akshare()
        if not ak:
            return {'max_streak': 5, 'total_limit_ups': 50}
        
        target_date = target_date or china_today()
        date_str = target_date.strftime("%Y%m%d")
        
        try:
            df = await asyncio.to_thread(ak.stock_zt_pool_em, date=date_str)
            
            if df is None or df.empty:
                return {'max_streak': 5, 'total_limit_ups': 0}
            
            total = len(df)
            max_streak = df['连板数'].max() if '连板数' in df.columns else 1
            
            # Count by streak
            streak_counts = {}
            if '连板数' in df.columns:
                for streak in df['连板数']:
                    streak_counts[int(streak)] = streak_counts.get(int(streak), 0) + 1
            
            # Calculate 2板晋级率 (how many 1板 became 2板)
            # This would need previous day data - simplified for now
            shouban_count = streak_counts.get(1, 0)
            erban_count = streak_counts.get(2, 0)
            
            return {
                'max_streak': int(max_streak),
                'total_limit_ups': total,
                'shouban_count': shouban_count,
                'erban_count': erban_count,
                'streak_counts': streak_counts,
            }
            
        except Exception as e:
            logger.warn(f"Failed to get market context: {e}")
            return {'max_streak': 5, 'total_limit_ups': 50}
    
    async def analyze_daban_candidates(self, target_date: date = None) -> Tuple[List[Dict], Dict]:
        """
        Analyze and score all limit-up stocks for 打板 potential.
        
        Returns (candidates_list, stats_dict).
        """
        # Reset stats
        self._stats = defaultdict(int)
        
        ak = self._get_akshare()
        if not ak:
            return [], {}
        
        target_date = target_date or china_today()
        date_str = target_date.strftime("%Y%m%d")
        
        # Get market context first
        market_ctx = await self.get_market_context(target_date)
        max_streak = market_ctx.get('max_streak', 5)
        
        try:
            df = await asyncio.to_thread(ak.stock_zt_pool_em, date=date_str)
            
            if df is None or df.empty:
                logger.info(f"No limit-up stocks found for {date_str}")
                return [], {'total': 0}
            
            candidates = []
            
            for _, row in df.iterrows():
                try:
                    code = str(row.get('代码', ''))
                    name = str(row.get('名称', ''))
                    
                    # Skip ST and special stocks
                    if 'ST' in name or '*ST' in name:
                        self._stats['filtered_st'] += 1
                        continue
                    if name.startswith('N') or name.startswith('C'):
                        self._stats['filtered_new'] += 1
                        continue
                    
                    # Extract data
                    price = float(row.get('最新价', 0) or 0)
                    change_pct = float(row.get('涨跌幅', 0) or 0)
                    turnover_rate = float(row.get('换手率', 0) or 0)
                    market_cap = float(row.get('流通市值', 0) or 0) / 100000000  # 亿
                    seal_amount = float(row.get('封单额', 0) or 0) / 100000000  # 亿
                    turnover_amount = float(row.get('成交额', 0) or 0) / 100000000  # 当日成交额
                    limit_times = int(row.get('连板数', 1) or 1)
                    first_limit_time = str(row.get('首次涨停时间', '') or '')
                    
                    # Check for missing critical data
                    if market_cap == 0:
                        self._stats['missing_market_cap'] += 1
                    if turnover_amount == 0:
                        self._stats['missing_turnover_amount'] += 1
                    
                    # Calculate scores
                    score_breakdown = {}
                    total_score = 0
                    
                    # 1. Seal Strength Score - now uses 封单额/成交额 ratio
                    if turnover_amount > 0:
                        seal_vs_turnover = seal_amount / turnover_amount * 100
                    elif market_cap > 0:
                        seal_vs_turnover = seal_amount / market_cap * 100
                    else:
                        seal_vs_turnover = 0
                    
                    if seal_vs_turnover >= 50:
                        seal_score = 100
                    elif seal_vs_turnover >= 30:
                        seal_score = 85
                    elif seal_vs_turnover >= 15:
                        seal_score = 70
                    elif seal_vs_turnover >= 5:
                        seal_score = 50
                    else:
                        seal_score = 30
                    
                    score_breakdown['seal_strength'] = seal_score
                    total_score += seal_score * SCORE_WEIGHTS['seal_strength'] / 100
                    
                    # 2. Limit Time Score (proper trading sessions)
                    time_score, time_label = self._score_time(first_limit_time)
                    score_breakdown['limit_time'] = time_score
                    total_score += time_score * SCORE_WEIGHTS['limit_time'] / 100
                    
                    # 3. Board Type Score (relative to market height)
                    # Adaptive: score based on position relative to max_streak
                    relative_position = limit_times / max(max_streak, 1)
                    
                    if limit_times == 1:
                        board_score = 60  # 首板 baseline
                        board_type = "首板"
                    elif limit_times == 2:
                        board_score = 75  # 二板 sweet spot
                        board_type = "二连板"
                    elif limit_times == 3:
                        board_score = 85 if relative_position < 0.6 else 70  # 三板
                        board_type = "三连板"
                    elif limit_times >= 4:
                        # High boards: good if market hot, risky if at max
                        if relative_position >= 0.9:
                            board_score = 50  # At market peak = high risk
                        elif relative_position >= 0.7:
                            board_score = 70
                        else:
                            board_score = 85
                        board_type = f"{limit_times}连板"
                    else:
                        board_score = 50
                        board_type = "未知"
                    
                    score_breakdown['board_type'] = board_score
                    total_score += board_score * SCORE_WEIGHTS['board_type'] / 100
                    
                    # 4. Turnover Rate Score
                    if limit_times == 1:
                        # 首板: 5-15% optimal
                        if 5 <= turnover_rate <= 15:
                            turnover_score = 100
                        elif 3 <= turnover_rate < 5 or 15 < turnover_rate <= 20:
                            turnover_score = 70
                        elif turnover_rate > 25:
                            turnover_score = 40
                        else:
                            turnover_score = 50
                    else:
                        # 连板: lower turnover = stronger
                        if turnover_rate <= 5:
                            turnover_score = 100
                        elif turnover_rate <= 10:
                            turnover_score = 80
                        elif turnover_rate <= 15:
                            turnover_score = 60
                        else:
                            turnover_score = 40
                    
                    score_breakdown['turnover'] = turnover_score
                    total_score += turnover_score * SCORE_WEIGHTS['turnover'] / 100
                    
                    # 5. Market Cap Score
                    if 10 <= market_cap <= 50:
                        cap_score = 100
                    elif 5 <= market_cap < 10 or 50 < market_cap <= 100:
                        cap_score = 75
                    elif market_cap < 5:
                        cap_score = 50
                    elif market_cap <= 200:
                        cap_score = 50
                    else:
                        cap_score = 30
                    
                    score_breakdown['market_cap'] = cap_score
                    total_score += cap_score * SCORE_WEIGHTS['market_cap'] / 100
                    
                    # Determine limit percent
                    limit_pct = self._get_limit_percent(code, name)
                    
                    # Check executability
                    stock_data = {
                        'turnover_rate': turnover_rate,
                        'seal_ratio': seal_vs_turnover,
                        'limit_times': limit_times,
                        'first_limit_time': first_limit_time,
                    }
                    exec_flag, exec_reason = self._check_executability(stock_data)
                    
                    # Penalize score for non-executable stocks
                    if exec_flag == ExecutabilityFlag.YIZI_BOARD:
                        total_score *= 0.5
                    elif exec_flag == ExecutabilityFlag.WEAK_TAIL:
                        total_score *= 0.6
                    elif exec_flag == ExecutabilityFlag.HIGH_RISK:
                        total_score *= 0.7
                    
                    candidates.append({
                        'code': code,
                        'name': name,
                        'price': price,
                        'change_pct': change_pct,
                        'limit_pct': limit_pct,
                        'turnover_rate': turnover_rate,
                        'turnover_amount': turnover_amount,
                        'market_cap': market_cap,
                        'seal_amount': seal_amount,
                        'seal_ratio': seal_vs_turnover,
                        'limit_times': limit_times,
                        'board_type': board_type,
                        'first_limit_time': first_limit_time,
                        'time_label': time_label,
                        'score': round(total_score, 1),
                        'score_breakdown': score_breakdown,
                        'exec_flag': exec_flag,
                        'exec_reason': exec_reason,
                    })
                    
                except Exception as e:
                    self._stats['parse_error'] += 1
                    logger.debug(f"Error processing stock: {e}")
                    continue
            
            # Sort by score descending
            candidates.sort(key=lambda x: x['score'], reverse=True)
            
            # Build stats
            stats = {
                'total': len(candidates),
                'market_max_streak': max_streak,
                'shouban_count': market_ctx.get('shouban_count', 0),
                'erban_count': market_ctx.get('erban_count', 0),
                'executable_count': sum(1 for c in candidates if c['exec_flag'] == ExecutabilityFlag.OK),
                'yizi_count': sum(1 for c in candidates if c['exec_flag'] == ExecutabilityFlag.YIZI_BOARD),
                'parse_errors': self._stats.get('parse_error', 0),
            }
            
            logger.info(f"Analyzed {len(candidates)} candidates, {stats['executable_count']} executable")
            return candidates, stats
            
        except Exception as e:
            logger.error(f"Failed to analyze candidates: {e}")
            return [], {}
    
    async def get_buy_recommendations(self, top_n: int = 5) -> List[Dict]:
        """Get top N executable 打板 recommendations."""
        candidates, _ = await self.analyze_daban_candidates()
        
        # Only recommend executable stocks with score >= 60
        recommendations = [
            c for c in candidates 
            if c['score'] >= 60 and c['exec_flag'] == ExecutabilityFlag.OK
        ]
        
        return recommendations[:top_n]
    
    async def generate_daban_report(self) -> str:
        """Generate 打板 post-close review report."""
        candidates, stats = await self.analyze_daban_candidates()
        
        if not candidates:
            return "📊 <b>打板复盘</b>\n\n暂无涨停股票"
        
        now = china_now()
        lines = [
            "📊 <b>打板盘后复盘</b>",
            f"<i>{now.strftime('%Y-%m-%d %H:%M')}</i>",
            f"涨停 {stats.get('total', 0)} 只 | 最高板 {stats.get('market_max_streak', 0)} | 可打 {stats.get('executable_count', 0)}只\n",
            "━━━━━━━━━━━━━━━━━━━━━"
        ]
        
        # Top recommendations (executable, score >= 70)
        top_exec = [c for c in candidates if c['exec_flag'] == ExecutabilityFlag.OK and c['score'] >= 70]
        if top_exec:
            lines.append("\n🎯 <b>可打标的</b>")
            for c in top_exec[:5]:
                sb = c['score_breakdown']
                lines.append(
                    f"🟢 <b>{c['name']}</b> ({c['code']})\n"
                    f"   {c['board_type']} | 总分: <b>{c['score']}</b>\n"
                    f"   封:{sb['seal_strength']} 时:{sb['limit_time']} 板:{sb['board_type']} 换:{sb['turnover']} 值:{sb['market_cap']}\n"
                    f"   {c['time_label']} | 封单: {c['seal_amount']:.1f}亿 | 换手: {c['turnover_rate']:.1f}%"
                )
        
        # Observe stocks (尾盘板, etc)
        observe = [c for c in candidates if c['exec_flag'] == ExecutabilityFlag.OBSERVE and c['score'] >= 60]
        if observe:
            lines.append("\n👀 <b>观望标的</b>")
            for c in observe[:3]:
                lines.append(f"⚪ {c['name']} ({c['code']}) - {c['exec_reason']} | 分:{c['score']}")
        
        # 一字板 (for reference)
        yizi = [c for c in candidates if c['exec_flag'] == ExecutabilityFlag.YIZI_BOARD][:3]
        if yizi:
            lines.append("\n🔒 <b>一字板(无法买入)</b>")
            for c in yizi:
                lines.append(f"• {c['name']} ({c['code']}) - {c['board_type']}")
        
        # High risk
        high_risk = [c for c in candidates if c['exec_flag'] == ExecutabilityFlag.HIGH_RISK]
        if high_risk:
            lines.append("\n⚠️ <b>高风险(慎重)</b>")
            for c in high_risk[:3]:
                lines.append(f"🔴 {c['name']} ({c['code']}) - {c['exec_reason']}")
        
        # Stats footer
        lines.append(f"\n<i>首板{stats.get('shouban_count', 0)} 二板{stats.get('erban_count', 0)} 一字{stats.get('yizi_count', 0)}</i>")
        
        return "\n".join(lines)
    
    async def send_daban_report(self):
        """Send 打板 report to configured channel."""
        try:
            from app.bots.registry import get_bot
            bot = get_bot("crawler")
            
            if bot and settings.REPORT_TARGET_CHANNEL:
                report = await self.generate_daban_report()
                await bot.send_message(
                    int(settings.REPORT_TARGET_CHANNEL),
                    report,
                    parse_mode="HTML"
                )
                logger.info("打板复盘 report sent")
        except Exception as e:
            logger.error(f"Failed to send 打板 report: {e}")
    
    async def _scheduler_loop(self):
        """
        Background scheduler for 打板 reports and Phase 2 tracking.
        
        Schedule:
        - 15:05: Send daily report
        - 15:10: Save market stats + recommendations
        - 09:40: Update yesterday's recommendation performance
        """
        schedules = [
            (15, 5, 'daily_report'),
            (15, 10, 'save_stats'),
            (9, 40, 'update_perf'),
        ]
        
        while self.is_running:
            try:
                now = china_now()
                current_date = now.strftime("%Y-%m-%d")
                
                # Date change detection - clear triggered set
                if self._last_date and self._last_date != current_date:
                    self._triggered_today.clear()
                    logger.debug("Cleared triggered set for new day")
                self._last_date = current_date
                
                # Skip weekends
                if now.weekday() >= 5:
                    await asyncio.sleep(60)
                    continue
                
                for sched_hour, sched_min, task in schedules:
                    key = f"{current_date}_{task}"
                    
                    if key not in self._triggered_today:
                        target_time = now.replace(hour=sched_hour, minute=sched_min, second=0, microsecond=0)
                        time_diff = abs((now - target_time).total_seconds())
                        
                        if time_diff < 60:  # Within 1 minute window
                            self._triggered_today.add(key)
                            logger.info(f"Triggering 打板 task: {task}")
                            
                            if task == 'daily_report':
                                await self.send_daban_report()
                            elif task == 'save_stats':
                                await self.save_market_stats()
                                await self.save_recommendations()
                            elif task == 'update_perf':
                                await self.update_recommendation_performance()
                
            except Exception as e:
                logger.error(f"打板 scheduler error: {e}")
            
            await asyncio.sleep(30)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Phase 2: Market Sentiment & Recommendation Tracking
    # ═══════════════════════════════════════════════════════════════════════════
    
    async def ensure_phase2_tables(self):
        """Create Phase 2 database tables."""
        if not db.pool:
            return
        
        try:
            # Market sentiment daily stats
            await db.pool.execute("""
                CREATE TABLE IF NOT EXISTS daban_market_stats (
                    id SERIAL PRIMARY KEY,
                    stat_date DATE UNIQUE,
                    total_limit_ups INT,
                    max_streak INT,
                    shouban_count INT,
                    erban_count INT,
                    sanban_count INT,
                    sibanplus_count INT,
                    yizi_count INT,
                    burst_count INT,
                    promotion_rate_2b DECIMAL(5,2),
                    promotion_rate_3b DECIMAL(5,2),
                    avg_turnover DECIMAL(5,2),
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            # Daily recommendations with next-day performance tracking
            await db.pool.execute("""
                CREATE TABLE IF NOT EXISTS daban_recommendations (
                    id SERIAL PRIMARY KEY,
                    rec_date DATE,
                    code VARCHAR(10),
                    name VARCHAR(50),
                    rec_price DECIMAL(10,2),
                    score DECIMAL(5,2),
                    board_type VARCHAR(20),
                    limit_times INT,
                    exec_flag VARCHAR(20),
                    next_open DECIMAL(10,2),
                    next_high DECIMAL(10,2),
                    next_close DECIMAL(10,2),
                    next_limit_up BOOLEAN DEFAULT FALSE,
                    open_pct DECIMAL(6,2),
                    high_pct DECIMAL(6,2),
                    close_pct DECIMAL(6,2),
                    tracked BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(rec_date, code)
                )
            """)
            
            logger.info("✅ 打板 Phase 2 tables initialized")
        except Exception as e:
            logger.error(f"Failed to create Phase 2 tables: {e}")
    
    async def save_market_stats(self, target_date: date = None):
        """
        Calculate and save daily market sentiment stats.
        Call this at end of day (15:05+) to record the day's data.
        """
        if not db.pool:
            return
        
        target_date = target_date or china_today()
        candidates, stats = await self.analyze_daban_candidates(target_date)
        
        if not candidates:
            return
        
        # Calculate additional stats
        streak_counts = {}
        total_turnover = 0
        burst_count = 0
        
        for c in candidates:
            lt = c.get('limit_times', 1)
            streak_counts[lt] = streak_counts.get(lt, 0) + 1
            total_turnover += c.get('turnover_rate', 0)
            # Approximate burst detection: high turnover + not early board
            if c.get('turnover_rate', 0) > 15 and c.get('time_label', '') in ['午后板', '尾盘板']:
                burst_count += 1
        
        avg_turnover = total_turnover / len(candidates) if candidates else 0
        
        # Calculate promotion rates (need previous day data)
        shouban = streak_counts.get(1, 0)
        erban = streak_counts.get(2, 0)
        sanban = streak_counts.get(3, 0)
        sibanplus = sum(v for k, v in streak_counts.items() if k >= 4)
        
        # Note: True promotion rate needs yesterday's shouban count
        # For now, store the counts and can calculate later
        promotion_rate_2b = 0  # Will be calculated in get_market_sentiment
        promotion_rate_3b = 0
        
        try:
            await db.pool.execute("""
                INSERT INTO daban_market_stats 
                (stat_date, total_limit_ups, max_streak, shouban_count, erban_count,
                 sanban_count, sibanplus_count, yizi_count, burst_count,
                 promotion_rate_2b, promotion_rate_3b, avg_turnover)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                ON CONFLICT (stat_date) DO UPDATE SET
                    total_limit_ups = $2, max_streak = $3, shouban_count = $4,
                    erban_count = $5, sanban_count = $6, sibanplus_count = $7,
                    yizi_count = $8, burst_count = $9, promotion_rate_2b = $10,
                    promotion_rate_3b = $11, avg_turnover = $12
            """, target_date, len(candidates), stats.get('market_max_streak', 0),
                shouban, erban, sanban, sibanplus, stats.get('yizi_count', 0),
                burst_count, promotion_rate_2b, promotion_rate_3b, avg_turnover)
            
            logger.info(f"Saved market stats for {target_date}")
        except Exception as e:
            logger.error(f"Failed to save market stats: {e}")
    
    async def save_recommendations(self, target_date: date = None):
        """
        Save today's top recommendations for next-day tracking.
        Call this at end of day after market close.
        """
        if not db.pool:
            return
        
        target_date = target_date or china_today()
        recommendations = await self.get_buy_recommendations(top_n=10)
        
        if not recommendations:
            logger.info("No recommendations to save")
            return
        
        saved = 0
        for rec in recommendations:
            try:
                await db.pool.execute("""
                    INSERT INTO daban_recommendations
                    (rec_date, code, name, rec_price, score, board_type, 
                     limit_times, exec_flag)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (rec_date, code) DO NOTHING
                """, target_date, rec['code'], rec['name'], rec['price'],
                    rec['score'], rec['board_type'], rec['limit_times'], rec['exec_flag'])
                saved += 1
            except Exception as e:
                logger.warn(f"Failed to save recommendation {rec['code']}: {e}")
        
        logger.info(f"Saved {saved} recommendations for {target_date}")
    
    async def update_recommendation_performance(self, rec_date: date = None):
        """
        Update next-day performance for recommendations made on rec_date.
        Call this the day AFTER recommendations were made (after 15:00).
        """
        if not db.pool:
            return
        
        ak = self._get_akshare()
        if not ak:
            return
        
        # Get recommendations from previous trading day that haven't been tracked
        rows = await db.pool.fetch("""
            SELECT id, code, rec_price FROM daban_recommendations
            WHERE tracked = FALSE AND rec_date <= $1
            ORDER BY rec_date DESC
            LIMIT 50
        """, rec_date or china_today())
        
        if not rows:
            return
        
        # Get real-time/daily data
        try:
            df = await asyncio.to_thread(ak.stock_zh_a_spot_em)
            if df is None or df.empty:
                return
            
            price_map = {}
            for _, row in df.iterrows():
                code = str(row.get('代码', ''))
                price_map[code] = {
                    'open': float(row.get('今开', 0) or 0),
                    'high': float(row.get('最高', 0) or 0),
                    'close': float(row.get('最新价', 0) or 0),
                    'change_pct': float(row.get('涨跌幅', 0) or 0),
                }
            
            updated = 0
            for rec in rows:
                code = rec['code']
                if code not in price_map:
                    continue
                
                p = price_map[code]
                rec_price = float(rec['rec_price'])
                
                if rec_price == 0:
                    continue
                
                open_pct = (p['open'] - rec_price) / rec_price * 100
                high_pct = (p['high'] - rec_price) / rec_price * 100
                close_pct = (p['close'] - rec_price) / rec_price * 100
                
                # Check if hit limit again (within 0.5% of limit)
                next_limit_up = p['change_pct'] >= 9.5  # Simplified check
                
                try:
                    await db.pool.execute("""
                        UPDATE daban_recommendations
                        SET next_open = $1, next_high = $2, next_close = $3,
                            next_limit_up = $4, open_pct = $5, high_pct = $6,
                            close_pct = $7, tracked = TRUE
                        WHERE id = $8
                    """, p['open'], p['high'], p['close'], next_limit_up,
                        open_pct, high_pct, close_pct, rec['id'])
                    updated += 1
                except Exception as e:
                    logger.warn(f"Failed to update performance: {e}")
            
            logger.info(f"Updated {updated} recommendation performances")
            
        except Exception as e:
            logger.error(f"Failed to update performances: {e}")
    
    async def get_market_sentiment(self, days: int = 7) -> Dict:
        """
        Get market sentiment summary over recent days.
        Calculates promotion rates and trend indicators.
        """
        if not db.pool:
            return {}
        
        rows = await db.pool.fetch("""
            SELECT * FROM daban_market_stats
            ORDER BY stat_date DESC
            LIMIT $1
        """, days)
        
        if not rows:
            return {}
        
        # Calculate averages and trends
        total_limits = [r['total_limit_ups'] for r in rows]
        max_streaks = [r['max_streak'] for r in rows]
        
        # Calculate actual promotion rates using consecutive days
        promotion_2b_rates = []
        for i in range(len(rows) - 1):
            today_erban = rows[i]['erban_count']
            yesterday_shouban = rows[i + 1]['shouban_count']
            if yesterday_shouban > 0:
                rate = today_erban / yesterday_shouban * 100
                promotion_2b_rates.append(rate)
        
        return {
            'days_analyzed': len(rows),
            'avg_limit_ups': sum(total_limits) / len(total_limits),
            'avg_max_streak': sum(max_streaks) / len(max_streaks),
            'latest_max_streak': rows[0]['max_streak'] if rows else 0,
            'promotion_2b_avg': sum(promotion_2b_rates) / len(promotion_2b_rates) if promotion_2b_rates else 0,
            'trend': 'up' if len(rows) >= 2 and rows[0]['total_limit_ups'] > rows[1]['total_limit_ups'] else 'down',
        }
    
    async def get_recommendation_performance_stats(self, days: int = 30) -> Dict:
        """
        Calculate performance statistics for past recommendations.
        This is the backtest result.
        """
        if not db.pool:
            return {}
        
        rows = await db.pool.fetch("""
            SELECT * FROM daban_recommendations
            WHERE tracked = TRUE
            ORDER BY rec_date DESC
            LIMIT $1
        """, days * 10)  # Roughly 10 recommendations per day
        
        if not rows:
            return {}
        
        total = len(rows)
        open_positive = sum(1 for r in rows if r['open_pct'] and r['open_pct'] > 0)
        high_over_5 = sum(1 for r in rows if r['high_pct'] and r['high_pct'] >= 5)
        close_positive = sum(1 for r in rows if r['close_pct'] and r['close_pct'] > 0)
        limit_continued = sum(1 for r in rows if r['next_limit_up'])
        
        avg_open = sum(r['open_pct'] for r in rows if r['open_pct']) / total if total else 0
        avg_high = sum(r['high_pct'] for r in rows if r['high_pct']) / total if total else 0
        avg_close = sum(r['close_pct'] for r in rows if r['close_pct']) / total if total else 0
        
        return {
            'total_tracked': total,
            'open_positive_rate': open_positive / total * 100 if total else 0,
            'high_over_5pct_rate': high_over_5 / total * 100 if total else 0,
            'close_positive_rate': close_positive / total * 100 if total else 0,
            'limit_continue_rate': limit_continued / total * 100 if total else 0,
            'avg_next_open_pct': avg_open,
            'avg_next_high_pct': avg_high,
            'avg_next_close_pct': avg_close,
        }
    
    async def generate_sentiment_report(self) -> str:
        """Generate market sentiment report."""
        sentiment = await self.get_market_sentiment(days=7)
        perf = await self.get_recommendation_performance_stats(days=14)
        
        if not sentiment:
            return "📊 <b>市场情绪</b>\n\n暂无数据，请确保已收集数据"
        
        trend_emoji = "📈" if sentiment.get('trend') == 'up' else "📉"
        
        lines = [
            "📊 <b>市场情绪 & 打板效果</b>\n",
            f"<b>近{sentiment.get('days_analyzed', 7)}日情绪</b>",
            f"• 日均涨停: {sentiment.get('avg_limit_ups', 0):.0f} 只",
            f"• 平均高度: {sentiment.get('avg_max_streak', 0):.1f} 板",
            f"• 最新高度: {sentiment.get('latest_max_streak', 0)} 板",
            f"• 二板晋级率: {sentiment.get('promotion_2b_avg', 0):.1f}%",
            f"• 趋势: {trend_emoji} {sentiment.get('trend', 'unknown')}",
        ]
        
        if perf and perf.get('total_tracked', 0) > 0:
            lines.extend([
                f"\n<b>推荐效果 (近{perf.get('total_tracked', 0)}笔)</b>",
                f"• 开盘正收益: {perf.get('open_positive_rate', 0):.1f}%",
                f"• 盘中涨5%+: {perf.get('high_over_5pct_rate', 0):.1f}%",
                f"• 收盘正收益: {perf.get('close_positive_rate', 0):.1f}%",
                f"• 连板成功: {perf.get('limit_continue_rate', 0):.1f}%",
                f"• 平均开盘: {perf.get('avg_next_open_pct', 0):+.2f}%",
                f"• 平均最高: {perf.get('avg_next_high_pct', 0):+.2f}%",
            ])
        
        return "\n".join(lines)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Phase 3: Intraday Real-Time Signal Detection
    # ═══════════════════════════════════════════════════════════════════════════
    
    def set_notify_callback(self, callback):
        """Set callback for sending signal notifications."""
        self._notify_callback = callback
    
    async def _notify(self, message: str):
        """Send notification."""
        logger.info(f"[SIGNAL] {message}")
        
        # Send to Telegram Target Channel
        try:
            if settings.REPORT_TARGET_CHANNEL:
                from app.core.bot import telegram_service
                await telegram_service.send_message(
                    settings.REPORT_TARGET_CHANNEL, 
                    message, 
                    parse_mode="HTML"
                )
        except Exception as e:
            logger.error(f"Failed to send signal to Telegram: {e}")

        if self._notify_callback:
            try:
                await self._notify_callback(message)
            except Exception as e:
                logger.error(f"Signal notification failed: {e}")
    
    def _is_market_hours(self) -> bool:
        """Check if currently in A-share market hours."""
        now = china_now()
        if now.weekday() >= 5:  # Weekend
            return False
        
        hour, minute = now.hour, now.minute
        time_mins = hour * 60 + minute
        
        # 09:30-11:30 (570-690) or 13:00-15:00 (780-900)
        return (570 <= time_mins <= 690) or (780 <= time_mins <= 900)
    
    async def _poll_limit_up_pool(self) -> Dict:
        """Fetch current limit-up pool and return state."""
        ak = self._get_akshare()
        if not ak:
            return {}
        
        today = china_today()
        date_str = today.strftime("%Y%m%d")
        
        try:
            df = await asyncio.to_thread(ak.stock_zt_pool_em, date=date_str)
            
            if df is None or df.empty:
                return {}
            
            current_state = {}
            for _, row in df.iterrows():
                code = str(row.get('代码', ''))
                name = str(row.get('名称', ''))
                
                # Skip ST
                if 'ST' in name:
                    continue
                
                seal_amount = float(row.get('封单额', 0) or 0)
                first_limit_time = str(row.get('首次涨停时间', '') or '')
                limit_times = int(row.get('连板数', 1) or 1)
                turnover_rate = float(row.get('换手率', 0) or 0)
                
                current_state[code] = {
                    'name': name,
                    'seal': seal_amount,
                    'limit_since': first_limit_time,
                    'limit_times': limit_times,
                    'turnover': turnover_rate,
                }
            
            return current_state
            
        except Exception as e:
            logger.warn(f"Failed to poll limit-up pool: {e}")
            return {}
    
    async def _detect_signals(self, current_state: Dict):
        """Compare current state with previous and detect signals."""
        signals = []
        now_str = china_now().strftime("%H:%M:%S")
        prev_codes = set(self._intraday_state.keys())
        curr_codes = set(current_state.keys())
        
        # 🔥 新上板 - New limit-ups
        new_limits = curr_codes - prev_codes
        for code in new_limits:
            info = current_state[code]
            signals.append({
                'type': 'new_limit',
                'emoji': '🔥',
                'code': code,
                'name': info['name'],
                'time': now_str,
                'msg': f"新上板 {info['limit_times']}板 换手{info['turnover']:.1f}%",
            })
            # Initialize tracking
            self._intraday_state[code] = {
                'seal': info['seal'],
                'prev_seal': info['seal'],
                'limit_since': info['limit_since'],
                'burst_count': 0,
                'reseal_count': 0,
                'name': info['name'],
                'limit_times': info['limit_times'],
            }
        
        # ⚠️ 炸板 - Limit breaks (was in pool, now not)
        burst = prev_codes - curr_codes
        for code in burst:
            if code in self._intraday_state:
                info = self._intraday_state[code]
                info['burst_count'] = info.get('burst_count', 0) + 1
                signals.append({
                    'type': 'burst',
                    'emoji': '⚠️',
                    'code': code,
                    'name': info.get('name', ''),
                    'time': now_str,
                    'msg': f"炸板! 第{info['burst_count']}次",
                })
        
        # Check existing stocks for seal changes
        for code in curr_codes & prev_codes:
            curr_info = current_state[code]
            prev_info = self._intraday_state.get(code, {})
            
            curr_seal = curr_info['seal']
            prev_seal = prev_info.get('seal', curr_seal)
            
            if prev_seal > 0:
                change_pct = (curr_seal - prev_seal) / prev_seal * 100
                
                # 📉 撤单 - Seal drops >30%
                if change_pct <= -30:
                    signals.append({
                        'type': 'seal_drop',
                        'emoji': '📉',
                        'code': code,
                        'name': curr_info['name'],
                        'time': now_str,
                        'msg': f"封单骤降 {change_pct:.0f}%",
                    })
                
                # 💪 加封 - Seal increases >50%
                elif change_pct >= 50:
                    signals.append({
                        'type': 'seal_add',
                        'emoji': '💪',
                        'code': code,
                        'name': curr_info['name'],
                        'time': now_str,
                        'msg': f"封单增加 +{change_pct:.0f}%",
                    })
            
            # Update state
            self._intraday_state[code] = {
                'seal': curr_seal,
                'prev_seal': prev_seal,
                'limit_since': curr_info['limit_since'],
                'burst_count': prev_info.get('burst_count', 0),
                'reseal_count': prev_info.get('reseal_count', 0),
                'name': curr_info['name'],
                'limit_times': curr_info['limit_times'],
            }
        
        # 🔄 回封 - Stocks that were burst but came back
        for code in curr_codes:
            if code in self._intraday_state:
                info = self._intraday_state[code]
                if info.get('burst_count', 0) > 0 and code not in burst:
                    # Check if this is a reseal (was marked as burst, now back)
                    if code not in prev_codes:
                        info['reseal_count'] = info.get('reseal_count', 0) + 1
                        signals.append({
                            'type': 'reseal',
                            'emoji': '🔄',
                            'code': code,
                            'name': info.get('name', ''),
                            'time': now_str,
                            'msg': f"回封成功! 第{info['reseal_count']}次",
                        })
        
        return signals
    
    async def _send_signal_alerts(self, signals: List[Dict]):
        """Send alerts for detected signals."""
        if not signals:
            return
        
        # Add to history (keep last 50)
        self._signal_history.extend(signals)
        self._signal_history = self._signal_history[-50:]
        
        # Group alerts
        alert_lines = []
        for sig in signals:
            alert_lines.append(
                f"{sig['emoji']} <b>{sig['name']}</b> ({sig['code']})\n"
                f"   {sig['msg']} @ {sig['time']}"
            )
        
        if alert_lines:
            now = china_now()
            message = (
                f"🎯 <b>打板实时信号</b>\n"
                f"<i>{now.strftime('%H:%M:%S')}</i>\n\n" +
                "\n".join(alert_lines)
            )
            await self._notify(message)
    
    async def _intraday_loop(self):
        """Intraday polling loop - runs every 60 seconds during market hours."""
        logger.info("Starting intraday monitoring loop")
        
        while self.is_running:
            try:
                if self._is_market_hours():
                    # Poll and detect signals
                    current_state = await self._poll_limit_up_pool()
                    
                    if current_state:
                        signals = await self._detect_signals(current_state)
                        if signals:
                            await self._send_signal_alerts(signals)
                    
                    await asyncio.sleep(60)  # Poll every 60 seconds
                else:
                    # Outside market hours - check less frequently
                    # Clear state at market open
                    now = china_now()
                    if now.hour == 9 and now.minute == 25:
                        self._intraday_state.clear()
                        self._signal_history.clear()
                        logger.info("Cleared intraday state for new trading day")
                    
                    await asyncio.sleep(60)
                    
            except Exception as e:
                logger.error(f"Intraday loop error: {e}")
                await asyncio.sleep(30)
    
    def get_live_status(self) -> Dict:
        """Get current live limit-up status."""
        return {
            'stocks': list(self._intraday_state.values()),
            'count': len(self._intraday_state),
            'is_market_hours': self._is_market_hours(),
        }
    
    def get_signal_history(self, limit: int = 20) -> List[Dict]:
        """Get recent signal history."""
        return self._signal_history[-limit:]
    
    async def generate_live_report(self) -> str:
        """Generate live limit-up status report."""
        status = self.get_live_status()
        
        if not status['is_market_hours']:
            return "📊 <b>打板实时监控</b>\n\n非交易时段，暂无数据"
        
        if not status['stocks']:
            return "📊 <b>打板实时监控</b>\n\n当前无涨停股票"
        
        now = china_now()
        lines = [
            "📊 <b>打板实时监控</b>",
            f"<i>{now.strftime('%H:%M:%S')}</i>",
            f"涨停 {status['count']} 只\n",
        ]
        
        # Sort by seal amount
        stocks = sorted(status['stocks'], key=lambda x: x.get('seal', 0), reverse=True)
        
        for s in stocks[:15]:  # Top 15
            seal_yi = s.get('seal', 0) / 100000000
            burst = s.get('burst_count', 0)
            reseal = s.get('reseal_count', 0)
            
            flags = ""
            if burst > 0:
                flags += f" ⚠️炸{burst}"
            if reseal > 0:
                flags += f" 🔄封{reseal}"
            
            lines.append(
                f"• <b>{s.get('name', '')}</b> {s.get('limit_times', 1)}板 "
                f"封{seal_yi:.1f}亿{flags}"
            )
        
        return "\n".join(lines)
    
    async def generate_signals_report(self) -> str:
        """Generate recent signals report."""
        signals = self.get_signal_history(20)
        
        if not signals:
            return "🔔 <b>打板信号记录</b>\n\n暂无信号"
        
        now = china_now()
        lines = [
            "🔔 <b>打板信号记录</b>",
            f"<i>{now.strftime('%H:%M:%S')}</i>\n",
        ]
        
        # Reverse to show most recent first
        for sig in reversed(signals[-15:]):
            lines.append(
                f"{sig['emoji']} {sig['time']} <b>{sig['name']}</b> - {sig['msg']}"
            )
        
        return "\n".join(lines)


# Singleton
daban_service = DabanService()


