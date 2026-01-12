"""
Unit tests for Forward Filter Framework.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch
import pytz

from app.services.forward_filters import (
    FilterAction, FilterResult, FilterContext, FilterChain,
    ForwardFilter, VIPFilter, OwnAccountFilter, TimeRestrictionFilter,
    BlacklistFilter, ContentTypeFilter, KeywordFilter, DeduplicationFilter,
    create_default_filter_chain, SHANGHAI_TZ
)


class TestFilterResult:
    """Test FilterResult dataclass."""
    
    @pytest.mark.unit
    def test_filter_result_defaults(self):
        result = FilterResult(FilterAction.CONTINUE)
        assert result.action == FilterAction.CONTINUE
        assert result.reason == ""
        assert result.target_channel is None
    
    @pytest.mark.unit
    def test_filter_result_with_target(self):
        result = FilterResult(FilterAction.FORWARD, "vip:user", "-12345")
        assert result.action == FilterAction.FORWARD
        assert result.reason == "vip:user"
        assert result.target_channel == "-12345"


class TestFilterChain:
    """Test FilterChain execution."""
    
    @pytest.fixture
    def chain(self):
        return FilterChain()
    
    @pytest.fixture
    def ctx(self):
        return FilterContext(
            message_text="Test message",
            message_id=123,
            sender_id="456",
            chat_id="789",
            default_target="-100111"
        )
    
    @pytest.mark.unit
    def test_empty_chain_forwards(self, chain, ctx):
        """Empty chain should forward to default target."""
        result = chain.run(ctx)
        assert result.action == FilterAction.FORWARD
        assert result.target_channel == "-100111"
    
    @pytest.mark.unit
    def test_block_stops_chain(self, chain, ctx):
        """BLOCK action should stop chain."""
        class BlockFilter(ForwardFilter):
            @property
            def name(self): return "blocker"
            @property
            def priority(self): return 50
            def check(self, ctx): return FilterResult(FilterAction.BLOCK, "blocked")
        
        class NeverReached(ForwardFilter):
            @property
            def name(self): return "never"
            @property
            def priority(self): return 100
            def check(self, ctx):
                raise Exception("Should not be called")
        
        chain.add(BlockFilter())
        chain.add(NeverReached())
        
        result = chain.run(ctx)
        assert result.action == FilterAction.BLOCK
        assert result.reason == "blocked"
    
    @pytest.mark.unit
    def test_forward_stops_chain(self, chain, ctx):
        """FORWARD action should stop chain with target."""
        class EarlyForwarder(ForwardFilter):
            @property
            def name(self): return "forwarder"
            @property
            def priority(self): return 50
            def check(self, ctx): 
                return FilterResult(FilterAction.FORWARD, "early", "-999")
        
        chain.add(EarlyForwarder())
        result = chain.run(ctx)
        assert result.action == FilterAction.FORWARD
        assert result.target_channel == "-999"
    
    @pytest.mark.unit
    def test_priority_order(self, chain, ctx):
        """Filters should run in priority order."""
        order = []
        
        class LowPriority(ForwardFilter):
            @property
            def name(self): return "low"
            @property
            def priority(self): return 100
            def check(self, c):
                order.append("low")
                return FilterResult(FilterAction.CONTINUE)
        
        class HighPriority(ForwardFilter):
            @property
            def name(self): return "high"
            @property
            def priority(self): return 10
            def check(self, c):
                order.append("high")
                return FilterResult(FilterAction.CONTINUE)
        
        chain.add(LowPriority())
        chain.add(HighPriority())
        chain.run(ctx)
        
        assert order == ["high", "low"]


class TestVIPFilter:
    """Test VIPFilter."""
    
    @pytest.mark.unit
    def test_vip_forwards_to_vip_channel(self):
        """VIP user should forward to VIP channel."""
        monitor = MagicMock()
        monitor.is_vip_user.return_value = True
        monitor.vip_target_channel = "-vip123"
        
        ctx = FilterContext(
            message_text="test",
            message_id=1,
            sender_id="user1",
            sender_name="VipUser",
            default_target="-default",
            monitor_service=monitor
        )
        
        f = VIPFilter()
        result = f.check(ctx)
        
        assert result.action == FilterAction.FORWARD
        assert result.target_channel == "-vip123"
        assert "vip:" in result.reason
    
    @pytest.mark.unit
    def test_non_vip_continues(self):
        """Non-VIP should continue."""
        monitor = MagicMock()
        monitor.is_vip_user.return_value = False
        
        ctx = FilterContext(
            message_text="test",
            message_id=1,
            sender_id="user1",
            monitor_service=monitor
        )
        
        f = VIPFilter()
        result = f.check(ctx)
        
        assert result.action == FilterAction.CONTINUE


class TestTimeRestrictionFilter:
    """Test TimeRestrictionFilter."""
    
    @pytest.mark.unit
    def test_before_noon_continues(self):
        """Before noon should continue."""
        with patch('app.services.forward_filters.datetime') as mock_dt:
            mock_now = MagicMock()
            mock_now.hour = 9
            mock_dt.now.return_value = mock_now
            
            f = TimeRestrictionFilter()
            ctx = FilterContext(message_text="test", message_id=1)
            result = f.check(ctx)
            
            assert result.action == FilterAction.CONTINUE
    
    @pytest.mark.unit
    def test_after_noon_blocks(self):
        """After noon should block."""
        with patch('app.services.forward_filters.datetime') as mock_dt:
            mock_now = MagicMock()
            mock_now.hour = 14
            mock_dt.now.return_value = mock_now
            
            f = TimeRestrictionFilter()
            ctx = FilterContext(message_text="test", message_id=1)
            result = f.check(ctx)
            
            assert result.action == FilterAction.BLOCK
            assert "after_noon" in result.reason


class TestKeywordFilter:
    """Test KeywordFilter."""
    
    @pytest.mark.unit
    def test_no_keywords_continues(self):
        """No keywords configured should continue."""
        with patch('app.services.forward_filters.settings') as mock_settings:
            mock_settings.keywords_list = []
            
            f = KeywordFilter()
            ctx = FilterContext(message_text="test", message_id=1)
            result = f.check(ctx)
            
            assert result.action == FilterAction.CONTINUE
    
    @pytest.mark.unit
    def test_keyword_match_continues(self):
        """Keyword match should continue."""
        with patch('app.services.forward_filters.settings') as mock_settings:
            mock_settings.keywords_list = ["bitcoin", "eth"]
            
            f = KeywordFilter()
            ctx = FilterContext(message_text="Bitcoin price rising", message_id=1)
            result = f.check(ctx)
            
            assert result.action == FilterAction.CONTINUE
    
    @pytest.mark.unit
    def test_no_keyword_match_blocks(self):
        """No keyword match should block."""
        with patch('app.services.forward_filters.settings') as mock_settings:
            mock_settings.keywords_list = ["bitcoin", "eth"]
            
            f = KeywordFilter()
            ctx = FilterContext(message_text="Weather is nice today", message_id=1)
            result = f.check(ctx)
            
            assert result.action == FilterAction.BLOCK


class TestCreateDefaultFilterChain:
    """Test factory function."""
    
    @pytest.mark.unit
    def test_creates_chain_with_filters(self):
        """Should create chain with all default filters."""
        chain = create_default_filter_chain()
        filters = chain.list_filters()
        
        assert len(filters) == 10
        names = [f["name"] for f in filters]
        assert "vip" in names
        assert "time_restriction" in names
        assert "blacklist" in names
        assert "deduplication" in names
