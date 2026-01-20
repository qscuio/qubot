"""
Module 5: Profile Builder (LLM + Rules)

Constructs member profiles by merging:
- Rule-based statistics (from Module 3)
- LLM-extracted views (from Module 4)
- LLM-generated summary (role type, trading style, bias)

Produces MemberProfile with validated/rejected views.
"""

import json
import re
from typing import List, Dict, Optional

from app.core.logger import Logger
from app.services.trader_influence.data_models import (
    MemberInfluence,
    ExtractedView,
    MemberProfile,
    RoleType,
    TradingStyle,
    ViewOutcome,
)
from app.services.trader_influence.prompts import (
    PROFILE_SUMMARY_SYSTEM_PROMPT,
    PROFILE_SUMMARY_PROMPT,
    format_views_summary,
)

logger = Logger("ProfileBuilder")


# ═══════════════════════════════════════════════════════════════════════════════
# JSON Parsing
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_json_from_response(response: str) -> Optional[Dict]:
    """Extract JSON from LLM response."""
    json_match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', response)
    if json_match:
        json_str = json_match.group(1).strip()
    else:
        json_str = response.strip()
    
    json_str = re.sub(r',\s*}', '}', json_str)
    json_str = re.sub(r',\s*]', ']', json_str)
    
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None


def _parse_role_type(role_str: str) -> RoleType:
    """Parse role type string to enum."""
    role_lower = role_str.lower().strip()
    role_map = {
        'leader': RoleType.LEADER,
        'analyst': RoleType.ANALYST,
        'follower': RoleType.FOLLOWER,
        'contrarian': RoleType.CONTRARIAN,
        'noise': RoleType.NOISE,
    }
    return role_map.get(role_lower, RoleType.FOLLOWER)


def _parse_trading_style(style_str: str) -> TradingStyle:
    """Parse trading style string to enum."""
    style_lower = style_str.lower().strip()
    style_map = {
        'technical': TradingStyle.TECHNICAL,
        'fundamental': TradingStyle.FUNDAMENTAL,
        'sentiment': TradingStyle.SENTIMENT,
        'mixed': TradingStyle.MIXED,
    }
    return style_map.get(style_lower, TradingStyle.MIXED)


# ═══════════════════════════════════════════════════════════════════════════════
# Rule-based Role Inference (Fallback when LLM fails)
# ═══════════════════════════════════════════════════════════════════════════════

def _infer_role_from_stats(influence: MemberInfluence) -> RoleType:
    """Infer role type from statistics (no LLM)."""
    breakdown = influence.breakdown
    
    # Leader: high citations and behavior changes
    if breakdown.citation_count >= 5 and breakdown.behavior_change_count >= 3:
        return RoleType.LEADER
    
    # Analyst: high forward-looking, low emotional
    if influence.forward_looking_ratio >= 0.3 and breakdown.emotional_spam_count == 0:
        return RoleType.ANALYST
    
    # Noise: high emotional or hindsight
    if breakdown.emotional_spam_count >= 2 or breakdown.hindsight_count > breakdown.forward_looking_count:
        return RoleType.NOISE
    
    # Default: follower
    return RoleType.FOLLOWER


# ═══════════════════════════════════════════════════════════════════════════════
# Profile Builder
# ═══════════════════════════════════════════════════════════════════════════════

class ProfileBuilder:
    """
    Builds member profiles from influence stats and extracted views.
    
    Uses LLM for:
    - Role type classification
    - Trading style analysis
    - Core bias summary
    
    Falls back to rule-based inference if LLM fails.
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
    
    async def build_profile(
        self,
        influence: MemberInfluence,
        views: List[ExtractedView],
    ) -> MemberProfile:
        """
        Build complete profile for a member.
        
        Args:
            influence: Influence stats from Module 3
            views: Extracted views from Module 4
            
        Returns:
            Complete MemberProfile
        """
        # Try LLM-based summary
        llm_result = await self._get_llm_summary(influence, views)
        
        if llm_result:
            role_type = _parse_role_type(llm_result.get('role_type', 'follower'))
            trading_style = _parse_trading_style(llm_result.get('trading_style', 'mixed'))
            core_bias = llm_result.get('core_bias', '')
            risk_triggers = llm_result.get('risk_triggers', [])
        else:
            # Fallback to rule-based
            role_type = _infer_role_from_stats(influence)
            trading_style = TradingStyle.MIXED
            core_bias = ""
            risk_triggers = []
        
        # Categorize views by outcome
        validated = [v for v in views if v.outcome == ViewOutcome.VALIDATED]
        rejected = [v for v in views if v.outcome == ViewOutcome.REJECTED]
        pending = [v for v in views if v.outcome == ViewOutcome.PENDING]
        
        profile = MemberProfile(
            user_id=influence.user_id,
            user_name=influence.user_name,
            influence_score=influence.influence_score,
            rank=influence.rank,
            role_type=role_type,
            trading_style=trading_style,
            core_bias=core_bias,
            risk_triggers=risk_triggers,
            validated_views=validated,
            rejected_views=rejected,
            pending_views=pending,
        )
        
        profile.calculate_accuracy()
        
        logger.info(
            f"👤 Built profile for {influence.user_name}: "
            f"role={role_type.value}, style={trading_style.value}"
        )
        
        return profile
    
    async def _get_llm_summary(
        self,
        influence: MemberInfluence,
        views: List[ExtractedView],
    ) -> Optional[Dict]:
        """Get LLM-generated profile summary."""
        try:
            # Format views for prompt
            views_summary = format_views_summary(views)
            
            # Build prompt
            prompt = PROFILE_SUMMARY_PROMPT.format(
                user_name=influence.user_name,
                total_messages=influence.total_messages,
                forward_looking_count=influence.breakdown.forward_looking_count,
                forward_ratio=influence.forward_looking_ratio,
                citation_count=influence.breakdown.citation_count,
                behavior_change_count=influence.breakdown.behavior_change_count,
                hindsight_count=influence.breakdown.hindsight_count,
                influence_score=influence.influence_score,
                rank=influence.rank,
                views_summary=views_summary,
            )
            
            result = await self.ai_service.quick_chat(prompt)
            self.llm_calls += 1
            
            content = result.get('content', '')
            return _extract_json_from_response(content)
            
        except Exception as e:
            logger.warn(f"LLM summary failed for {influence.user_name}: {e}")
            return None
    
    async def build_profiles(
        self,
        members: List[MemberInfluence],
        views_by_user: Dict[str, List[ExtractedView]],
    ) -> List[MemberProfile]:
        """
        Build profiles for multiple members.
        
        Args:
            members: Top N members from influence scoring
            views_by_user: Dict mapping user_id to extracted views
            
        Returns:
            List of MemberProfile objects
        """
        profiles = []
        
        for member in members:
            views = views_by_user.get(member.user_id, [])
            profile = await self.build_profile(member, views)
            profiles.append(profile)
        
        return profiles


# ═══════════════════════════════════════════════════════════════════════════════
# Singleton Instance
# ═══════════════════════════════════════════════════════════════════════════════

profile_builder = ProfileBuilder()
