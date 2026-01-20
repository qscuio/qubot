"""
Trader Influence Analysis System

A pipeline-based system to analyze stock trading group chats:
1. Identify influential members based on behavior + time
2. Extract trading views with evidence binding
3. Build member profiles with validated/rejected views
4. Generate group-level insights

Architecture:
    Messages → Preprocessing → Event Detection → Influence Scoring
            → Opinion Extraction (LLM) → Profile Building → Insights
"""

from app.services.trader_influence.data_models import (
    AnnotatedMessage,
    MarketEvent,
    MemberInfluence,
    ExtractedView,
    MemberProfile,
    GroupInsights,
    InfluenceWeights,
)
from app.services.trader_influence.service import (
    TraderInfluenceService,
    trader_influence_service,
)

__all__ = [
    # Data models
    "AnnotatedMessage",
    "MarketEvent",
    "MemberInfluence",
    "ExtractedView",
    "MemberProfile",
    "GroupInsights",
    "InfluenceWeights",
    # Service
    "TraderInfluenceService",
    "trader_influence_service",
]
