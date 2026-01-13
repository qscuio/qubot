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
    """打板 盘后复盘服务 (Post-Close Review)."""
    
    def __init__(self):
        self.is_running = False
        self._scheduler_task = None
        self._ak = None
        self._last_date = None  # For date change detection
        self._triggered_today = set()
        
        # Stats for observability
        self._stats = defaultdict(int)
    
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
        self.is_running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("✅ 打板 盘后复盘服务 started")
    
    async def stop(self):
        """Stop the service."""
        self.is_running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
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
        Background scheduler for 打板 reports.
        
        Fixes:
        - Uses time window instead of exact match
        - Uses date change for clearing triggered set
        """
        # Report at 15:05 (after market close)
        report_hour = 15
        report_minute = 5
        
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
                
                # Check if within report window (within 1 minute of target time)
                key = f"{current_date}_daban_report"
                if key not in self._triggered_today:
                    target_time = now.replace(hour=report_hour, minute=report_minute, second=0, microsecond=0)
                    time_diff = abs((now - target_time).total_seconds())
                    
                    if time_diff < 60:  # Within 1 minute window
                        self._triggered_today.add(key)
                        logger.info("Triggering 打板复盘 report")
                        await self.send_daban_report()
                
            except Exception as e:
                logger.error(f"打板 scheduler error: {e}")
            
            await asyncio.sleep(30)


# Singleton
daban_service = DabanService()
