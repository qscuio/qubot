"""
Data Models for Trader Influence Analysis

All dataclasses and schemas for the 6-module pipeline.
Designed for traceability (message_id binding) and incremental updates.
"""

from __future__ import annotations
import json
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Dict, Optional, Any, Set
from enum import Enum


# ═══════════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════════

class DirectionType(str, Enum):
    """Market direction sentiment."""
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class ActionType(str, Enum):
    """Trading action type."""
    BUY = "buy"
    SELL = "sell"
    ADD = "add"       # 加仓
    REDUCE = "reduce" # 减仓
    HOLD = "hold"


class EventType(str, Enum):
    """Market event types detected from chat patterns."""
    SPIKE = "spike"           # 急涨
    DROP = "drop"             # 急跌
    HIGH = "high"             # 阶段高点
    LOW = "low"               # 阶段低点
    DIVERGENCE = "divergence" # 分歧集中


class RoleType(str, Enum):
    """Member role classification."""
    LEADER = "leader"         # 意见领袖
    ANALYST = "analyst"       # 分析师型
    FOLLOWER = "follower"     # 跟随者
    CONTRARIAN = "contrarian" # 逆向思维者
    NOISE = "noise"           # 噪音型


class TradingStyle(str, Enum):
    """Trading style classification."""
    TECHNICAL = "technical"   # 技术面
    FUNDAMENTAL = "fundamental" # 基本面
    SENTIMENT = "sentiment"   # 情绪面
    MIXED = "mixed"


class ViewOutcome(str, Enum):
    """Outcome of a trading view."""
    VALIDATED = "validated"   # 验证正确
    REJECTED = "rejected"     # 验证错误
    PENDING = "pending"       # 待验证


# ═══════════════════════════════════════════════════════════════════════════════
# Module 1: Preprocessor Output
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class MessageFeatures:
    """Extracted features from a message (non-LLM)."""
    has_direction: bool = False        # Contains direction words (涨/跌/多/空)
    has_action: bool = False           # Contains action words (买/卖/加仓)
    has_condition: bool = False        # Contains conditional (如果/只要/不破)
    is_hindsight: bool = False         # Post-hoc statement (果然/早就说)
    is_emotional: bool = False         # Emotional expression
    
    direction_type: Optional[DirectionType] = None
    action_type: Optional[ActionType] = None
    
    @property
    def is_forward_looking(self) -> bool:
        """A forward-looking statement has direction but isn't hindsight."""
        return self.has_direction and not self.is_hindsight
    
    @property
    def is_actionable(self) -> bool:
        """Statement that suggests action."""
        return self.has_action or (self.has_direction and self.has_condition)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_direction": self.has_direction,
            "has_action": self.has_action,
            "has_condition": self.has_condition,
            "is_hindsight": self.is_hindsight,
            "is_emotional": self.is_emotional,
            "direction_type": self.direction_type.value if self.direction_type else None,
            "action_type": self.action_type.value if self.action_type else None,
            "is_forward_looking": self.is_forward_looking,
            "is_actionable": self.is_actionable,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> MessageFeatures:
        return cls(
            has_direction=data.get("has_direction", False),
            has_action=data.get("has_action", False),
            has_condition=data.get("has_condition", False),
            is_hindsight=data.get("is_hindsight", False),
            is_emotional=data.get("is_emotional", False),
            direction_type=DirectionType(data["direction_type"]) if data.get("direction_type") else None,
            action_type=ActionType(data["action_type"]) if data.get("action_type") else None,
        )


@dataclass
class AnnotatedMessage:
    """Message with extracted features (Module 1 output)."""
    message_id: str
    user_id: str
    user_name: str
    timestamp: datetime
    text: str
    reply_to: Optional[str] = None
    
    # Annotated features
    features: MessageFeatures = field(default_factory=MessageFeatures)
    
    # Computed during graph building
    referenced_by: List[str] = field(default_factory=list)  # message_ids that reply to this
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "timestamp": self.timestamp.isoformat(),
            "text": self.text,
            "reply_to": self.reply_to,
            "features": self.features.to_dict(),
            "referenced_by": self.referenced_by,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> AnnotatedMessage:
        timestamp = data["timestamp"]
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        
        return cls(
            message_id=data["message_id"],
            user_id=data["user_id"],
            user_name=data["user_name"],
            timestamp=timestamp,
            text=data["text"],
            reply_to=data.get("reply_to"),
            features=MessageFeatures.from_dict(data.get("features", {})),
            referenced_by=data.get("referenced_by", []),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Module 2: Market Event Detection Output
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class MarketEvent:
    """Market event marker (Module 2 output)."""
    event_id: str
    start_time: datetime
    end_time: datetime
    event_type: EventType
    
    # Intensity based on message density + sentiment shift
    intensity: float = 0.5  # 0-1
    
    # Related messages for traceability
    related_messages: List[str] = field(default_factory=list)
    
    # Description (optional, can be LLM-generated later)
    description: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "event_type": self.event_type.value,
            "intensity": self.intensity,
            "related_messages": self.related_messages,
            "description": self.description,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> MarketEvent:
        return cls(
            event_id=data["event_id"],
            start_time=datetime.fromisoformat(data["start_time"].replace('Z', '+00:00')),
            end_time=datetime.fromisoformat(data["end_time"].replace('Z', '+00:00')),
            event_type=EventType(data["event_type"]),
            intensity=data.get("intensity", 0.5),
            related_messages=data.get("related_messages", []),
            description=data.get("description"),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Module 3: Influence Scoring Output
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class InfluenceWeights:
    """Configurable weights for influence scoring."""
    forward_looking: float = 3.0       # 前瞻性判断
    citation: float = 2.0              # 被引用次数
    behavior_change: float = 4.0       # 引发行为改变
    key_event: float = 2.5             # 关键节点活跃
    hindsight_penalty: float = 1.5     # 事后复盘惩罚
    emotional_penalty: float = 0.5     # 情绪刷屏惩罚
    
    def to_dict(self) -> Dict[str, float]:
        return asdict(self)


@dataclass
class InfluenceBreakdown:
    """Breakdown of influence score components."""
    forward_looking_count: int = 0
    citation_count: int = 0
    behavior_change_count: int = 0
    key_event_presence: int = 0
    hindsight_count: int = 0
    emotional_spam_count: int = 0
    
    def to_dict(self) -> Dict[str, int]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> InfluenceBreakdown:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class MemberInfluence:
    """Influence score for a member (Module 3 output)."""
    user_id: str
    user_name: str
    
    # Score breakdown
    breakdown: InfluenceBreakdown = field(default_factory=InfluenceBreakdown)
    
    # Final score and rank
    influence_score: float = 0.0
    rank: int = 0
    
    # Evidence: top influential messages
    top_messages: List[str] = field(default_factory=list)
    
    # Statistics
    total_messages: int = 0
    forward_looking_ratio: float = 0.0
    
    def calculate_score(self, weights: InfluenceWeights) -> float:
        """Calculate influence score using weighted formula."""
        score = (
            weights.forward_looking * self.breakdown.forward_looking_count
            + weights.citation * self.breakdown.citation_count
            + weights.behavior_change * self.breakdown.behavior_change_count
            + weights.key_event * self.breakdown.key_event_presence
            - weights.hindsight_penalty * self.breakdown.hindsight_count
            - weights.emotional_penalty * self.breakdown.emotional_spam_count
        )
        self.influence_score = max(0, score)
        return self.influence_score
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "user_name": self.user_name,
            "breakdown": self.breakdown.to_dict(),
            "influence_score": self.influence_score,
            "rank": self.rank,
            "top_messages": self.top_messages,
            "total_messages": self.total_messages,
            "forward_looking_ratio": self.forward_looking_ratio,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> MemberInfluence:
        return cls(
            user_id=data["user_id"],
            user_name=data["user_name"],
            breakdown=InfluenceBreakdown.from_dict(data.get("breakdown", {})),
            influence_score=data.get("influence_score", 0.0),
            rank=data.get("rank", 0),
            top_messages=data.get("top_messages", []),
            total_messages=data.get("total_messages", 0),
            forward_looking_ratio=data.get("forward_looking_ratio", 0.0),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Module 4: Opinion Extraction Output (LLM)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ExtractedView:
    """Extracted trading view (Module 4 output, LLM-generated)."""
    view_id: str
    user_id: str
    
    # Core view
    stance: DirectionType = DirectionType.NEUTRAL
    target: Optional[str] = None        # Stock code or sector
    basis: List[str] = field(default_factory=list)      # Reasoning
    conditions: List[str] = field(default_factory=list) # If X then Y
    risk_factors: List[str] = field(default_factory=list)
    
    # Source evidence (message_ids)
    evidence_messages: List[str] = field(default_factory=list)
    
    # Validation
    was_adopted: bool = False           # Others followed this view
    outcome: ViewOutcome = ViewOutcome.PENDING
    outcome_evidence: Optional[str] = None
    
    # Timestamps
    first_mentioned: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "view_id": self.view_id,
            "user_id": self.user_id,
            "stance": self.stance.value,
            "target": self.target,
            "basis": self.basis,
            "conditions": self.conditions,
            "risk_factors": self.risk_factors,
            "evidence_messages": self.evidence_messages,
            "was_adopted": self.was_adopted,
            "outcome": self.outcome.value,
            "outcome_evidence": self.outcome_evidence,
            "first_mentioned": self.first_mentioned.isoformat() if self.first_mentioned else None,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> ExtractedView:
        first_mentioned = data.get("first_mentioned")
        if isinstance(first_mentioned, str):
            first_mentioned = datetime.fromisoformat(first_mentioned.replace('Z', '+00:00'))
        
        return cls(
            view_id=data["view_id"],
            user_id=data["user_id"],
            stance=DirectionType(data.get("stance", "neutral")),
            target=data.get("target"),
            basis=data.get("basis", []),
            conditions=data.get("conditions", []),
            risk_factors=data.get("risk_factors", []),
            evidence_messages=data.get("evidence_messages", []),
            was_adopted=data.get("was_adopted", False),
            outcome=ViewOutcome(data.get("outcome", "pending")),
            outcome_evidence=data.get("outcome_evidence"),
            first_mentioned=first_mentioned,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Module 5: Member Profile Output
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class MemberProfile:
    """Complete member profile (Module 5 output)."""
    user_id: str
    user_name: str
    
    # From Module 3
    influence_score: float = 0.0
    rank: int = 0
    
    # From LLM analysis
    role_type: RoleType = RoleType.FOLLOWER
    trading_style: TradingStyle = TradingStyle.MIXED
    core_bias: str = ""                 # One-line summary of typical stance
    risk_triggers: List[str] = field(default_factory=list)
    
    # Views categorized by outcome
    validated_views: List[ExtractedView] = field(default_factory=list)
    rejected_views: List[ExtractedView] = field(default_factory=list)
    pending_views: List[ExtractedView] = field(default_factory=list)
    
    # Statistics
    accuracy_rate: float = 0.0          # validated / (validated + rejected)
    
    def calculate_accuracy(self):
        """Calculate prediction accuracy."""
        total = len(self.validated_views) + len(self.rejected_views)
        if total > 0:
            self.accuracy_rate = len(self.validated_views) / total
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "user_name": self.user_name,
            "influence_score": self.influence_score,
            "rank": self.rank,
            "role_type": self.role_type.value,
            "trading_style": self.trading_style.value,
            "core_bias": self.core_bias,
            "risk_triggers": self.risk_triggers,
            "validated_views": [v.to_dict() for v in self.validated_views],
            "rejected_views": [v.to_dict() for v in self.rejected_views],
            "pending_views": [v.to_dict() for v in self.pending_views],
            "accuracy_rate": self.accuracy_rate,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> MemberProfile:
        return cls(
            user_id=data["user_id"],
            user_name=data["user_name"],
            influence_score=data.get("influence_score", 0.0),
            rank=data.get("rank", 0),
            role_type=RoleType(data.get("role_type", "follower")),
            trading_style=TradingStyle(data.get("trading_style", "mixed")),
            core_bias=data.get("core_bias", ""),
            risk_triggers=data.get("risk_triggers", []),
            validated_views=[ExtractedView.from_dict(v) for v in data.get("validated_views", [])],
            rejected_views=[ExtractedView.from_dict(v) for v in data.get("rejected_views", [])],
            pending_views=[ExtractedView.from_dict(v) for v in data.get("pending_views", [])],
            accuracy_rate=data.get("accuracy_rate", 0.0),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Module 6: Group Insights Output
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class GroupInsights:
    """Global group analysis (Module 6 output)."""
    channel_id: str
    channel_name: str
    
    # Key members
    opinion_anchors: List[str] = field(default_factory=list)     # user_ids who set direction
    emotion_amplifiers: List[str] = field(default_factory=list)  # user_ids who amplify sentiment
    
    # Group characteristics
    group_susceptibility: float = 0.5   # 0-1, how easily swayed
    echo_chamber_score: float = 0.5     # 0=echo chamber, 1=diverse
    
    # Warnings
    over_reliance_warning: bool = False
    over_reliance_users: List[str] = field(default_factory=list)
    
    # Summary (LLM-generated)
    summary: str = ""
    
    # Timestamps
    calculated_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel_id": self.channel_id,
            "channel_name": self.channel_name,
            "opinion_anchors": self.opinion_anchors,
            "emotion_amplifiers": self.emotion_amplifiers,
            "group_susceptibility": self.group_susceptibility,
            "echo_chamber_score": self.echo_chamber_score,
            "over_reliance_warning": self.over_reliance_warning,
            "over_reliance_users": self.over_reliance_users,
            "summary": self.summary,
            "calculated_at": self.calculated_at.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> GroupInsights:
        calculated_at = data.get("calculated_at")
        if isinstance(calculated_at, str):
            calculated_at = datetime.fromisoformat(calculated_at.replace('Z', '+00:00'))
        else:
            calculated_at = datetime.now()
        
        return cls(
            channel_id=data["channel_id"],
            channel_name=data["channel_name"],
            opinion_anchors=data.get("opinion_anchors", []),
            emotion_amplifiers=data.get("emotion_amplifiers", []),
            group_susceptibility=data.get("group_susceptibility", 0.5),
            echo_chamber_score=data.get("echo_chamber_score", 0.5),
            over_reliance_warning=data.get("over_reliance_warning", False),
            over_reliance_users=data.get("over_reliance_users", []),
            summary=data.get("summary", ""),
            calculated_at=calculated_at,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Processing Result
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class InfluenceAnalysisResult:
    """Complete result of influence analysis pipeline."""
    channel_id: str
    channel_name: str
    
    # Processed data
    messages_processed: int = 0
    events_detected: int = 0
    
    # Top members
    top_members: List[MemberInfluence] = field(default_factory=list)
    profiles: List[MemberProfile] = field(default_factory=list)
    
    # Group insights
    insights: Optional[GroupInsights] = None
    
    # Processing stats
    processing_time_ms: float = 0.0
    llm_calls: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel_id": self.channel_id,
            "channel_name": self.channel_name,
            "messages_processed": self.messages_processed,
            "events_detected": self.events_detected,
            "top_members": [m.to_dict() for m in self.top_members],
            "profiles": [p.to_dict() for p in self.profiles],
            "insights": self.insights.to_dict() if self.insights else None,
            "processing_time_ms": self.processing_time_ms,
            "llm_calls": self.llm_calls,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Utility Functions
# ═══════════════════════════════════════════════════════════════════════════════

def generate_id(content: str, prefix: str = "") -> str:
    """Generate unique ID from content hash."""
    hash_val = hashlib.md5(content.encode()).hexdigest()[:8]
    return f"{prefix}{hash_val}" if prefix else hash_val


def generate_event_id(start_time: datetime, event_type: str) -> str:
    """Generate unique event ID."""
    return generate_id(f"{start_time.isoformat()}:{event_type}", "evt_")


def generate_view_id(user_id: str, stance: str, target: str) -> str:
    """Generate unique view ID."""
    return generate_id(f"{user_id}:{stance}:{target}", "view_")
