"""
A股市场AI分析服务 (A-Share Market AI Analysis Service)

Using ported Core Algorithms from daily_stock_analysis:
- MarketAnalyzerLogic: For indices and sector overview.
- StockTrendAnalyzer: For deep dive technical analysis on top stocks.

Features:
- Robust data fetching with retry.
- Deterministic technical analysis (MA, Bias, Trend).
- Professional AI reporting.
"""

import asyncio
import logging
import random
import time
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional

import pandas as pd
import akshare as ak

from app.core.config import settings
from app.core.bot import telegram_service
from app.core.timezone import china_now, china_today
from app.services.ai import ai_service
from app.services.stock_trend_analyzer import StockTrendAnalyzer, TrendAnalysisResult
from app.services.market_analyzer import MarketAnalyzerLogic, MarketOverview

logger = logging.getLogger(__name__)


class MarketAIAnalysisService:
    """Market AI Analysis Service with Robust Fetching & Core Algorithms"""
    
    def __init__(self):
        self.is_running = False
        self._scheduler_task = None
        self._triggered_today = set()
        
        # Analyzers
        self.trend_analyzer = StockTrendAnalyzer()
        self.market_analyzer = MarketAnalyzerLogic()
        
    async def start(self):
        """Start the service"""
        if self.is_running:
            return
            
        report_target = settings.REPORT_TARGET_GROUP or settings.REPORT_TARGET_CHANNEL
        if not report_target:
            logger.warning("REPORT_TARGET_GROUP/CHANNEL not configured, analysis service disabled")
            return
            
        self.is_running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("✅ Market AI Analysis Service started (with Core Algorithms)")

    async def stop(self):
        """Stop the service"""
        self.is_running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        logger.info("Market AI Analysis Service stopped")

    # ─────────────────────────────────────────────────────────────────────────
    # Data Fetching (Robust)
    # ─────────────────────────────────────────────────────────────────────────

    async def _fetch_with_retry(self, func, *args, retries=3, delay=2, **kwargs):
        """Execute akshare function with retry logic"""
        for i in range(retries):
            try:
                # Run in thread pool to avoid blocking async loop
                return await asyncio.to_thread(func, *args, **kwargs)
            except Exception as e:
                if i == retries - 1:
                    logger.error(f"Fetch failed after {retries} attempts: {e}")
                    return None
                logger.warning(f"Fetch attempt {i+1} failed: {e}, retrying...")
                await asyncio.sleep(delay * (i + 1))
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # Market Overview
    # ─────────────────────────────────────────────────────────────────────────

    async def get_market_overview_data(self) -> Optional[MarketOverview]:
        """Fetch and aggregate market overview data"""
        try:
            # 1. Major Indices (Keep online fetch as per plan - not in DB)
            indices_df = await self._fetch_with_retry(ak.stock_zh_index_spot_sina)
            
            # 2. Sectors (Keep online fetch as per plan - not in DB)
            sector_df = await self._fetch_with_retry(ak.stock_board_industry_name_em)
            
            # 3. Market Stats (Use Local DB)
            today = china_today()
            from app.services.stock_history import stock_history_service
            market_stats = await stock_history_service.get_daily_market_stats(today)
            
            # Create partial market_df for MarketAnalyzer if stats available
            # MarketAnalyzer expects a generic structure. We might need to adjust it 
            # or manually create the MarketOverview object.
            # Let's bypass MarketAnalyzer.process_market_data partially/completely or mock the DF?
            # Actually, constructing a partial DataFrame from stats is hard because process_market_data calculates counts itself.
            # Best approach: Use MarketAnalyzer for Indices/Sectors, but inject our DB stats.
            
            # Let's see MarketAnalyzerLogic.process_market_data signature...
            # It takes (indices_df, market_df, sector_df).
            # If we pass None for market_df, it returns None?
            # We should probably modify process_market_data to accept pre-calculated stats 
            # OR manually build MarketOverview here. Manually building is safer/cleaner here.
            
            # Helper to parse indices
            indices = []
            if indices_df is not None and not indices_df.empty:
                # Same logic as MarketAnalyzer
                main_indices = ['上证指数', '深证成指', '创业板指', '科创50']
                for _, row in indices_df.iterrows():
                    name = row['名称']
                    if name in main_indices:
                        indices.append(type('obj', (object,), {
                            'name': name,
                            'change_pct': float(row['涨跌幅'])
                        }))

            # Helper to parse sectors
            top_sectors = []
            bottom_sectors = []
            if sector_df is not None and not sector_df.empty:
                sector_df['涨跌幅'] = pd.to_numeric(sector_df['涨跌幅'], errors='coerce')
                df_sorted = sector_df.sort_values('涨跌幅', ascending=False)
                for _, row in df_sorted.head(5).iterrows():
                    top_sectors.append({'name': row['板块名称'], 'change': row['涨跌幅']})
                for _, row in df_sorted.tail(5).iterrows():
                    bottom_sectors.append({'name': row['板块名称'], 'change': row['涨跌幅']})
            
            if not market_stats:
                # If DB has no data for today (yet), maybe try fallback?
                # User asked to replace online fetch. We return None if not ready.
                return None
                
            return MarketOverview(
                indices=indices,
                top_sectors=top_sectors,
                bottom_sectors=bottom_sectors,
                up_count=market_stats['up_count'],
                down_count=market_stats['down_count'],
                flat_count=market_stats['flat_count'],
                total_amount=market_stats['total_turnover'] / 100000000, # Convert to Hundred Millions
                total_volume=market_stats['total_volume']
            )
            
        except Exception as e:
            logger.error(f"Failed to get market overview: {e}")
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # Deep Dive Analysis (Top Stock)
    # ─────────────────────────────────────────────────────────────────────────

    async def analyze_stock_deep_dive(self, code: str, name: str) -> Optional[TrendAnalysisResult]:
        """Perform deep technical analysis on a single stock using Local DB"""
        try:
            from app.services.stock_history import stock_history_service
            df = await stock_history_service.get_stock_df(code, days=200)
            
            if df is None or df.empty:
                return None
            
            return self.trend_analyzer.analyze(df, code)
            
        except Exception as e:
            logger.error(f"Deep dive failed for {code}: {e}")
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # Report Generation
    # ─────────────────────────────────────────────────────────────────────────

    async def generate_daily_report(self, progress_callback=None) -> str:
        """
        Generate the comprehensive AI report
        
        Args:
            progress_callback: Optional async function(current, total, message) used to report progress
        """
        async def _report(current, total, msg):
            if progress_callback:
                try:
                    await progress_callback(current, total, msg)
                except Exception:
                    pass

        # 1. Get Market Overview (now uses DB for stats)
        await _report(10, 100, "正在采集市场概况数据 (Local DB + API)...")
        overview = await self.get_market_overview_data()
        if not overview:
            # Check reasons? Maybe DB not updated?
            return "❌ 无法获取今日市场数据。可能本地数据库尚未同步，请稍后再试 (15:30后数据同步完成)。"
            
        overview_text = self.market_analyzer.format_market_overview(overview)
        
        # 2. Identify Top Stock (from DB)
        await _report(30, 100, "正在筛选今日关注星标股...")
        top_stock = None
        trend_result = None
        
        try:
            from app.services.stock_history import stock_history_service
            today = china_today()
            top_gainers = await stock_history_service.get_top_gainers_db(today, limit=5)
            
            if top_gainers:
                row = top_gainers[0]
                code = row['code']
                name = row['name'] or code
                change = row['change_pct']
                
                await _report(50, 100, f"正在对 {name}({code}) 进行深度技术复盘...")
                trend_result = await self.analyze_stock_deep_dive(code, name)
                if trend_result:
                    top_stock = {'code': code, 'name': name, 'change': change}
        except Exception as e:
            logger.error(f"Failed to get top stock from DB: {e}")

        # 3. Build AI Prompt
        prompt = self._build_ai_prompt(overview, top_stock, trend_result)
        
        # 4. Generate AI Content
        await _report(70, 100, "AI正在深度思考与撰写报告 (约需15秒)...")
        try:
            result = await ai_service.analyze(prompt)
            ai_content = result.get("content", "⚠️ AI未返回有效内容")
        except Exception as e:
            ai_content = f"⚠️ AI分析暂时不可用 ({e})\n\n请参考上方客观数据。"
            
        await _report(100, 100, "报告生成完成")

        # 5. Assemble Final Report
        report = [
            overview_text,
            "━━━━━━━━━━━━━━━━━━━━━",
            "🤖 <b>AI 深度复盘</b>",
            "",
            ai_content
        ]
        
        return "\n".join(report)

    def _build_ai_prompt(self, overview: MarketOverview, top_stock: dict, trend: Optional[TrendAnalysisResult]) -> str:
        """Build the System Prompt for AI (Ported from daily_stock_analysis)"""
        
        # Indices Stats
        indices_str = ", ".join([f"{i.name}{i.change_pct:+.2f}%" for i in overview.indices])
        
        # Sectors
        sectors_up = ", ".join([f"{s['name']}" for s in overview.top_sectors[:3]])
        sectors_down = ", ".join([f"{s['name']}" for s in overview.bottom_sectors[:3]])
        
        # Deep Dive Data
        deep_dive_text = "暂无具体个股深度分析数据"
        if trend:
            deep_dive_text = f"""
【今日关注星标股】：{top_stock['name']} ({top_stock['code']})
- 涨跌幅：{top_stock['change']}%
- 趋势状态：{trend.trend_status.value} (强度 {trend.trend_strength})
- 均线形态：{trend.ma_alignment}
- MA5乖离率：{trend.bias_ma5:.2f}% ({'⚠️偏高' if trend.bias_ma5 > 5 else '✅安全'})
- 量能状态：{trend.volume_status.value}
- 系统评分：{trend.signal_score}分 ({trend.buy_signal.value})
- 信号理由：{', '.join(trend.signal_reasons)}
- 风险提示：{', '.join(trend.risk_factors)}
"""

        prompt = f"""你是一位专注于趋势交易的 A 股投资分析师。请根据以下客观数据，生成一份专业的【决策仪表盘】风格的市场复盘报告。

## 核心交易理念（必须严格遵守）

### 1. 严进策略（不追高）
- **绝对不追高**：当股价偏离 MA5 超过 5% 时，坚决不买入
- **乖离率公式**：(现价 - MA5) / MA5 × 100%
- 乖离率 < 2%：最佳买点区间
- 乖离率 2-5%：可小仓介入
- 乖离率 > 5%：严禁追高！直接判定为"观望"

### 2. 趋势交易（顺势而为）
- **多头排列必须条件**：MA5 > MA10 > MA20
- 只做多头排列的股票，空头排列坚决不碰
- 均线发散上行优于均线粘合
- 趋势强度判断：看均线间距是否在扩大

### 3. 效率优先（筹码结构）
- 关注筹码集中度与获利比例
- 缩量回调是洗盘，放量下跌要注意风险

### 4. 风险排查重点
- 关注减持公告、业绩预亏、监管处罚等重大利空
- 跌破 MA20 时需谨慎观望

---

## 今日市场数据
- 指数表现：{indices_str}
- 涨跌家数：涨{overview.up_count}/跌{overview.down_count}
- 成交金额：{overview.total_amount:.0f}亿
- 领涨板块：{sectors_up}
- 领跌板块：{sectors_down}

{deep_dive_text}

---

## 任务要求
请基于以上数据和**核心交易理念**，生成一份简练、犀利的文本报告（直接输出报告内容，无需Markdown标题）：

1. **市场定调**：用一句话概括今日行情（如"放量普涨"、"缩量分化"、"情绪修复"等），并点评市场赚钱效应。
2. **热点复盘**：简析领涨板块的驱动逻辑，指出是游资炒作还是机构抱团。
3. **操作建议**：这是一份给用户的实操指南。
   - 仓位建议（空仓/半仓/满仓）。
   - 具体方向（是进攻热门，还是防守低吸）。
4. **星标股深评**（如果有）：
   - 严格根据【核心交易理念】点评该股。
   - 重点检查：乖离率是否过高？是否多头排列？量能是否健康？
   - **必须给出明确结论**：是"机会"还是"风险"？

**风格要求**：
- 语言风格：专业、客观、犀利，拒绝模棱两可的废话。
- 风险控制：把风险提示放在首位，特别是对于高位股。
- 字数控制：400字左右。
"""
        return prompt

    async def send_daily_analysis(self):
        """Send the analysis to the target channel"""
        report_target = settings.REPORT_TARGET_GROUP or settings.REPORT_TARGET_CHANNEL
        if not report_target:
            return

        logger.info("Generating Daily Market AI Report...")
        report = await self.generate_daily_report()
        
        await telegram_service.send_message(
            report_target,
            report,
            parse_mode="html",
            link_preview=False
        )
        logger.info("✅ Daily Report Sent.")

    # ─────────────────────────────────────────────────────────────────────────
    # Scheduler Logic
    # ─────────────────────────────────────────────────────────────────────────
    
    async def _scheduler_loop(self):
        """Daily Schedule Loop"""
        while self.is_running:
            try:
                now = china_now()
                # Schedule for 15:30 on weekdays
                if now.hour == 15 and now.minute == 30 and now.weekday() < 5:
                    date_str = now.strftime("%Y-%m-%d")
                    if date_str not in self._triggered_today:
                        self._triggered_today.add(date_str)
                        asyncio.create_task(self.send_daily_analysis())
                
                # Reset triggers at midnight
                if now.hour == 0 and now.minute == 0:
                    self._triggered_today.clear()
                    
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
            
            await asyncio.sleep(60)

market_ai_analysis_service = MarketAIAnalysisService()
