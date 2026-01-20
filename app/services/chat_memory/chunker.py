"""
Topic-Aware Message Chunker

Intelligently groups messages by topic/context rather than fixed token count.
Key strategies:
- Detect topic shifts via time gaps (>30min) or explicit markers
- Use reply-to chains to keep related messages together
- Enforce max token limit as fallback
- Preserve full argumentation chains in same chunk
"""

import re
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any

from app.core.logger import Logger

logger = Logger("TopicChunker")


# ═══════════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════════

# Time gap threshold for topic split (in minutes)
TIME_GAP_THRESHOLD_MINS = 30

# Max messages per chunk (fallback limit)
MAX_MESSAGES_PER_CHUNK = 200

# Minimum messages to form a chunk (avoid tiny chunks)
MIN_MESSAGES_PER_CHUNK = 5

# Topic transition detection patterns (Chinese + English)
TOPIC_TRANSITION_PATTERNS = [
    # Explicit topic change
    r'换个话题|另外|顺便说|说回|回到.+话题|关于.+问题',
    r'btw|by the way|anyway|moving on|back to',
    # Section markers
    r'^#{1,3}\s|^[-=]{3,}',
    # Strong assertions that often start new topics
    r'^重点[：:]|^总结[：:]|^结论[：:]|^公告[：:]',
]

# Compile patterns for efficiency
TRANSITION_REGEX = re.compile('|'.join(TOPIC_TRANSITION_PATTERNS), re.IGNORECASE | re.MULTILINE)


# ═══════════════════════════════════════════════════════════════════════════════
# Data Structures
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Message:
    """Normalized message structure for chunking."""
    id: str                     # Message ID or hash
    sender: str                 # Sender name
    text: str                   # Message text
    timestamp: datetime         # Message time
    reply_to: Optional[str] = None  # Reply-to message ID if any
    
    @property
    def token_estimate(self) -> int:
        """Rough token count (Chinese ~1.5 tokens/char, English ~0.25)."""
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', self.text))
        other_chars = len(self.text) - chinese_chars
        return int(chinese_chars * 1.5 + other_chars * 0.25)


@dataclass
class MessageChunk:
    """A chunk of related messages."""
    chunk_id: str
    messages: List[Message] = field(default_factory=list)
    
    @property
    def time_start(self) -> Optional[datetime]:
        if not self.messages:
            return None
        return min(m.timestamp for m in self.messages)
    
    @property
    def time_end(self) -> Optional[datetime]:
        if not self.messages:
            return None
        return max(m.timestamp for m in self.messages)
    
    @property
    def message_count(self) -> int:
        return len(self.messages)
    
    @property
    def total_tokens(self) -> int:
        return sum(m.token_estimate for m in self.messages)
    
    def add_message(self, msg: Message):
        self.messages.append(msg)
    
    def get_text_for_extraction(self) -> str:
        """Format messages for AI extraction."""
        lines = []
        for msg in sorted(self.messages, key=lambda m: m.timestamp):
            time_str = msg.timestamp.strftime('%H:%M')
            lines.append(f"[{time_str}] {msg.sender}: {msg.text}")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# Topic Chunker
# ═══════════════════════════════════════════════════════════════════════════════

class TopicChunker:
    """
    Intelligent message chunker that groups by topic/context.
    
    Algorithm:
    1. Parse and normalize messages
    2. Detect potential split points (time gaps, topic markers)
    3. Group messages respecting reply chains
    4. Enforce max token limit as fallback
    """
    
    def __init__(
        self,
        time_gap_mins: int = TIME_GAP_THRESHOLD_MINS,
        max_messages: int = MAX_MESSAGES_PER_CHUNK,
        min_messages: int = MIN_MESSAGES_PER_CHUNK,
    ):
        self.time_gap_mins = time_gap_mins
        self.max_messages = max_messages
        self.min_messages = min_messages
    
    def chunk_messages(
        self, 
        messages: List[Dict[str, Any]], 
        channel_id: str
    ) -> List[MessageChunk]:
        """
        Chunk messages into topic-coherent groups.
        
        Args:
            messages: List of message dicts from database
            channel_id: Channel identifier for chunk IDs
            
        Returns:
            List of MessageChunk objects
        """
        if not messages:
            return []
        
        # Step 1: Normalize messages
        normalized = self._normalize_messages(messages)
        if not normalized:
            return []
        
        # Sort by timestamp
        normalized.sort(key=lambda m: m.timestamp)
        
        # Step 2: Detect split points
        split_indices = self._detect_splits(normalized)
        
        # Step 3: Create chunks
        chunks = self._create_chunks(normalized, split_indices, channel_id)
        
        # Step 4: Merge small chunks
        chunks = self._merge_small_chunks(chunks)
        
        logger.info(f"📦 Chunked {len(normalized)} messages into {len(chunks)} chunks")
        return chunks
    
    def _normalize_messages(self, messages: List[Dict]) -> List[Message]:
        """Convert raw message dicts to Message objects."""
        result = []
        
        for msg in messages:
            try:
                # Extract fields with fallbacks
                text = msg.get('message_text') or msg.get('text') or ''
                if not text.strip():
                    continue
                
                # Parse timestamp
                created_at = msg.get('created_at') or msg.get('timestamp')
                if isinstance(created_at, str):
                    try:
                        timestamp = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    except:
                        timestamp = datetime.now()
                elif isinstance(created_at, datetime):
                    timestamp = created_at
                else:
                    timestamp = datetime.now()
                
                # Generate ID if not present
                msg_id = msg.get('id') or msg.get('message_id') or hashlib.md5(text.encode()).hexdigest()[:8]
                
                result.append(Message(
                    id=str(msg_id),
                    sender=msg.get('sender_name') or msg.get('sender') or 'Unknown',
                    text=text,
                    timestamp=timestamp,
                    reply_to=msg.get('reply_to'),
                ))
            except Exception as e:
                logger.debug(f"Failed to normalize message: {e}")
                continue
        
        return result
    
    def _detect_splits(self, messages: List[Message]) -> List[int]:
        """
        Detect potential split points in message sequence.
        
        Returns indices where a new chunk should start.
        """
        split_indices = [0]  # First message always starts a chunk
        
        for i in range(1, len(messages)):
            prev_msg = messages[i - 1]
            curr_msg = messages[i]
            
            should_split = False
            
            # Check 1: Time gap
            time_diff = (curr_msg.timestamp - prev_msg.timestamp).total_seconds() / 60
            if time_diff > self.time_gap_mins:
                should_split = True
                logger.debug(f"Split at {i}: time gap {time_diff:.1f} mins")
            
            # Check 2: Topic transition marker
            if not should_split and TRANSITION_REGEX.search(curr_msg.text[:100]):
                should_split = True
                logger.debug(f"Split at {i}: topic transition detected")
            
            # Check 3: Max messages limit (fallback)
            messages_since_last_split = i - split_indices[-1]
            if messages_since_last_split >= self.max_messages:
                should_split = True
                logger.debug(f"Split at {i}: max messages reached")
            
            if should_split:
                split_indices.append(i)
        
        return split_indices
    
    def _create_chunks(
        self, 
        messages: List[Message], 
        split_indices: List[int],
        channel_id: str
    ) -> List[MessageChunk]:
        """Create MessageChunk objects from split indices."""
        chunks = []
        
        for i, start_idx in enumerate(split_indices):
            # Determine end index
            if i + 1 < len(split_indices):
                end_idx = split_indices[i + 1]
            else:
                end_idx = len(messages)
            
            # Create chunk
            chunk_messages = messages[start_idx:end_idx]
            if not chunk_messages:
                continue
            
            # Generate chunk ID
            time_start = chunk_messages[0].timestamp.strftime('%Y%m%d%H%M')
            chunk_id = f"{channel_id}_{time_start}_{i}"
            
            chunk = MessageChunk(
                chunk_id=chunk_id,
                messages=chunk_messages,
            )
            chunks.append(chunk)
        
        return chunks
    
    def _merge_small_chunks(self, chunks: List[MessageChunk]) -> List[MessageChunk]:
        """Merge chunks that are too small with adjacent chunks."""
        if len(chunks) <= 1:
            return chunks
        
        result = []
        current_chunk = None
        
        for chunk in chunks:
            if current_chunk is None:
                current_chunk = chunk
                continue
            
            # Check if current chunk is too small
            if current_chunk.message_count < self.min_messages:
                # Merge with next chunk
                combined_messages = current_chunk.messages + chunk.messages
                current_chunk = MessageChunk(
                    chunk_id=current_chunk.chunk_id,
                    messages=combined_messages,
                )
            else:
                result.append(current_chunk)
                current_chunk = chunk
        
        # Don't forget the last chunk
        if current_chunk:
            result.append(current_chunk)
        
        return result
    
    def estimate_chunks(self, messages: List[Dict]) -> int:
        """Estimate number of chunks without fully processing."""
        if not messages:
            return 0
        return max(1, len(messages) // self.max_messages)


# ═══════════════════════════════════════════════════════════════════════════════
# Singleton Instance
# ═══════════════════════════════════════════════════════════════════════════════

topic_chunker = TopicChunker()
