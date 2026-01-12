"""
Hot Words Service

Daily trending word statistics with database persistence.
Uses jieba for Chinese text segmentation.
"""

import re
from collections import Counter
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional

from app.core.logger import Logger
from app.core.database import db
from app.core.timezone import china_strftime, china_now
from app.services.market_keywords import MarketKeywords

logger = Logger("HotWordsService")


class HotWordsService:
    """Daily hot words statistics service with persistence."""
    
    # Stop words (filter out meaningless words)
    STOP_WORDS = {
        # Chinese
        "的", "了", "是", "在", "有", "和", "就", "都", "而", "及",
        "这", "那", "个", "也", "不", "人", "我", "他", "你", "它",
        "吗", "呢", "啊", "吧", "呀", "哦", "嗯", "哈", "哪", "怎么",
        "什么", "为什么", "如何", "可以", "可能", "应该", "需要",
        "一个", "一些", "这个", "那个", "这些", "那些",
        "但是", "因为", "所以", "如果", "虽然", "然后", "或者",
        "还是", "已经", "正在", "将要", "会", "能", "要",
        # English
        "the", "a", "an", "is", "are", "was", "were", "be", "to", "of",
        "and", "or", "but", "in", "on", "at", "for", "with", "by",
        "from", "up", "about", "into", "over", "after",
        "this", "that", "these", "those", "it", "its",
        "i", "you", "he", "she", "we", "they", "my", "your", "his", "her",
        "what", "which", "who", "when", "where", "why", "how",
        "not", "no", "yes", "just", "only", "also", "very", "so",
    }
    
    def __init__(self):
        self.daily_words: Dict[str, Counter] = {}  # date -> Counter
        self._jieba_initialized = False
    
    def _init_jieba(self):
        """Lazy initialize jieba with market keywords."""
        if self._jieba_initialized:
            return
        
        try:
            import jieba
            # Add market keywords to jieba dictionary
            for word in MarketKeywords.all_keywords():
                if len(word) >= 2:
                    jieba.add_word(word.lower())
            self._jieba_initialized = True
            logger.info("jieba initialized with market keywords")
        except ImportError:
            logger.warn("jieba not installed, using simple segmentation")
            self._jieba_initialized = True
    
    def extract_words(self, text: str) -> List[str]:
        """Extract meaningful words from text."""
        if not text:
            return []
        
        self._init_jieba()
        
        try:
            import jieba
            words = list(jieba.cut(text))
        except ImportError:
            # Fallback: simple regex split
            words = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', text)
        
        # Filter words
        result = []
        for w in words:
            w = w.strip().lower()
            if len(w) < 2:
                continue
            if w in self.STOP_WORDS:
                continue
            if w.isdigit():
                continue
            # Skip pure punctuation
            if re.match(r'^[^\w\u4e00-\u9fff]+$', w):
                continue
            result.append(w)
        
        return result
    
    def add_message(self, text: str, date: str = None):
        """Add message to hot words statistics."""
        if not text:
            return
        
        date = date or china_strftime('%Y-%m-%d')
        if date not in self.daily_words:
            self.daily_words[date] = Counter()
        
        words = self.extract_words(text)
        self.daily_words[date].update(words)
    
    def get_hot_words(self, date: str = None, top_n: int = 20) -> List[Tuple[str, int]]:
        """Get hot words for a specific date."""
        date = date or china_strftime('%Y-%m-%d')
        counter = self.daily_words.get(date, Counter())
        return counter.most_common(top_n)
    
    def get_hot_words_dict(self, date: str = None, top_n: int = 20) -> Dict[str, int]:
        """Get hot words as a dictionary."""
        hot = self.get_hot_words(date, top_n)
        return {word: count for word, count in hot}
    
    async def persist_to_db(self, date: str = None):
        """Persist hot words to database."""
        if not db.pool:
            logger.warn("Database not available for hot words persistence")
            return
        
        date = date or china_strftime('%Y-%m-%d')
        counter = self.daily_words.get(date)
        if not counter:
            return
        
        try:
            async with db.pool.acquire() as conn:
                for word, count in counter.most_common(100):  # Top 100
                    # Determine category
                    categories = MarketKeywords.categorize(word)
                    category = categories[0] if categories else "general"
                    
                    await conn.execute("""
                        INSERT INTO hot_words (date, word, count, category)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT (date, word) 
                        DO UPDATE SET count = hot_words.count + $3
                    """, date, word, count, category)
            
            logger.info(f"Persisted {len(counter)} hot words for {date}")
        except Exception as e:
            logger.error(f"Failed to persist hot words: {e}")
    
    async def load_from_db(self, date: str = None) -> List[Tuple[str, int]]:
        """Load hot words from database."""
        if not db.pool:
            return []
        
        date = date or china_strftime('%Y-%m-%d')
        
        try:
            rows = await db.pool.fetch("""
                SELECT word, count FROM hot_words 
                WHERE date = $1 
                ORDER BY count DESC 
                LIMIT 50
            """, date)
            return [(row['word'], row['count']) for row in rows]
        except Exception as e:
            logger.error(f"Failed to load hot words: {e}")
            return []
    
    async def get_trending(self, days: int = 7, top_n: int = 10) -> List[Dict]:
        """Get trending words (rising frequency over past days)."""
        if not db.pool:
            return []
        
        today = china_strftime('%Y-%m-%d')
        week_ago = (china_now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        try:
            # Get words that appeared more today than average
            rows = await db.pool.fetch("""
                WITH today_words AS (
                    SELECT word, count FROM hot_words WHERE date = $1
                ),
                history_avg AS (
                    SELECT word, AVG(count) as avg_count 
                    FROM hot_words 
                    WHERE date >= $2 AND date < $1
                    GROUP BY word
                )
                SELECT 
                    t.word, 
                    t.count as today_count,
                    COALESCE(h.avg_count, 0) as avg_count,
                    t.count - COALESCE(h.avg_count, 0) as growth
                FROM today_words t
                LEFT JOIN history_avg h ON t.word = h.word
                ORDER BY growth DESC
                LIMIT $3
            """, today, week_ago, top_n)
            
            return [
                {
                    "word": row['word'],
                    "today_count": row['today_count'],
                    "avg_count": float(row['avg_count']),
                    "growth": float(row['growth'])
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Failed to get trending words: {e}")
            return []
    
    def format_report(self, date: str = None, top_n: int = 15) -> str:
        """Generate hot words report in markdown format."""
        hot = self.get_hot_words(date, top_n)
        
        if not hot:
            return "## 🔥 今日热词\n\n暂无数据"
        
        lines = ["## 🔥 今日热词", ""]
        for i, (word, count) in enumerate(hot, 1):
            if i == 1:
                emoji = "🥇"
            elif i == 2:
                emoji = "🥈"
            elif i == 3:
                emoji = "🥉"
            else:
                emoji = f"{i}."
            
            # Add market category badge
            categories = MarketKeywords.categorize(word)
            cat_badge = ""
            if "crypto" in categories:
                cat_badge = " `加密`"
            elif "a_stock" in categories:
                cat_badge = " `A股`"
            elif "us_stock" in categories:
                cat_badge = " `美股`"
            elif "hk_stock" in categories:
                cat_badge = " `港股`"
            elif "futures" in categories:
                cat_badge = " `期货`"
            elif "forex" in categories:
                cat_badge = " `外汇`"
            
            lines.append(f"{emoji} **{word}**{cat_badge} ({count}次)")
        
        return "\n".join(lines)
    
    def clear_date(self, date: str = None):
        """Clear hot words for a specific date."""
        date = date or china_strftime('%Y-%m-%d')
        if date in self.daily_words:
            del self.daily_words[date]


# Singleton instance
hot_words_service = HotWordsService()
