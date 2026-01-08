"""
Message Deduplication Service

Uses SimHash (locality-sensitive hashing) for efficient near-duplicate detection.
This allows detecting messages that are similar but not identical (e.g., minor edits,
different timestamps, or slight variations).

Key features:
- O(1) lookup time
- Memory-efficient (stores only 64-bit fingerprints)
- Detects near-duplicates (not just exact matches)
- Configurable similarity threshold
- LRU cache with automatic eviction
"""

import re
import hashlib
from collections import OrderedDict
from typing import Optional, Set, Tuple
from app.core.logger import Logger

logger = Logger("Dedup")


class SimHash:
    """
    SimHash implementation for text fingerprinting.
    
    SimHash produces similar hashes for similar inputs.
    Hamming distance between hashes indicates similarity.
    """
    
    @staticmethod
    def _tokenize(text: str) -> list:
        """Extract tokens from text (words and n-grams)."""
        if not text:
            return []
        
        # Normalize: lowercase, remove extra whitespace
        text = re.sub(r'\s+', ' ', text.lower().strip())
        
        # Remove common noise: URLs, mentions, hashtags (keep the text content)
        text = re.sub(r'https?://\S+', '', text)
        text = re.sub(r'@\w+', '', text)
        
        # Split into words
        words = text.split()
        
        # Create 2-grams and 3-grams for better similarity detection
        tokens = []
        tokens.extend(words)
        
        for i in range(len(words) - 1):
            tokens.append(f"{words[i]} {words[i+1]}")
        
        for i in range(len(words) - 2):
            tokens.append(f"{words[i]} {words[i+1]} {words[i+2]}")
        
        return tokens
    
    @staticmethod
    def _hash_token(token: str) -> int:
        """Hash a token to a 64-bit integer."""
        h = hashlib.md5(token.encode('utf-8')).digest()
        return int.from_bytes(h[:8], byteorder='big')
    
    @staticmethod
    def compute(text: str) -> int:
        """
        Compute SimHash fingerprint for text.
        Returns a 64-bit integer.
        """
        tokens = SimHash._tokenize(text)
        if not tokens:
            return 0
        
        # Initialize bit counts
        v = [0] * 64
        
        # Weight each bit position by token hashes
        for token in tokens:
            h = SimHash._hash_token(token)
            for i in range(64):
                if h & (1 << i):
                    v[i] += 1
                else:
                    v[i] -= 1
        
        # Convert to fingerprint
        fingerprint = 0
        for i in range(64):
            if v[i] > 0:
                fingerprint |= (1 << i)
        
        return fingerprint
    
    @staticmethod
    def hamming_distance(hash1: int, hash2: int) -> int:
        """Calculate Hamming distance between two fingerprints."""
        xor = hash1 ^ hash2
        count = 0
        while xor:
            count += 1
            xor &= xor - 1  # Clear lowest set bit
        return count
    
    @staticmethod
    def similarity(hash1: int, hash2: int) -> float:
        """
        Calculate similarity ratio (0.0 to 1.0).
        1.0 = identical, 0.0 = completely different
        """
        dist = SimHash.hamming_distance(hash1, hash2)
        return 1.0 - (dist / 64.0)


class MessageDeduplicator:
    """
    Efficient message deduplication using SimHash.
    
    Features:
    - Content-based fingerprinting (not just message ID)
    - Near-duplicate detection with configurable threshold
    - LRU cache with automatic eviction
    - Separate caches for different purposes (forwarding vs caching)
    """
    
    def __init__(
        self,
        max_cache_size: int = 5000,
        similarity_threshold: float = 0.85,
        min_text_length: int = 20
    ):
        """
        Initialize deduplicator.
        
        Args:
            max_cache_size: Maximum fingerprints to store
            similarity_threshold: Minimum similarity to consider as duplicate (0.0-1.0)
            min_text_length: Minimum text length to consider for dedup
        """
        self.max_cache_size = max_cache_size
        self.similarity_threshold = similarity_threshold
        self.min_text_length = min_text_length
        
        # LRU cache: fingerprint -> (channel_id, first_seen_timestamp)
        self._fingerprints: OrderedDict[int, Tuple[str, float]] = OrderedDict()
        
        # Exact hash cache for quick exact-match lookup
        self._exact_hashes: OrderedDict[str, float] = OrderedDict()
        
        # Stats
        self.stats = {
            'total_checked': 0,
            'exact_duplicates': 0,
            'near_duplicates': 0,
            'unique_messages': 0
        }
    
    def _compute_exact_hash(self, text: str) -> str:
        """Compute exact content hash (MD5)."""
        normalized = re.sub(r'\s+', ' ', text.lower().strip())
        return hashlib.md5(normalized.encode('utf-8')).hexdigest()
    
    def _evict_if_needed(self):
        """Evict oldest entries if cache is full."""
        while len(self._fingerprints) > self.max_cache_size:
            self._fingerprints.popitem(last=False)
        
        while len(self._exact_hashes) > self.max_cache_size:
            self._exact_hashes.popitem(last=False)
    
    def is_duplicate(
        self,
        text: str,
        channel_id: str = None,
        check_near_duplicates: bool = True
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if message is a duplicate.
        
        Returns:
            (is_duplicate: bool, reason: Optional[str])
            - (True, "exact") - Exact duplicate
            - (True, "near:0.92") - Near duplicate with 92% similarity
            - (False, None) - Unique message
        """
        import time
        
        self.stats['total_checked'] += 1
        
        # Skip very short messages
        if not text or len(text) < self.min_text_length:
            return False, None
        
        # Check exact hash first (O(1) average)
        exact_hash = self._compute_exact_hash(text)
        if exact_hash in self._exact_hashes:
            self.stats['exact_duplicates'] += 1
            logger.debug(f"🔄 Exact duplicate detected: {text[:50]}...")
            return True, "exact"
        
        # Check near-duplicates using SimHash
        if check_near_duplicates:
            fingerprint = SimHash.compute(text)
            
            # Compare with existing fingerprints
            for existing_fp, (existing_channel, _) in self._fingerprints.items():
                similarity = SimHash.similarity(fingerprint, existing_fp)
                if similarity >= self.similarity_threshold:
                    self.stats['near_duplicates'] += 1
                    logger.debug(f"🔄 Near duplicate ({similarity:.0%}): {text[:50]}...")
                    return True, f"near:{similarity:.2f}"
            
            # Store new fingerprint
            self._fingerprints[fingerprint] = (channel_id or '', time.time())
        
        # Store exact hash
        self._exact_hashes[exact_hash] = time.time()
        
        # Evict old entries
        self._evict_if_needed()
        
        self.stats['unique_messages'] += 1
        return False, None
    
    def add_message(self, text: str, channel_id: str = None):
        """
        Add a message to the dedup cache without checking.
        Useful for pre-populating from database.
        """
        import time
        
        if not text or len(text) < self.min_text_length:
            return
        
        exact_hash = self._compute_exact_hash(text)
        fingerprint = SimHash.compute(text)
        
        self._exact_hashes[exact_hash] = time.time()
        self._fingerprints[fingerprint] = (channel_id or '', time.time())
        
        self._evict_if_needed()
    
    def clear(self):
        """Clear all cached fingerprints."""
        self._fingerprints.clear()
        self._exact_hashes.clear()
        self.stats = {
            'total_checked': 0,
            'exact_duplicates': 0,
            'near_duplicates': 0,
            'unique_messages': 0
        }
    
    def get_stats(self) -> dict:
        """Get deduplication statistics."""
        return {
            **self.stats,
            'cache_size': len(self._fingerprints),
            'exact_cache_size': len(self._exact_hashes),
            'dedup_rate': (
                (self.stats['exact_duplicates'] + self.stats['near_duplicates']) /
                max(1, self.stats['total_checked'])
            )
        }


# Global singleton instance - uses config values
def _create_deduplicator():
    from app.core.config import settings
    return MessageDeduplicator(
        max_cache_size=settings.DEDUP_CACHE_SIZE,
        similarity_threshold=settings.DEDUP_SIMILARITY_THRESHOLD,
        min_text_length=20
    )

# Lazy initialization
_deduplicator_instance = None

def get_deduplicator() -> MessageDeduplicator:
    global _deduplicator_instance
    if _deduplicator_instance is None:
        _deduplicator_instance = _create_deduplicator()
    return _deduplicator_instance

# For backward compatibility
message_deduplicator = MessageDeduplicator(
    max_cache_size=5000,
    similarity_threshold=0.85,
    min_text_length=20
)
