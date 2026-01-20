"""
Module 3: Influence Scoring (Core, Non-LLM)

Calculates influence score for each member based on:
- Forward-looking judgment count
- Citation/reference count (others reply to them)
- Behavior change count (others act after their advice)
- Key event presence (active during important moments)
- Penalties for hindsight and emotional spam

Formula:
influence_score = w1*forward + w2*citation + w3*behavior + w4*event
                - w5*hindsight - w6*emotional

All calculations are rule-based, no LLM calls.
"""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Dict, Set, Tuple, Optional

from app.core.logger import Logger
from app.services.trader_influence.data_models import (
    AnnotatedMessage,
    MarketEvent,
    MemberInfluence,
    InfluenceBreakdown,
    InfluenceWeights,
)

logger = Logger("InfluenceScorer")


# ═══════════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════════

# Behavior change detection: how soon after a user's message
# do we look for others to act (in minutes)
BEHAVIOR_CHANGE_WINDOW_MINUTES = 10

# Emotional spam: max messages in window before counting as spam
EMOTIONAL_SPAM_THRESHOLD = 3
EMOTIONAL_SPAM_WINDOW_MINUTES = 5

# Default number of top members to return
DEFAULT_TOP_N = 10

# Default weights (can be customized)
DEFAULT_WEIGHTS = InfluenceWeights()


# ═══════════════════════════════════════════════════════════════════════════════
# Metric Calculation Functions
# ═══════════════════════════════════════════════════════════════════════════════

def _count_forward_looking(messages: List[AnnotatedMessage]) -> int:
    """Count forward-looking (predictive) messages."""
    return sum(1 for m in messages if m.features.is_forward_looking)


def _count_hindsight(messages: List[AnnotatedMessage]) -> int:
    """Count hindsight (post-hoc) messages."""
    return sum(1 for m in messages if m.features.is_hindsight)


def _count_citations(messages: List[AnnotatedMessage]) -> int:
    """Count how many times user's messages were replied to."""
    return sum(len(m.referenced_by) for m in messages)


def _count_emotional_spam(
    messages: List[AnnotatedMessage],
    threshold: int = EMOTIONAL_SPAM_THRESHOLD,
    window_minutes: int = EMOTIONAL_SPAM_WINDOW_MINUTES,
) -> int:
    """
    Count emotional spam incidents.
    
    Spam = more than `threshold` emotional messages within `window_minutes`.
    """
    emotional_msgs = [m for m in messages if m.features.is_emotional]
    if len(emotional_msgs) < threshold:
        return 0
    
    # Sort by time
    emotional_msgs.sort(key=lambda m: m.timestamp)
    
    spam_count = 0
    window = timedelta(minutes=window_minutes)
    
    # Sliding window count
    i = 0
    for j, msg in enumerate(emotional_msgs):
        while emotional_msgs[i].timestamp < msg.timestamp - window:
            i += 1
        
        if j - i + 1 >= threshold:
            spam_count += 1
    
    return spam_count


def _count_behavior_changes(
    user_messages: List[AnnotatedMessage],
    all_messages: List[AnnotatedMessage],
    user_id: str,
    window_minutes: int = BEHAVIOR_CHANGE_WINDOW_MINUTES,
) -> int:
    """
    Count behavior changes triggered by user's messages.
    
    Behavior change = another user posts action words within window
    after this user's direction message.
    """
    # Get user's direction messages
    direction_msgs = [
        m for m in user_messages 
        if m.features.has_direction and not m.features.is_hindsight
    ]
    
    if not direction_msgs:
        return 0
    
    # Create timestamp-sorted list of all action messages from others
    other_actions = sorted([
        m for m in all_messages 
        if m.user_id != user_id and m.features.has_action
    ], key=lambda m: m.timestamp)
    
    if not other_actions:
        return 0
    
    # Count behavior changes
    window = timedelta(minutes=window_minutes)
    changes = 0
    seen_users = set()  # Don't count same user twice per direction msg
    
    for dir_msg in direction_msgs:
        seen_users.clear()
        
        for action_msg in other_actions:
            # Only look at messages after direction message
            if action_msg.timestamp <= dir_msg.timestamp:
                continue
            
            # Stop if outside window
            if action_msg.timestamp > dir_msg.timestamp + window:
                break
            
            # Count if different user we haven't seen
            if action_msg.user_id not in seen_users:
                changes += 1
                seen_users.add(action_msg.user_id)
    
    return changes


def _count_key_event_presence(
    user_message_ids: Set[str],
    events: List[MarketEvent],
) -> int:
    """Count how many key events user participated in."""
    count = 0
    
    for event in events:
        event_msg_ids = set(event.related_messages)
        if user_message_ids & event_msg_ids:
            count += 1
    
    return count


def _get_top_messages(
    messages: List[AnnotatedMessage],
    limit: int = 5,
) -> List[str]:
    """Get most influential message IDs for a user."""
    # Score each message
    scored = []
    
    for msg in messages:
        score = 0
        
        # Forward-looking is valuable
        if msg.features.is_forward_looking:
            score += 3
        
        # Action words are valuable
        if msg.features.has_action:
            score += 2
        
        # Has condition (specific) is valuable
        if msg.features.has_condition:
            score += 2
        
        # Being cited is valuable
        score += len(msg.referenced_by) * 2
        
        # Penalize hindsight
        if msg.features.is_hindsight:
            score -= 2
        
        # Penalize emotional
        if msg.features.is_emotional:
            score -= 1
        
        scored.append((msg.message_id, score))
    
    # Sort by score descending
    scored.sort(key=lambda x: x[1], reverse=True)
    
    return [msg_id for msg_id, _ in scored[:limit]]


# ═══════════════════════════════════════════════════════════════════════════════
# Influence Scorer
# ═══════════════════════════════════════════════════════════════════════════════

class InfluenceScorer:
    """
    Calculates influence scores for group members.
    
    All calculations are rule-based, no LLM calls.
    """
    
    def __init__(self, weights: InfluenceWeights = None):
        self.weights = weights or DEFAULT_WEIGHTS
    
    def score_all_members(
        self,
        messages: List[AnnotatedMessage],
        events: List[MarketEvent],
        top_n: int = DEFAULT_TOP_N,
    ) -> List[MemberInfluence]:
        """
        Calculate influence scores for all members.
        
        Args:
            messages: Preprocessed messages with features
            events: Detected market events
            top_n: Number of top members to return
            
        Returns:
            List of MemberInfluence sorted by score descending
        """
        if not messages:
            return []
        
        # Group messages by user
        user_messages: Dict[str, List[AnnotatedMessage]] = defaultdict(list)
        user_names: Dict[str, str] = {}
        
        for msg in messages:
            user_messages[msg.user_id].append(msg)
            user_names[msg.user_id] = msg.user_name
        
        # Calculate scores for each user
        results = []
        
        for user_id, user_msgs in user_messages.items():
            influence = self._score_user(
                user_id=user_id,
                user_name=user_names.get(user_id, 'Unknown'),
                user_messages=user_msgs,
                all_messages=messages,
                events=events,
            )
            results.append(influence)
        
        # Sort by score descending
        results.sort(key=lambda x: x.influence_score, reverse=True)
        
        # Assign ranks
        for i, influence in enumerate(results):
            influence.rank = i + 1
        
        logger.info(f"🏆 Scored {len(results)} members, returning top {top_n}")
        
        # Log top 3
        for influence in results[:3]:
            logger.debug(
                f"#{influence.rank} {influence.user_name}: "
                f"score={influence.influence_score:.1f}, "
                f"forward={influence.breakdown.forward_looking_count}, "
                f"cited={influence.breakdown.citation_count}"
            )
        
        return results[:top_n]
    
    def _score_user(
        self,
        user_id: str,
        user_name: str,
        user_messages: List[AnnotatedMessage],
        all_messages: List[AnnotatedMessage],
        events: List[MarketEvent],
    ) -> MemberInfluence:
        """Calculate influence score for a single user."""
        # Calculate each metric
        forward_looking = _count_forward_looking(user_messages)
        citation = _count_citations(user_messages)
        behavior_change = _count_behavior_changes(user_messages, all_messages, user_id)
        key_event = _count_key_event_presence(
            {m.message_id for m in user_messages}, 
            events
        )
        hindsight = _count_hindsight(user_messages)
        emotional_spam = _count_emotional_spam(user_messages)
        
        # Build breakdown
        breakdown = InfluenceBreakdown(
            forward_looking_count=forward_looking,
            citation_count=citation,
            behavior_change_count=behavior_change,
            key_event_presence=key_event,
            hindsight_count=hindsight,
            emotional_spam_count=emotional_spam,
        )
        
        # Get top messages
        top_messages = _get_top_messages(user_messages)
        
        # Calculate forward-looking ratio
        total = len(user_messages)
        forward_ratio = forward_looking / total if total > 0 else 0
        
        # Create influence object
        influence = MemberInfluence(
            user_id=user_id,
            user_name=user_name,
            breakdown=breakdown,
            top_messages=top_messages,
            total_messages=total,
            forward_looking_ratio=forward_ratio,
        )
        
        # Calculate final score
        influence.calculate_score(self.weights)
        
        return influence
    
    def get_user_stats(
        self,
        user_id: str,
        messages: List[AnnotatedMessage],
        events: List[MarketEvent],
    ) -> MemberInfluence:
        """Get stats for a specific user."""
        user_msgs = [m for m in messages if m.user_id == user_id]
        user_name = user_msgs[0].user_name if user_msgs else 'Unknown'
        
        return self._score_user(
            user_id=user_id,
            user_name=user_name,
            user_messages=user_msgs,
            all_messages=messages,
            events=events,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Singleton Instance
# ═══════════════════════════════════════════════════════════════════════════════

influence_scorer = InfluenceScorer()
