"""
Message Compressor Service

Cleans, filters, scores, and structures messages for report generation.
Outputs structured data with market categorization, sentiment, and hot words.
"""

import re
import json
import hashlib
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import List, Dict, Optional, Any

from app.core.logger import Logger
from app.core.config import settings
from app.core.database import db
from app.services.content_filter import content_filter
from app.services.market_keywords import MarketKeywords
from app.services.hot_words import hot_words_service

logger = Logger("MessageCompressor")


@dataclass
class StructuredMessage:
    """Structured message with metadata."""
    id: str                       # Unique ID (hash)
    channel_id: str               # Source channel ID
    channel_name: str             # Channel display name
    sender: str                   # Sender name
    content: str                  # Message content
    timestamp: str                # Timestamp (ISO format)
    score: float                  # Quality score 0-1
    categories: List[str]         # Market categories [crypto, a_stock, us_stock, ...]
    keywords: List[str]           # Extracted keywords
    has_numbers: bool             # Contains numeric data
    has_url: bool                 # Contains URL
    sentiment: str                # Sentiment: bullish/bearish/neutral
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class CompressionResult:
    """Result of message compression."""
    channel_id: str
    channel_name: str
    original_count: int           # Original message count
    compressed_count: int         # Compressed message count
    compression_ratio: float      # Compression ratio
    messages: List[StructuredMessage] = field(default_factory=list)
    hot_words: Dict[str, int] = field(default_factory=dict)
    category_stats: Dict[str, int] = field(default_factory=dict)
    sentiment_stats: Dict[str, int] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "channel_id": self.channel_id,
            "channel_name": self.channel_name,
            "original_count": self.original_count,
            "compressed_count": self.compressed_count,
            "compression_ratio": round(self.compression_ratio, 3),
            "messages": [m.to_dict() for m in self.messages],
            "hot_words": self.hot_words,
            "category_stats": self.category_stats,
            "sentiment_stats": self.sentiment_stats,
        }
    
    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


class MessageCompressor:
    """
    Message compression pipeline:
    1. Clean and filter (remove ads, spam, duplicates)
    2. Score by quality and relevance
    3. Structure with metadata
    4. Extract hot words
    """
    
    # Configuration with defaults
    MIN_LENGTH = getattr(settings, 'COMPRESSOR_MIN_LENGTH', 15)
    MAX_MESSAGES = getattr(settings, 'COMPRESSOR_MAX_MESSAGES', 50)
    SCORE_THRESHOLD = getattr(settings, 'COMPRESSOR_SCORE_THRESHOLD', 0.2)
    
    def __init__(self):
        self._seen_hashes: set = set()  # For deduplication
    
    async def compress(
        self, 
        messages: List[Dict], 
        channel_id: str,
        channel_name: str
    ) -> CompressionResult:
        """
        Compress and structure messages.
        
        Args:
            messages: List of message dicts from database
            channel_id: Source channel ID
            channel_name: Channel display name
            
        Returns:
            CompressionResult with structured messages and statistics
        """
        original_count = len(messages)
        if original_count == 0:
            return CompressionResult(
                channel_id=channel_id,
                channel_name=channel_name,
                original_count=0,
                compressed_count=0,
                compression_ratio=0.0
            )
        
        # Reset dedup cache
        self._seen_hashes.clear()
        
        # Step 1: Clean and filter
        cleaned = self._clean(messages)
        logger.debug(f"Cleaned: {original_count} -> {len(cleaned)}")
        
        # Step 2: Score and sort
        scored = self._score_all(cleaned, channel_id, channel_name)
        scored.sort(key=lambda x: x['_score'], reverse=True)
        
        # Step 3: Take top N above threshold
        top_messages = [
            m for m in scored 
            if m['_score'] >= self.SCORE_THRESHOLD
        ][:self.MAX_MESSAGES]
        
        # Step 4: Convert to structured format
        structured = [
            self._to_structured(m, channel_id, channel_name)
            for m in top_messages
        ]
        
        # Step 5: Extract statistics
        hot_words = self._extract_hot_words(structured)
        category_stats = self._count_categories(structured)
        sentiment_stats = self._count_sentiments(structured)
        
        # Add to global hot words service
        for msg in structured:
            hot_words_service.add_message(msg.content)
        
        compressed_count = len(structured)
        ratio = compressed_count / original_count if original_count > 0 else 0
        
        logger.info(
            f"📦 Compressed {channel_name}: "
            f"{original_count} -> {compressed_count} ({ratio:.1%})"
        )
        
        return CompressionResult(
            channel_id=channel_id,
            channel_name=channel_name,
            original_count=original_count,
            compressed_count=compressed_count,
            compression_ratio=ratio,
            messages=structured,
            hot_words=hot_words,
            category_stats=category_stats,
            sentiment_stats=sentiment_stats,
        )
    
    def _clean(self, messages: List[Dict]) -> List[Dict]:
        """Step 1: Clean and filter messages."""
        cleaned = []
        
        for msg in messages:
            text = msg.get('message_text') or ''
            
            # Skip empty or too short
            if len(text.strip()) < self.MIN_LENGTH:
                continue
            
            # Skip using content filter (ads, adult, spam, bot admission)
            should_filter, reason = content_filter.check(text)
            if should_filter:
                continue
            
            # Skip duplicates (by content hash)
            content_hash = hashlib.md5(text.encode()).hexdigest()
            if content_hash in self._seen_hashes:
                continue
            self._seen_hashes.add(content_hash)
            
            # Skip pure emoji/media placeholder messages
            text_only = re.sub(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]', '', text)
            if len(text_only.strip()) < 10:
                continue
            
            cleaned.append(msg)
        
        return cleaned
    
    def _score_all(self, messages: List[Dict], channel_id: str, channel_name: str) -> List[Dict]:
        """Step 2: Score all messages by quality."""
        for msg in messages:
            msg['_score'] = self._score_message(msg, channel_id, channel_name)
        return messages
    
    def _score_message(self, msg: Dict, channel_id: str, channel_name: str) -> float:
        """
        Score a single message (0.0 - 1.0).
        
        Scoring factors:
        - Market keywords: +0.3
        - Numeric data: +0.2
        - Proper length: +0.15
        - URL reference: +0.15
        - Sentiment strength: +0.1
        - VIP source: +0.1
        """
        text = msg.get('message_text', '')
        score = 0.0
        
        # Market keywords presence (+0.3)
        if MarketKeywords.is_market_relevant(text):
            # More keywords = higher score
            keywords = MarketKeywords.extract_matched_keywords(text)
            score += min(0.3, 0.05 * len(keywords) + 0.1)
        
        # Contains numeric data (+0.2)
        # Numbers with units (%, $, ¥, K, M, B) are more valuable
        if re.search(r'\d+\.?\d*\s*[%$¥KMB万亿]', text):
            score += 0.2
        elif re.search(r'\d+\.?\d*', text):
            score += 0.1
        
        # Proper length (+0.15)
        # Too short = low info, too long = possibly spam
        length = len(text)
        if 50 <= length <= 500:
            score += 0.15
        elif 30 <= length < 50 or 500 < length <= 1000:
            score += 0.1
        elif length > 1000:
            score += 0.05
        
        # Contains URL reference (+0.15)
        if re.search(r'https?://[^\s]+', text):
            score += 0.15
        
        # Sentiment strength (+0.1)
        sentiment = MarketKeywords.detect_sentiment(text)
        if sentiment in ("bullish", "bearish"):
            score += 0.1
        
        # Source credibility (placeholder for future)
        # Can add VIP user detection here
        
        return min(score, 1.0)
    
    def _to_structured(
        self, 
        msg: Dict, 
        channel_id: str, 
        channel_name: str
    ) -> StructuredMessage:
        """Step 4: Convert to structured format."""
        text = msg.get('message_text', '')
        created_at = msg.get('created_at')
        
        # Generate unique ID
        msg_id = hashlib.md5(text.encode()).hexdigest()[:8]
        
        # Parse timestamp
        if isinstance(created_at, datetime):
            timestamp = created_at.isoformat()
        elif created_at:
            timestamp = str(created_at)
        else:
            timestamp = datetime.now().isoformat()
        
        return StructuredMessage(
            id=msg_id,
            channel_id=channel_id,
            channel_name=channel_name,
            sender=msg.get('sender_name', 'Unknown'),
            content=text,
            timestamp=timestamp,
            score=msg.get('_score', 0.0),
            categories=MarketKeywords.categorize(text),
            keywords=MarketKeywords.extract_matched_keywords(text),
            has_numbers=bool(re.search(r'\d+\.?\d*', text)),
            has_url=bool(re.search(r'https?://', text)),
            sentiment=MarketKeywords.detect_sentiment(text),
        )
    
    def _extract_hot_words(self, messages: List[StructuredMessage]) -> Dict[str, int]:
        """Extract hot words from structured messages."""
        from collections import Counter
        counter = Counter()
        
        for msg in messages:
            counter.update(msg.keywords)
        
        return dict(counter.most_common(20))
    
    def _count_categories(self, messages: List[StructuredMessage]) -> Dict[str, int]:
        """Count messages by market category."""
        from collections import Counter
        counter = Counter()
        
        for msg in messages:
            for cat in msg.categories:
                counter[cat] += 1
        
        return dict(counter)
    
    def _count_sentiments(self, messages: List[StructuredMessage]) -> Dict[str, int]:
        """Count messages by sentiment."""
        from collections import Counter
        counter = Counter()
        
        for msg in messages:
            counter[msg.sentiment] += 1
        
        return dict(counter)
    
    def format_for_prompt(self, result: CompressionResult) -> str:
        """Format compression result for AI prompt."""
        lines = []
        
        # Header with stats
        lines.append(f"📊 原始消息: {result.original_count} 条 → 压缩后: {result.compressed_count} 条")
        lines.append("")
        
        # Category distribution
        if result.category_stats:
            cat_str = ", ".join([f"{k}: {v}" for k, v in result.category_stats.items()])
            lines.append(f"📁 分类: {cat_str}")
        
        # Sentiment distribution
        if result.sentiment_stats:
            sent_str = ", ".join([f"{k}: {v}" for k, v in result.sentiment_stats.items()])
            lines.append(f"📈 情绪: {sent_str}")
        
        lines.append("")
        lines.append("─" * 40)
        lines.append("")
        
        # Messages
        for msg in result.messages:
            time_str = msg.timestamp.split('T')[1][:5] if 'T' in msg.timestamp else msg.timestamp
            cat_tag = "/".join(msg.categories[:2])  # Limit to 2 categories
            sentiment_emoji = "📈" if msg.sentiment == "bullish" else "📉" if msg.sentiment == "bearish" else ""
            
            lines.append(f"[{time_str}] [{cat_tag}] {sentiment_emoji} {msg.sender}:")
            lines.append(f"  {msg.content[:300]}{'...' if len(msg.content) > 300 else ''}")
            lines.append("")
        
        return "\n".join(lines)


# Singleton instance
message_compressor = MessageCompressor()
