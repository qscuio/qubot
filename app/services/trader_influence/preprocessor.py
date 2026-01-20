"""
Module 1: Data Preprocessor (Non-LLM)

Annotates messages with features using regex patterns:
- Direction words (涨/跌/多/空)
- Action words (买/卖/加仓/减仓)
- Condition words (如果/只要/不破)
- Hindsight markers (果然/早就说)
- Emotional expressions

Also builds the reply graph for citation tracking.
No LLM calls - all rule-based.
"""

import re
import hashlib
from collections import defaultdict
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any

from app.core.logger import Logger
from app.services.trader_influence.data_models import (
    AnnotatedMessage,
    MessageFeatures,
    DirectionType,
    ActionType,
)

logger = Logger("TraderPreprocessor")


# ═══════════════════════════════════════════════════════════════════════════════
# Feature Detection Patterns (Rule-based, No LLM)
# ═══════════════════════════════════════════════════════════════════════════════

# Direction patterns - detect bullish/bearish sentiment
DIRECTION_PATTERNS = {
    DirectionType.BULLISH: [
        r'(?:看)?涨|做?多|牛|冲|拉升|起飞|突破|上攻|反弹|新高',
        r'利好|利多|利涨|强势|暴涨|大涨',
        r'买买买|抄底|满仓|加仓',
        r'long|bullish|up|moon|pump',
    ],
    DirectionType.BEARISH: [
        r'(?:看)?跌|做?空|熊|崩|下跌|跳水|破位|下杀|回调',
        r'利空|利跌|弱势|暴跌|大跌|腰斩',
        r'卖卖卖|清仓|跑|撤',
        r'short|bearish|down|crash|dump',
    ],
}

# Action patterns - detect trading actions
ACTION_PATTERNS = {
    ActionType.BUY: [
        r'买入?|进场?|建仓|开多|做多|抄底',
        r'buy|long|enter|open',
    ],
    ActionType.SELL: [
        r'卖出?|出场?|清仓|平仓|止盈|止损',
        r'sell|close|exit|take profit|stop loss',
    ],
    ActionType.ADD: [
        r'加仓|补仓|加[多空]|追[多空]',
        r'add|double down',
    ],
    ActionType.REDUCE: [
        r'减仓|减[多空]|部分平',
        r'reduce|scale out',
    ],
}

# Condition patterns - detect conditional statements (forward-looking)
CONDITION_PATTERNS = [
    r'如果|只要|除非|一旦|等到|要是',
    r'(?:不)?破[位\d]|站稳|突破.{0,5}就|跌破.{0,5}就',
    r'到了?[就再]|达到.{0,5}就',
    r'if|unless|once|when|provided',
]

# Hindsight patterns - detect post-hoc statements (should be penalized)
HINDSIGHT_PATTERNS = [
    r'果然|早就说|之前说|我说的吧|验证了|应验',
    r'看吧|怎么样|对吧|没错吧',
    r'told you|saw it coming|predicted|called it|i said',
]

# Emotional patterns - detect non-analytical emotional expressions
EMOTIONAL_PATTERNS = [
    r'[!！]{2,}',                              # Multiple exclamations
    r'[?？]{2,}',                              # Multiple questions
    r'卧槽|我[草艹操靠]|天啊|完蛋|牛[逼批]|太[牛猛]了',
    r'哈哈{2,}|呵呵{2,}|[哭泣流泪😭😢]+',
    r'🚀{2,}|💰{2,}|🔥{2,}',                   # Emoji spam
    r'aww+|wow+|omg|wtf|lmao|fuck',
]

# Compile all patterns for efficiency
def _compile_patterns(pattern_dict: Dict) -> Dict:
    """Compile regex patterns for a category dict."""
    return {
        key: [re.compile(p, re.IGNORECASE) for p in patterns]
        for key, patterns in pattern_dict.items()
    }

def _compile_list(patterns: List[str]) -> List:
    """Compile a list of patterns."""
    return [re.compile(p, re.IGNORECASE) for p in patterns]

COMPILED_DIRECTION = _compile_patterns(DIRECTION_PATTERNS)
COMPILED_ACTION = _compile_patterns(ACTION_PATTERNS)
COMPILED_CONDITION = _compile_list(CONDITION_PATTERNS)
COMPILED_HINDSIGHT = _compile_list(HINDSIGHT_PATTERNS)
COMPILED_EMOTIONAL = _compile_list(EMOTIONAL_PATTERNS)


# ═══════════════════════════════════════════════════════════════════════════════
# Feature Detection Functions
# ═══════════════════════════════════════════════════════════════════════════════

def detect_direction(text: str) -> Tuple[bool, Optional[DirectionType]]:
    """Detect if text contains direction words and which type."""
    for direction_type, patterns in COMPILED_DIRECTION.items():
        for pattern in patterns:
            if pattern.search(text):
                return True, direction_type
    return False, None


def detect_action(text: str) -> Tuple[bool, Optional[ActionType]]:
    """Detect if text contains action words and which type."""
    for action_type, patterns in COMPILED_ACTION.items():
        for pattern in patterns:
            if pattern.search(text):
                return True, action_type
    return False, None


def detect_condition(text: str) -> bool:
    """Detect if text contains conditional statements."""
    for pattern in COMPILED_CONDITION:
        if pattern.search(text):
            return True
    return False


def detect_hindsight(text: str) -> bool:
    """Detect if text is a hindsight/post-hoc statement."""
    for pattern in COMPILED_HINDSIGHT:
        if pattern.search(text):
            return True
    return False


def detect_emotional(text: str) -> bool:
    """Detect if text is primarily emotional expression."""
    for pattern in COMPILED_EMOTIONAL:
        if pattern.search(text):
            return True
    return False


def extract_features(text: str) -> MessageFeatures:
    """Extract all features from message text."""
    has_direction, direction_type = detect_direction(text)
    has_action, action_type = detect_action(text)
    has_condition = detect_condition(text)
    is_hindsight = detect_hindsight(text)
    is_emotional = detect_emotional(text)
    
    return MessageFeatures(
        has_direction=has_direction,
        has_action=has_action,
        has_condition=has_condition,
        is_hindsight=is_hindsight,
        is_emotional=is_emotional,
        direction_type=direction_type,
        action_type=action_type,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Preprocessor Class
# ═══════════════════════════════════════════════════════════════════════════════

class Preprocessor:
    """
    Message preprocessor that annotates features and builds reply graph.
    
    All operations are rule-based, no LLM calls.
    """
    
    def process(
        self,
        messages: List[Dict[str, Any]],
    ) -> List[AnnotatedMessage]:
        """
        Process raw messages into annotated messages with features.
        
        Args:
            messages: Raw message dicts with message_id, user_id, user_name,
                     timestamp, text, reply_to
                     
        Returns:
            List of AnnotatedMessage with features and reply graph
        """
        if not messages:
            return []
        
        # Step 1: Normalize and sort by timestamp
        normalized = self._normalize_messages(messages)
        normalized.sort(key=lambda m: m.timestamp)
        
        # Step 2: Extract features for each message
        for msg in normalized:
            msg.features = extract_features(msg.text)
        
        # Step 3: Build reply graph
        self._build_reply_graph(normalized)
        
        logger.info(f"📝 Preprocessed {len(normalized)} messages")
        
        # Log feature stats
        forward_count = sum(1 for m in normalized if m.features.is_forward_looking)
        action_count = sum(1 for m in normalized if m.features.has_action)
        hindsight_count = sum(1 for m in normalized if m.features.is_hindsight)
        emotional_count = sum(1 for m in normalized if m.features.is_emotional)
        
        logger.debug(
            f"Features: forward_looking={forward_count}, "
            f"action={action_count}, hindsight={hindsight_count}, "
            f"emotional={emotional_count}"
        )
        
        return normalized
    
    def _normalize_messages(self, messages: List[Dict]) -> List[AnnotatedMessage]:
        """Convert raw message dicts to AnnotatedMessage objects."""
        result = []
        
        for msg in messages:
            try:
                # Extract required fields
                text = msg.get('text') or msg.get('message_text') or ''
                if not text.strip():
                    continue
                
                # Parse timestamp
                timestamp = msg.get('timestamp') or msg.get('created_at')
                if isinstance(timestamp, str):
                    try:
                        timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    except:
                        timestamp = datetime.now()
                elif not isinstance(timestamp, datetime):
                    timestamp = datetime.now()
                
                # Generate message ID if not present
                message_id = msg.get('message_id') or msg.get('id')
                if not message_id:
                    message_id = hashlib.md5(
                        f"{msg.get('user_id', '')}:{timestamp.isoformat()}:{text[:50]}".encode()
                    ).hexdigest()[:12]
                
                result.append(AnnotatedMessage(
                    message_id=str(message_id),
                    user_id=str(msg.get('user_id') or 'unknown'),
                    user_name=msg.get('user_name') or msg.get('sender_name') or 'Unknown',
                    timestamp=timestamp,
                    text=text,
                    reply_to=msg.get('reply_to'),
                ))
            except Exception as e:
                logger.debug(f"Failed to normalize message: {e}")
                continue
        
        return result
    
    def _build_reply_graph(self, messages: List[AnnotatedMessage]):
        """Build reply graph - track which messages reference which."""
        # Create message index
        msg_index = {m.message_id: m for m in messages}
        
        # Build reverse references
        for msg in messages:
            if msg.reply_to and msg.reply_to in msg_index:
                msg_index[msg.reply_to].referenced_by.append(msg.message_id)
    
    def get_user_messages(
        self,
        messages: List[AnnotatedMessage],
        user_id: str,
        only_forward_looking: bool = False,
    ) -> List[AnnotatedMessage]:
        """Get all messages from a specific user."""
        user_msgs = [m for m in messages if m.user_id == user_id]
        
        if only_forward_looking:
            user_msgs = [m for m in user_msgs if m.features.is_forward_looking]
        
        return user_msgs
    
    def get_forward_looking_messages(
        self,
        messages: List[AnnotatedMessage],
    ) -> List[AnnotatedMessage]:
        """Get all forward-looking (predictive) messages."""
        return [m for m in messages if m.features.is_forward_looking]


# ═══════════════════════════════════════════════════════════════════════════════
# Singleton Instance
# ═══════════════════════════════════════════════════════════════════════════════

preprocessor = Preprocessor()
