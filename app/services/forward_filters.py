"""
Forward Filter Framework

Extensible filter chain for message forwarding. Filters run in priority order
(lowest first). FilterResult includes target channel for forwarding.

Filter Actions:
- CONTINUE: Pass to next filter
- FORWARD: Forward to specified target (stop chain)
- BLOCK: Block message (stop chain)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Any

from app.core.config import settings
from app.core.logger import Logger
from app.core.timezone import CHINA_TZ as SHANGHAI_TZ, china_now

logger = Logger("ForwardFilters")


class FilterAction(Enum):
    """Action to take after filter check."""
    CONTINUE = "continue"  # Pass to next filter
    FORWARD = "forward"    # Forward to target (stop chain)
    BLOCK = "block"        # Block message (stop chain)


@dataclass
class FilterResult:
    """Result from filter check, includes target channel for FORWARD action."""
    action: FilterAction
    reason: str = ""
    target_channel: Optional[str] = None  # Target for FORWARD action


@dataclass
class FilterContext:
    """Context passed through filter chain."""
    # Message content
    message_text: str
    message_id: int
    message_time: Optional[datetime] = None
    
    # Sender info
    sender_id: str = ""
    sender_username: Optional[str] = None
    sender_name: str = "Unknown"
    
    # Chat info
    chat_id: str = ""
    chat_username: Optional[str] = None
    chat_title: str = "Unknown"
    
    # Default target channel
    default_target: Optional[str] = None
    
    # Media info
    has_media: bool = False
    
    # Service references
    monitor_service: Any = None
    telegram_service: Any = None
    
    # Cache
    _cache: dict = field(default_factory=dict)


class ForwardFilter(ABC):
    """Base class for filters."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        pass
    
    @property
    @abstractmethod
    def priority(self) -> int:
        pass
    
    @abstractmethod
    def check(self, ctx: FilterContext) -> FilterResult:
        pass


class FilterChain:
    """Runs filters in priority order."""
    
    def __init__(self):
        self._filters: List[ForwardFilter] = []
        self._sorted = True
    
    def add(self, f: ForwardFilter):
        self._filters.append(f)
        self._sorted = False
    
    def remove(self, name: str) -> bool:
        for i, f in enumerate(self._filters):
            if f.name == name:
                self._filters.pop(i)
                return True
        return False
    
    def _sort(self):
        if not self._sorted:
            self._filters.sort(key=lambda f: f.priority)
            self._sorted = True
    
    def run(self, ctx: FilterContext) -> FilterResult:
        """Run filters, return final result with target channel."""
        self._sort()
        
        for f in self._filters:
            try:
                result = f.check(ctx)
                
                if result.action == FilterAction.FORWARD:
                    # Use filter's target or fall back to default
                    if not result.target_channel:
                        result.target_channel = ctx.default_target
                    logger.debug(f"✅ {f.name}: FORWARD -> {result.target_channel}")
                    return result
                
                if result.action == FilterAction.BLOCK:
                    logger.debug(f"🚫 {f.name}: BLOCK ({result.reason})")
                    return result
                    
            except Exception as e:
                logger.error(f"Filter {f.name} error: {e}")
        
        # All passed - forward to default target
        return FilterResult(
            action=FilterAction.FORWARD,
            reason="all_filters_passed",
            target_channel=ctx.default_target
        )
    
    def list_filters(self) -> List[dict]:
        self._sort()
        return [{"name": f.name, "priority": f.priority} for f in self._filters]


# =============================================================================
# Filter Implementations
# =============================================================================

class VIPFilter(ForwardFilter):
    """Priority 10: VIP users forward immediately to VIP channel."""
    
    @property
    def name(self) -> str:
        return "vip"
    
    @property
    def priority(self) -> int:
        return 10
    
    def check(self, ctx: FilterContext) -> FilterResult:
        if not ctx.monitor_service:
            return FilterResult(FilterAction.CONTINUE)
        
        is_vip = ctx.monitor_service.is_vip_user(ctx.sender_id, ctx.sender_username)
        if is_vip:
            vip_channel = ctx.monitor_service.vip_target_channel or ctx.default_target
            return FilterResult(
                FilterAction.FORWARD,
                f"vip:{ctx.sender_name}",
                target_channel=vip_channel
            )
        return FilterResult(FilterAction.CONTINUE)


class OwnAccountFilter(ForwardFilter):
    """Priority 20: Block own accounts and private bot chats."""
    
    @property
    def name(self) -> str:
        return "own_account"
    
    @property
    def priority(self) -> int:
        return 20
    
    def check(self, ctx: FilterContext) -> FilterResult:
        # Block private bot chats - user commands should not be forwarded
        if ctx.chat_username and ctx.chat_username.lower().endswith('bot'):
            return FilterResult(FilterAction.BLOCK, "private_bot_chat")
        
        if not ctx.telegram_service:
            return FilterResult(FilterAction.CONTINUE)
        
        try:
            sid = int(ctx.sender_id) if ctx.sender_id.isdigit() else 0
            if sid in ctx.telegram_service.own_user_ids:
                return FilterResult(FilterAction.BLOCK, "own_account")
        except (ValueError, AttributeError):
            pass
        return FilterResult(FilterAction.CONTINUE)


class TargetChannelFilter(ForwardFilter):
    """Priority 30: Block own target channels."""
    
    @property
    def name(self) -> str:
        return "target_channel"
    
    @property
    def priority(self) -> int:
        return 30
    
    def check(self, ctx: FilterContext) -> FilterResult:
        if ctx.monitor_service and ctx.monitor_service._is_own_target_channel(ctx.chat_id):
            return FilterResult(FilterAction.BLOCK, "own_target")
        return FilterResult(FilterAction.CONTINUE)


class TimeRestrictionFilter(ForwardFilter):
    """Priority 40: Only forward between 6 AM and 12 PM."""
    
    @property
    def name(self) -> str:
        return "time_restriction"
    
    @property
    def priority(self) -> int:
        return 40
    
    def check(self, ctx: FilterContext) -> FilterResult:
        hour = china_now().hour
        # Allow forwarding only between 6 AM and 12 PM (noon)
        if hour < 6:
            return FilterResult(FilterAction.BLOCK, f"before_6am:{hour}:00")
        if hour >= 12:
            return FilterResult(FilterAction.BLOCK, f"after_noon:{hour}:00")
        return FilterResult(FilterAction.CONTINUE)


class BlacklistFilter(ForwardFilter):
    """Priority 50: Block blacklisted channels."""
    
    @property
    def name(self) -> str:
        return "blacklist"
    
    @property
    def priority(self) -> int:
        return 50
    
    def check(self, ctx: FilterContext) -> FilterResult:
        if ctx.monitor_service and ctx.monitor_service.is_blacklisted(ctx.chat_username, ctx.chat_id):
            return FilterResult(FilterAction.BLOCK, f"blacklist:{ctx.chat_title}")
        return FilterResult(FilterAction.CONTINUE)


class ContentTypeFilter(ForwardFilter):
    """Priority 60: Block spam/ads/adult."""
    
    @property
    def name(self) -> str:
        return "content_type"
    
    @property
    def priority(self) -> int:
        return 60
    
    def check(self, ctx: FilterContext) -> FilterResult:
        from app.services.content_filter import content_filter
        should_filter, reason = content_filter.check(ctx.message_text)
        if should_filter:
            return FilterResult(FilterAction.BLOCK, reason)
        return FilterResult(FilterAction.CONTINUE)


class SourceChannelFilter(ForwardFilter):
    """Priority 70: Only monitored sources."""
    
    @property
    def name(self) -> str:
        return "source_channel"
    
    @property
    def priority(self) -> int:
        return 70
    
    def check(self, ctx: FilterContext) -> FilterResult:
        if not ctx.monitor_service:
            return FilterResult(FilterAction.CONTINUE)
        
        sources = ctx.monitor_service.source_channels
        if not sources:
            return FilterResult(FilterAction.CONTINUE)
        
        for src in sources:
            if ctx.monitor_service.matches_source(src, ctx.chat_username, ctx.chat_id):
                if src in ctx.monitor_service.disabled_sources:
                    return FilterResult(FilterAction.BLOCK, f"disabled:{src}")
                return FilterResult(FilterAction.CONTINUE)
        
        return FilterResult(FilterAction.BLOCK, "not_monitored")


class FromUsersFilter(ForwardFilter):
    """Priority 80: User whitelist."""
    
    @property
    def name(self) -> str:
        return "from_users"
    
    @property
    def priority(self) -> int:
        return 80
    
    def check(self, ctx: FilterContext) -> FilterResult:
        users = settings.from_users_list
        if not users:
            return FilterResult(FilterAction.CONTINUE)
        
        for u in users:
            if u in (ctx.sender_username, f"@{ctx.sender_username}", ctx.sender_id):
                return FilterResult(FilterAction.CONTINUE)
        
        return FilterResult(FilterAction.BLOCK, "user_not_allowed")


class KeywordFilter(ForwardFilter):
    """Priority 90: Keyword matching."""
    
    @property
    def name(self) -> str:
        return "keyword"
    
    @property
    def priority(self) -> int:
        return 90
    
    def check(self, ctx: FilterContext) -> FilterResult:
        keywords = settings.keywords_list
        if not keywords:
            return FilterResult(FilterAction.CONTINUE)
        
        lower = ctx.message_text.lower()
        if any(kw.lower() in lower for kw in keywords):
            return FilterResult(FilterAction.CONTINUE)
        
        return FilterResult(FilterAction.BLOCK, "no_keyword")


class DeduplicationFilter(ForwardFilter):
    """Priority 100: Block duplicates."""
    
    @property
    def name(self) -> str:
        return "deduplication"
    
    @property
    def priority(self) -> int:
        return 100
    
    def check(self, ctx: FilterContext) -> FilterResult:
        from app.services.message_dedup import get_deduplicator
        is_dup, reason = get_deduplicator().is_duplicate(
            ctx.message_text, channel_id=ctx.chat_id, check_near_duplicates=True
        )
        if is_dup:
            return FilterResult(FilterAction.BLOCK, f"dup:{reason}")
        return FilterResult(FilterAction.CONTINUE)


def create_default_filter_chain() -> FilterChain:
    """Create chain with all default filters."""
    chain = FilterChain()
    chain.add(VIPFilter())
    chain.add(OwnAccountFilter())
    chain.add(TargetChannelFilter())
    chain.add(TimeRestrictionFilter())
    chain.add(BlacklistFilter())
    chain.add(ContentTypeFilter())
    chain.add(SourceChannelFilter())
    chain.add(FromUsersFilter())
    chain.add(KeywordFilter())
    chain.add(DeduplicationFilter())
    logger.info(f"Created filter chain with {len(chain._filters)} filters")
    return chain
