"""
Content Filter Service

Detects and filters out unwanted content such as:
- Advertisements and promotions
- 18+ / Adult content
- Bot admission / verification messages
- Spam messages
"""

import re
from typing import Tuple
from app.core.logger import Logger

logger = Logger("ContentFilter")


class ContentFilter:
    """Filter unwanted content from messages."""
    
    # Advertisement keywords (Chinese & English)
    AD_KEYWORDS = [
        # Chinese ads
        "广告", "推广", "优惠", "折扣", "促销", "限时", "抢购", "秒杀",
        "代理", "招商", "加盟", "合作", "赚钱", "兼职", "日赚", "月入",
        "免费领", "点击领取", "扫码", "加微信", "加QQ", "私聊",
        "返利", "佣金", "提成", "分红", "投资", "理财",
        # English ads
        "advertisement", "promo", "discount", "sale", "limited time",
        "earn money", "make money", "join us", "click here",
        "free gift", "claim now", "dm me", "contact us",
    ]
    
    # 18+ / Adult content keywords
    ADULT_KEYWORDS = [
        # Chinese
        "成人", "18禁", "色情", "裸体", "性爱", "约炮", "一夜情",
        "小姐", "上门", "服务", "援交", "包养", "情色", "激情",
        "福利群", "看片", "资源群", "车群",
        # English
        "adult", "18+", "nsfw", "xxx", "porn", "sex", "nude",
        "escort", "hookup", "dating", "onlyfans",
    ]
    
    # Bot admission / verification message keywords
    BOT_ADMISSION_KEYWORDS = [
        # Chinese
        "验证", "人机验证", "点击验证", "完成验证", "通过验证",
        "入群验证", "加群验证", "新成员", "欢迎新成员",
        "发送验证码", "输入验证码", "获取验证码",
        "机器人", "自动回复", "自动消息",
        # English
        "verification", "verify", "captcha", "prove you're human",
        "welcome new member", "new member joined",
        "bot message", "automated message", "auto-reply",
    ]
    
    # Spam patterns (regex)
    SPAM_PATTERNS = [
        r"t\.me/\+\w+",  # Telegram invite links
        r"bit\.ly/\w+",  # Shortened URLs
        r"tinyurl\.com/\w+",
        r"加群.*\d{5,}",  # "Join group" with QQ numbers
        r"微信[：:]\s*\w+",  # WeChat IDs
        r"QQ[：:]\s*\d+",  # QQ numbers
        r"💰|🎁|🔥|📢|⚡",  # Common spam emojis
        r"[\u0600-\u06FF]{10,}",  # Long Arabic text (often spam)
    ]
    
    def __init__(self):
        # Compile regex patterns for performance
        self._spam_patterns = [re.compile(p, re.IGNORECASE) for p in self.SPAM_PATTERNS]
    
    def is_ad(self, text: str) -> bool:
        """Check if message contains advertisement content."""
        if not text:
            return False
        lower_text = text.lower()
        return any(kw.lower() in lower_text for kw in self.AD_KEYWORDS)
    
    def is_adult_content(self, text: str) -> bool:
        """Check if message contains 18+ / adult content."""
        if not text:
            return False
        lower_text = text.lower()
        return any(kw.lower() in lower_text for kw in self.ADULT_KEYWORDS)
    
    def is_bot_admission(self, text: str) -> bool:
        """Check if message is a bot admission / verification message."""
        if not text:
            return False
        lower_text = text.lower()
        return any(kw.lower() in lower_text for kw in self.BOT_ADMISSION_KEYWORDS)
    
    def is_spam(self, text: str) -> bool:
        """Check if message matches spam patterns."""
        if not text:
            return False
        return any(p.search(text) for p in self._spam_patterns)
    
    def check(self, text: str) -> Tuple[bool, str]:
        """
        Check if a message should be filtered.
        
        Returns:
            Tuple of (should_filter, reason)
        """
        if not text:
            return False, ""
        
        if self.is_ad(text):
            return True, "advertisement"
        
        if self.is_adult_content(text):
            return True, "adult_content"
        
        if self.is_bot_admission(text):
            return True, "bot_admission"
        
        if self.is_spam(text):
            return True, "spam"
        
        return False, ""
    
    def should_filter(self, text: str) -> bool:
        """Simple check returning True if message should be filtered."""
        should_filter, _ = self.check(text)
        return should_filter


# Singleton instance
content_filter = ContentFilter()
