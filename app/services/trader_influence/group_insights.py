"""
Module 6: Group Insights (Optional LLM)

Analyzes group-level patterns:
- Opinion anchors (who sets direction)
- Emotion amplifiers (who escalates sentiment)
- Echo chamber detection
- Over-reliance warnings

Most analysis is rule-based; LLM used only for summary.
"""

import json
import re
from collections import Counter
from typing import List, Dict, Optional

from app.core.logger import Logger
from app.services.trader_influence.data_models import (
    MemberInfluence,
    MemberProfile,
    GroupInsights,
    DirectionType,
    RoleType,
)
from app.services.trader_influence.prompts import (
    GROUP_INSIGHTS_SYSTEM_PROMPT,
    GROUP_INSIGHTS_PROMPT,
)

logger = Logger("GroupInsights")


# ═══════════════════════════════════════════════════════════════════════════════
# Rule-based Analysis Functions
# ═══════════════════════════════════════════════════════════════════════════════

def _identify_opinion_anchors(
    profiles: List[MemberProfile],
    top_n: int = 3,
) -> List[str]:
    """
    Identify opinion anchors (members who set group direction).
    
    Anchors = high influence leaders/analysts.
    """
    anchors = [
        p.user_id for p in profiles
        if p.role_type in (RoleType.LEADER, RoleType.ANALYST)
        and p.rank <= top_n
    ]
    
    # Fallback: just use top N by score
    if not anchors and profiles:
        anchors = [p.user_id for p in sorted(profiles, key=lambda p: p.influence_score, reverse=True)[:top_n]]
    
    return anchors


def _identify_emotion_amplifiers(
    members: List[MemberInfluence],
    profiles: List[MemberProfile],
) -> List[str]:
    """
    Identify emotion amplifiers (members who escalate sentiment).
    
    Amplifiers = high emotional spam + relatively high citation.
    """
    amplifiers = []
    
    for member in members:
        # High emotional activity
        if member.breakdown.emotional_spam_count >= 2:
            # But also has some influence (others respond)
            if member.breakdown.citation_count >= 2:
                amplifiers.append(member.user_id)
    
    return amplifiers


def _calculate_echo_chamber_score(
    profiles: List[MemberProfile],
) -> float:
    """
    Calculate echo chamber score.
    
    0 = everyone has same stance (echo chamber)
    1 = diverse views (healthy debate)
    """
    if not profiles:
        return 0.5
    
    # Count stances across all views
    stance_counts = Counter()
    
    for profile in profiles:
        all_views = profile.validated_views + profile.rejected_views + profile.pending_views
        for view in all_views:
            stance_counts[view.stance] += 1
    
    total = sum(stance_counts.values())
    if total == 0:
        return 0.5
    
    # Calculate entropy-like diversity
    max_ratio = max(stance_counts.values()) / total if total > 0 else 0
    
    # If one stance dominates (>80%), low diversity
    if max_ratio > 0.8:
        return 0.2
    elif max_ratio > 0.6:
        return 0.5
    else:
        return 0.8


def _calculate_susceptibility(
    members: List[MemberInfluence],
) -> float:
    """
    Calculate group susceptibility (how easily led).
    
    High susceptibility = high behavior_change relative to forward_looking.
    """
    if not members:
        return 0.5
    
    total_forward = sum(m.breakdown.forward_looking_count for m in members)
    total_behavior_change = sum(m.breakdown.behavior_change_count for m in members)
    
    if total_forward == 0:
        return 0.5
    
    # Ratio of behavior changes to forward statements
    ratio = total_behavior_change / total_forward
    
    # Normalize to 0-1 (cap at 1)
    return min(1.0, ratio / 2)


def _check_over_reliance(
    members: List[MemberInfluence],
    threshold: float = 0.6,
) -> tuple:
    """
    Check if group over-relies on few members.
    
    Warning if top 3 account for >threshold of influence.
    """
    if len(members) < 3:
        return False, []
    
    total_score = sum(m.influence_score for m in members)
    if total_score == 0:
        return False, []
    
    top3 = sorted(members, key=lambda m: m.influence_score, reverse=True)[:3]
    top3_score = sum(m.influence_score for m in top3)
    
    ratio = top3_score / total_score
    
    if ratio > threshold:
        return True, [m.user_id for m in top3]
    
    return False, []


# ═══════════════════════════════════════════════════════════════════════════════
# Group Insights Analyzer
# ═══════════════════════════════════════════════════════════════════════════════

class GroupInsightsAnalyzer:
    """
    Analyzes group-level patterns and behaviors.
    
    Mostly rule-based; LLM used only for final summary.
    """
    
    def __init__(self):
        self._ai_service = None
        self.llm_calls = 0
    
    @property
    def ai_service(self):
        """Lazy load AI service."""
        if self._ai_service is None:
            from app.services.ai import ai_service
            self._ai_service = ai_service
        return self._ai_service
    
    def analyze(
        self,
        channel_id: str,
        channel_name: str,
        members: List[MemberInfluence],
        profiles: List[MemberProfile],
        use_llm: bool = True,
    ) -> GroupInsights:
        """
        Analyze group patterns.
        
        Args:
            channel_id: Channel identifier
            channel_name: Channel display name
            members: All scored members
            profiles: Top N member profiles
            use_llm: Whether to use LLM for summary
            
        Returns:
            GroupInsights object
        """
        # Rule-based analysis
        opinion_anchors = _identify_opinion_anchors(profiles)
        emotion_amplifiers = _identify_emotion_amplifiers(members, profiles)
        echo_score = _calculate_echo_chamber_score(profiles)
        susceptibility = _calculate_susceptibility(members)
        over_reliance, reliance_users = _check_over_reliance(members)
        
        insights = GroupInsights(
            channel_id=channel_id,
            channel_name=channel_name,
            opinion_anchors=opinion_anchors,
            emotion_amplifiers=emotion_amplifiers,
            group_susceptibility=susceptibility,
            echo_chamber_score=echo_score,
            over_reliance_warning=over_reliance,
            over_reliance_users=reliance_users,
        )
        
        logger.info(
            f"📊 Group insights for {channel_name}: "
            f"anchors={len(opinion_anchors)}, "
            f"echo={echo_score:.2f}, "
            f"susceptibility={susceptibility:.2f}"
        )
        
        return insights
    
    async def analyze_with_summary(
        self,
        channel_id: str,
        channel_name: str,
        members: List[MemberInfluence],
        profiles: List[MemberProfile],
    ) -> GroupInsights:
        """Analyze with LLM-generated summary."""
        # Get rule-based insights first
        insights = self.analyze(channel_id, channel_name, members, profiles)
        
        # Generate LLM summary
        summary = await self._generate_summary(insights, members, profiles)
        if summary:
            insights.summary = summary
        
        return insights
    
    async def _generate_summary(
        self,
        insights: GroupInsights,
        members: List[MemberInfluence],
        profiles: List[MemberProfile],
    ) -> Optional[str]:
        """Generate LLM summary of group insights."""
        try:
            # Calculate distribution stats
            total_members = len(members)
            
            if total_members == 0:
                return None
            
            total_score = sum(m.influence_score for m in members)
            top3 = sorted(members, key=lambda m: m.influence_score, reverse=True)[:3]
            top10 = sorted(members, key=lambda m: m.influence_score, reverse=True)[:10]
            
            top3_ratio = sum(m.influence_score for m in top3) / total_score if total_score > 0 else 0
            top10_ratio = sum(m.influence_score for m in top10) / total_score if total_score > 0 else 0
            
            # Count stances
            bullish = sum(1 for p in profiles if any(v.stance == DirectionType.BULLISH for v in p.validated_views + p.pending_views))
            bearish = sum(1 for p in profiles if any(v.stance == DirectionType.BEARISH for v in p.validated_views + p.pending_views))
            neutral = len(profiles) - bullish - bearish
            
            # Format influence distribution
            influence_dist = "\n".join([
                f"- {m.user_name}: {m.influence_score:.1f} (rank #{m.rank})"
                for m in top3
            ])
            
            prompt = GROUP_INSIGHTS_PROMPT.format(
                channel_name=insights.channel_name,
                influence_distribution=influence_dist,
                bullish_count=bullish,
                bearish_count=bearish,
                neutral_count=neutral,
                total_members=total_members,
                top3_ratio=top3_ratio,
                top10_ratio=top10_ratio,
            )
            
            result = await self.ai_service.quick_chat(prompt)
            self.llm_calls += 1
            
            content = result.get('content', '')
            
            # Try to extract JSON
            json_match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', content)
            if json_match:
                json_str = json_match.group(1).strip()
                try:
                    data = json.loads(json_str)
                    return data.get('summary', '')
                except:
                    pass
            
            return None
            
        except Exception as e:
            logger.warn(f"LLM summary failed: {e}")
            return None


# ═══════════════════════════════════════════════════════════════════════════════
# Singleton Instance
# ═══════════════════════════════════════════════════════════════════════════════

group_insights_analyzer = GroupInsightsAnalyzer()
