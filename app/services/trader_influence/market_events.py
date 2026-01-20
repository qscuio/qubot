"""
Module 2: Market Event Identification (Non-LLM)

Detects market events from chat message patterns:
- Spikes: Sudden increase in bullish messages
- Drops: Sudden increase in bearish messages
- Divergence: High mix of bullish/bearish in short window
- High/Low: Sentiment extremes

No LLM calls - all rule-based using message density and sentiment.
"""

import hashlib
from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple

from app.core.logger import Logger
from app.services.trader_influence.data_models import (
    AnnotatedMessage,
    MarketEvent,
    EventType,
    DirectionType,
    generate_event_id,
)

logger = Logger("MarketEventDetector")


# ═══════════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════════

# Time window for event detection (minutes)
EVENT_WINDOW_MINUTES = 10

# Minimum messages in window to trigger event
MIN_MESSAGES_FOR_EVENT = 5

# Thresholds for event detection
SPIKE_THRESHOLD = 0.7       # >70% bullish messages
DROP_THRESHOLD = 0.7        # >70% bearish messages
DIVERGENCE_THRESHOLD = 0.4  # 40-60% split indicates divergence

# Intensity calculation weights
INTENSITY_WEIGHTS = {
    'density': 0.4,     # Message count / expected
    'unanimity': 0.3,   # How one-sided the sentiment
    'action': 0.3,      # How many have action words
}


# ═══════════════════════════════════════════════════════════════════════════════
# Time Window Analysis
# ═══════════════════════════════════════════════════════════════════════════════

def _group_by_time_window(
    messages: List[AnnotatedMessage],
    window_minutes: int = EVENT_WINDOW_MINUTES,
) -> Dict[datetime, List[AnnotatedMessage]]:
    """Group messages into time windows."""
    if not messages:
        return {}
    
    windows = defaultdict(list)
    
    for msg in messages:
        # Round down to window start
        window_start = msg.timestamp.replace(
            minute=(msg.timestamp.minute // window_minutes) * window_minutes,
            second=0,
            microsecond=0,
        )
        windows[window_start].append(msg)
    
    return dict(windows)


def _analyze_window(
    messages: List[AnnotatedMessage],
) -> Dict[str, float]:
    """Analyze sentiment distribution in a time window."""
    if not messages:
        return {'bullish': 0, 'bearish': 0, 'neutral': 0, 'total': 0}
    
    bullish = 0
    bearish = 0
    neutral = 0
    with_action = 0
    
    for msg in messages:
        if msg.features.direction_type == DirectionType.BULLISH:
            bullish += 1
        elif msg.features.direction_type == DirectionType.BEARISH:
            bearish += 1
        else:
            neutral += 1
        
        if msg.features.has_action:
            with_action += 1
    
    total = len(messages)
    
    return {
        'bullish': bullish,
        'bearish': bearish,
        'neutral': neutral,
        'total': total,
        'bullish_ratio': bullish / total if total > 0 else 0,
        'bearish_ratio': bearish / total if total > 0 else 0,
        'action_ratio': with_action / total if total > 0 else 0,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Event Detection Functions
# ═══════════════════════════════════════════════════════════════════════════════

def _detect_event_type(stats: Dict) -> Optional[EventType]:
    """Determine event type from window statistics."""
    if stats['total'] < MIN_MESSAGES_FOR_EVENT:
        return None
    
    bullish_ratio = stats['bullish_ratio']
    bearish_ratio = stats['bearish_ratio']
    
    # Spike: Strong bullish sentiment
    if bullish_ratio >= SPIKE_THRESHOLD:
        return EventType.SPIKE
    
    # Drop: Strong bearish sentiment
    if bearish_ratio >= DROP_THRESHOLD:
        return EventType.DROP
    
    # Divergence: Mixed signals
    if (DIVERGENCE_THRESHOLD <= bullish_ratio <= (1 - DIVERGENCE_THRESHOLD) and
        DIVERGENCE_THRESHOLD <= bearish_ratio <= (1 - DIVERGENCE_THRESHOLD)):
        return EventType.DIVERGENCE
    
    return None


def _calculate_intensity(
    stats: Dict,
    expected_density: float = 1.0,
) -> float:
    """Calculate event intensity (0-1)."""
    # Density: How active is this window vs expected
    density_score = min(1.0, stats['total'] / (expected_density * 10))
    
    # Unanimity: How one-sided is the sentiment
    max_ratio = max(stats['bullish_ratio'], stats['bearish_ratio'])
    unanimity_score = max_ratio
    
    # Action: How many have action words
    action_score = stats['action_ratio']
    
    intensity = (
        INTENSITY_WEIGHTS['density'] * density_score +
        INTENSITY_WEIGHTS['unanimity'] * unanimity_score +
        INTENSITY_WEIGHTS['action'] * action_score
    )
    
    return min(1.0, intensity)


# ═══════════════════════════════════════════════════════════════════════════════
# Market Event Detector
# ═══════════════════════════════════════════════════════════════════════════════

class MarketEventDetector:
    """
    Detects market events from chat message patterns.
    
    Events:
    - SPIKE: Sudden bullish surge
    - DROP: Sudden bearish surge
    - DIVERGENCE: High disagreement
    - HIGH/LOW: Sentiment extremes (TODO)
    
    All detection is rule-based, no LLM calls.
    """
    
    def __init__(
        self,
        window_minutes: int = EVENT_WINDOW_MINUTES,
        min_messages: int = MIN_MESSAGES_FOR_EVENT,
    ):
        self.window_minutes = window_minutes
        self.min_messages = min_messages
    
    def detect(
        self,
        messages: List[AnnotatedMessage],
    ) -> List[MarketEvent]:
        """
        Detect market events from annotated messages.
        
        Args:
            messages: Preprocessed messages with features
            
        Returns:
            List of detected MarketEvent objects
        """
        if not messages:
            return []
        
        # Group into time windows
        windows = _group_by_time_window(messages, self.window_minutes)
        
        if not windows:
            return []
        
        # Calculate expected density (messages per window on average)
        total_messages = len(messages)
        expected_density = total_messages / len(windows) if windows else 1.0
        
        events = []
        
        for window_start, window_messages in sorted(windows.items()):
            # Analyze window
            stats = _analyze_window(window_messages)
            
            # Detect event type
            event_type = _detect_event_type(stats)
            if not event_type:
                continue
            
            # Calculate intensity
            intensity = _calculate_intensity(stats, expected_density)
            
            # Create event
            window_end = window_start + timedelta(minutes=self.window_minutes)
            
            event = MarketEvent(
                event_id=generate_event_id(window_start, event_type.value),
                start_time=window_start,
                end_time=window_end,
                event_type=event_type,
                intensity=intensity,
                related_messages=[m.message_id for m in window_messages],
            )
            
            events.append(event)
            
            logger.debug(
                f"Detected {event_type.value} event at {window_start}: "
                f"intensity={intensity:.2f}, messages={len(window_messages)}"
            )
        
        # Merge adjacent events of same type
        events = self._merge_adjacent_events(events)
        
        logger.info(f"🎯 Detected {len(events)} market events")
        
        return events
    
    def _merge_adjacent_events(
        self,
        events: List[MarketEvent],
    ) -> List[MarketEvent]:
        """Merge consecutive events of the same type."""
        if len(events) <= 1:
            return events
        
        merged = []
        current = events[0]
        
        for next_event in events[1:]:
            # Check if same type and adjacent (within 2x window)
            time_gap = (next_event.start_time - current.end_time).total_seconds() / 60
            
            if (next_event.event_type == current.event_type and 
                time_gap <= self.window_minutes * 2):
                # Merge: extend current event
                current = MarketEvent(
                    event_id=current.event_id,
                    start_time=current.start_time,
                    end_time=next_event.end_time,
                    event_type=current.event_type,
                    intensity=max(current.intensity, next_event.intensity),
                    related_messages=current.related_messages + next_event.related_messages,
                )
            else:
                # Different event, save current and start new
                merged.append(current)
                current = next_event
        
        merged.append(current)
        return merged
    
    def get_events_for_timerange(
        self,
        events: List[MarketEvent],
        start: datetime,
        end: datetime,
    ) -> List[MarketEvent]:
        """Filter events within a time range."""
        return [
            e for e in events
            if e.start_time >= start and e.end_time <= end
        ]
    
    def is_key_event_participant(
        self,
        events: List[MarketEvent],
        message_ids: List[str],
    ) -> int:
        """Count how many key events a user participated in."""
        message_set = set(message_ids)
        count = 0
        
        for event in events:
            if message_set & set(event.related_messages):
                count += 1
        
        return count


# ═══════════════════════════════════════════════════════════════════════════════
# Singleton Instance
# ═══════════════════════════════════════════════════════════════════════════════

market_event_detector = MarketEventDetector()
