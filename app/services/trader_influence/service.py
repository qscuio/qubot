"""
Trader Influence Service - Main Orchestrator

Orchestrates the full 6-module pipeline:
1. Preprocess messages (annotate features)
2. Detect market events
3. Score member influence
4. Extract opinions (LLM, Top N only)
5. Build member profiles
6. Generate group insights

Supports incremental updates via last_processed_id tracking.
"""

import time
import json
from datetime import datetime
from typing import List, Dict, Optional, Any

from app.core.logger import Logger
from app.core.database import db
from app.services.trader_influence.data_models import (
    AnnotatedMessage,
    MarketEvent,
    MemberInfluence,
    MemberProfile,
    GroupInsights,
    InfluenceAnalysisResult,
    InfluenceWeights,
)
from app.services.trader_influence.preprocessor import Preprocessor, preprocessor
from app.services.trader_influence.market_events import MarketEventDetector, market_event_detector
from app.services.trader_influence.influence_scorer import InfluenceScorer, influence_scorer
from app.services.trader_influence.opinion_extractor import OpinionExtractor, opinion_extractor
from app.services.trader_influence.profile_builder import ProfileBuilder, profile_builder
from app.services.trader_influence.group_insights import GroupInsightsAnalyzer, group_insights_analyzer

logger = Logger("TraderInfluenceService")


# ═══════════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════════

# Default top N members for LLM analysis
DEFAULT_TOP_N = 10


# ═══════════════════════════════════════════════════════════════════════════════
# Database Operations
# ═══════════════════════════════════════════════════════════════════════════════

async def ensure_tables():
    """Create trader influence tables if they don't exist."""
    if not db.pool:
        return
    
    async with db.pool.acquire() as conn:
        # Annotated messages
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS trader_messages (
                id SERIAL PRIMARY KEY,
                message_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                user_name TEXT,
                timestamp TIMESTAMP,
                text TEXT,
                reply_to TEXT,
                features JSONB,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(channel_id, message_id)
            );
        """)
        
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_trader_messages_channel 
            ON trader_messages(channel_id);
        """)
        
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_trader_messages_user 
            ON trader_messages(channel_id, user_id);
        """)
        
        # Member influence scores
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS member_influence (
                id SERIAL PRIMARY KEY,
                channel_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                user_name TEXT,
                influence_score DECIMAL,
                score_breakdown JSONB,
                rank INT,
                top_messages JSONB,
                total_messages INT,
                forward_looking_ratio DECIMAL,
                calculated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(channel_id, user_id)
            );
        """)
        
        # Member profiles
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS member_profiles (
                id SERIAL PRIMARY KEY,
                channel_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                user_name TEXT,
                profile JSONB NOT NULL,
                views JSONB,
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(channel_id, user_id)
            );
        """)
        
        # Group insights
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS group_insights (
                id SERIAL PRIMARY KEY,
                channel_id TEXT UNIQUE NOT NULL,
                channel_name TEXT,
                insights JSONB NOT NULL,
                calculated_at TIMESTAMP DEFAULT NOW()
            );
        """)
        
        logger.info("📦 Trader influence tables initialized")


async def save_influence(channel_id: str, members: List[MemberInfluence]):
    """Save member influence scores to database."""
    if not db.pool or not members:
        return
    
    try:
        for member in members:
            await db.pool.execute("""
                INSERT INTO member_influence 
                (channel_id, user_id, user_name, influence_score, score_breakdown, 
                 rank, top_messages, total_messages, forward_looking_ratio, calculated_at)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7::jsonb, $8, $9, NOW())
                ON CONFLICT (channel_id, user_id) 
                DO UPDATE SET 
                    influence_score = $4,
                    score_breakdown = $5::jsonb,
                    rank = $6,
                    top_messages = $7::jsonb,
                    total_messages = $8,
                    forward_looking_ratio = $9,
                    calculated_at = NOW()
            """, 
            channel_id, 
            member.user_id, 
            member.user_name,
            member.influence_score,
            json.dumps(member.breakdown.to_dict()),
            member.rank,
            json.dumps(member.top_messages),
            member.total_messages,
            member.forward_looking_ratio,
            )
    except Exception as e:
        logger.error(f"Failed to save influence: {e}")


async def save_profiles(channel_id: str, profiles: List[MemberProfile]):
    """Save member profiles to database."""
    if not db.pool or not profiles:
        return
    
    try:
        for profile in profiles:
            await db.pool.execute("""
                INSERT INTO member_profiles 
                (channel_id, user_id, user_name, profile, views, updated_at)
                VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, NOW())
                ON CONFLICT (channel_id, user_id) 
                DO UPDATE SET 
                    profile = $4::jsonb,
                    views = $5::jsonb,
                    updated_at = NOW()
            """,
            channel_id,
            profile.user_id,
            profile.user_name,
            json.dumps(profile.to_dict()),
            json.dumps([v.to_dict() for v in profile.validated_views + profile.pending_views]),
            )
    except Exception as e:
        logger.error(f"Failed to save profiles: {e}")


async def save_insights(channel_id: str, insights: GroupInsights):
    """Save group insights to database."""
    if not db.pool:
        return
    
    try:
        await db.pool.execute("""
            INSERT INTO group_insights 
            (channel_id, channel_name, insights, calculated_at)
            VALUES ($1, $2, $3::jsonb, NOW())
            ON CONFLICT (channel_id) 
            DO UPDATE SET 
                insights = $3::jsonb,
                calculated_at = NOW()
        """,
        channel_id,
        insights.channel_name,
        json.dumps(insights.to_dict()),
        )
    except Exception as e:
        logger.error(f"Failed to save insights: {e}")


async def load_influence(channel_id: str) -> List[MemberInfluence]:
    """Load member influence scores from database."""
    if not db.pool:
        return []
    
    try:
        rows = await db.pool.fetch("""
            SELECT * FROM member_influence 
            WHERE channel_id = $1 
            ORDER BY rank ASC
        """, channel_id)
        
        return [
            MemberInfluence.from_dict({
                "user_id": r["user_id"],
                "user_name": r["user_name"],
                "influence_score": float(r["influence_score"]) if r["influence_score"] else 0,
                "rank": r["rank"],
                "breakdown": r["score_breakdown"] if isinstance(r["score_breakdown"], dict) else {},
                "top_messages": r["top_messages"] if isinstance(r["top_messages"], list) else [],
                "total_messages": r["total_messages"] or 0,
                "forward_looking_ratio": float(r["forward_looking_ratio"]) if r["forward_looking_ratio"] else 0,
            })
            for r in rows
        ]
    except Exception as e:
        logger.error(f"Failed to load influence: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════════════════
# Report Rendering
# ═══════════════════════════════════════════════════════════════════════════════

def render_report(result: InfluenceAnalysisResult) -> str:
    """Render analysis result as readable report."""
    lines = [
        f"# 📊 {result.channel_name} 成员影响力分析",
        f"> 分析 {result.messages_processed} 条消息 | 识别 {result.events_detected} 个市场事件",
        "",
    ]
    
    # Top members
    if result.top_members:
        lines.append("## 🏆 影响力排名")
        for member in result.top_members[:5]:
            b = member.breakdown
            lines.append(
                f"**#{member.rank} {member.user_name}** "
                f"(得分: {member.influence_score:.1f})"
            )
            lines.append(
                f"  - 前瞻判断: {b.forward_looking_count} | "
                f"被引用: {b.citation_count} | "
                f"引发行动: {b.behavior_change_count}"
            )
        lines.append("")
    
    # Profiles
    if result.profiles:
        lines.append("## 👤 成员画像")
        for profile in result.profiles[:5]:
            lines.append(
                f"**{profile.user_name}** - "
                f"`{profile.role_type.value}` / `{profile.trading_style.value}`"
            )
            if profile.core_bias:
                lines.append(f"  > {profile.core_bias}")
            lines.append(f"  - 观点验证率: {profile.accuracy_rate:.0%}")
        lines.append("")
    
    # Group insights
    if result.insights:
        ins = result.insights
        lines.append("## 📈 群体洞察")
        lines.append(f"- 意见领袖: {len(ins.opinion_anchors)} 人")
        lines.append(f"- 情绪放大者: {len(ins.emotion_amplifiers)} 人")
        lines.append(f"- 多元性评分: {ins.echo_chamber_score:.0%}")
        lines.append(f"- 易被带节奏: {ins.group_susceptibility:.0%}")
        
        if ins.over_reliance_warning:
            lines.append(f"\n⚠️ **警告**: 群体过度依赖少数成员")
        
        if ins.summary:
            lines.append(f"\n> {ins.summary}")
        lines.append("")
    
    # Footer
    lines.append("---")
    lines.append(
        f"*处理时间: {result.processing_time_ms:.0f}ms | "
        f"LLM调用: {result.llm_calls}次*"
    )
    
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# Main Service
# ═══════════════════════════════════════════════════════════════════════════════

class TraderInfluenceService:
    """
    Main orchestrator for trader influence analysis.
    
    Pipeline:
    1. Preprocess → 2. Events → 3. Score → 4. Extract → 5. Profile → 6. Insights
    
    Modules 1-3 are non-LLM (rule-based).
    Modules 4-6 use LLM selectively (Top N members only).
    """
    
    def __init__(self):
        self.preprocessor = preprocessor
        self.event_detector = market_event_detector
        self.scorer = influence_scorer
        self.extractor = opinion_extractor
        self.profile_builder = profile_builder
        self.insights_analyzer = group_insights_analyzer
        self._initialized = False
    
    async def initialize(self):
        """Initialize database tables."""
        if not self._initialized:
            await ensure_tables()
            self._initialized = True
    
    async def analyze(
        self,
        channel_id: str,
        channel_name: str,
        messages: List[Dict[str, Any]],
        top_n: int = DEFAULT_TOP_N,
        weights: InfluenceWeights = None,
        skip_llm: bool = False,
    ) -> InfluenceAnalysisResult:
        """
        Run full influence analysis pipeline.
        
        Args:
            channel_id: Channel identifier
            channel_name: Channel display name
            messages: Raw messages (message_id, user_id, text, timestamp, etc.)
            top_n: Number of top members for LLM analysis
            weights: Custom influence weights
            skip_llm: If True, skip LLM calls (faster, less detail)
            
        Returns:
            InfluenceAnalysisResult with all analysis
        """
        start_time = time.time()
        await self.initialize()
        
        if not messages:
            logger.info(f"No messages to analyze for {channel_name}")
            return InfluenceAnalysisResult(
                channel_id=channel_id,
                channel_name=channel_name,
            )
        
        logger.info(f"📊 Analyzing {len(messages)} messages for {channel_name}")
        
        # Configure scorer
        if weights:
            self.scorer.weights = weights
        
        # ─────────────────────────────────────────────────────────────────
        # Module 1: Preprocess messages
        # ─────────────────────────────────────────────────────────────────
        annotated = self.preprocessor.process(messages)
        
        # ─────────────────────────────────────────────────────────────────
        # Module 2: Detect market events
        # ─────────────────────────────────────────────────────────────────
        events = self.event_detector.detect(annotated)
        
        # ─────────────────────────────────────────────────────────────────
        # Module 3: Score all members, get Top N
        # ─────────────────────────────────────────────────────────────────
        top_members = self.scorer.score_all_members(annotated, events, top_n=top_n)
        
        # Save influence scores
        await save_influence(channel_id, top_members)
        
        # ─────────────────────────────────────────────────────────────────
        # Module 4-6: LLM-based analysis (only if not skipped)
        # ─────────────────────────────────────────────────────────────────
        profiles = []
        insights = None
        llm_calls = 0
        
        if not skip_llm and top_members:
            # Module 4: Extract opinions
            views_by_user = await self.extractor.extract_for_members(top_members, annotated)
            llm_calls += self.extractor.llm_calls
            
            # Module 5: Build profiles
            profiles = await self.profile_builder.build_profiles(top_members, views_by_user)
            llm_calls += self.profile_builder.llm_calls
            
            # Save profiles
            await save_profiles(channel_id, profiles)
            
            # Module 6: Group insights
            insights = await self.insights_analyzer.analyze_with_summary(
                channel_id, channel_name, top_members, profiles
            )
            llm_calls += self.insights_analyzer.llm_calls
            
            # Save insights
            await save_insights(channel_id, insights)
        else:
            # Rule-based insights only
            insights = self.insights_analyzer.analyze(
                channel_id, channel_name, top_members, profiles
            )
        
        # Build result
        processing_time = (time.time() - start_time) * 1000
        
        result = InfluenceAnalysisResult(
            channel_id=channel_id,
            channel_name=channel_name,
            messages_processed=len(messages),
            events_detected=len(events),
            top_members=top_members,
            profiles=profiles,
            insights=insights,
            processing_time_ms=processing_time,
            llm_calls=llm_calls,
        )
        
        logger.info(
            f"✅ Analysis complete for {channel_name}: "
            f"{len(top_members)} top members, "
            f"{len(profiles)} profiles, "
            f"time={processing_time:.0f}ms"
        )
        
        return result
    
    async def get_influence_ranking(
        self,
        channel_id: str,
    ) -> List[MemberInfluence]:
        """Get cached influence ranking for a channel."""
        await self.initialize()
        return await load_influence(channel_id)
    
    def render_report(self, result: InfluenceAnalysisResult) -> str:
        """Render analysis result as readable report."""
        return render_report(result)


# ═══════════════════════════════════════════════════════════════════════════════
# Singleton Instance
# ═══════════════════════════════════════════════════════════════════════════════

trader_influence_service = TraderInfluenceService()
