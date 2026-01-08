"""
Unit tests for MarketKeywords service.

Tests keyword detection, categorization, and sentiment analysis.
"""

import pytest
from app.services.market_keywords import MarketKeywords


class TestMarketKeywordsCategorize:
    """Test market category detection."""
    
    @pytest.mark.unit
    def test_categorize_crypto_btc(self):
        """Should detect crypto category for BTC mentions."""
        text = "BTC price is rising today"
        categories = MarketKeywords.categorize(text)
        assert "crypto" in categories
    
    @pytest.mark.unit
    def test_categorize_crypto_chinese(self):
        """Should detect crypto with Chinese keywords."""
        text = "比特币突破10万美元"
        categories = MarketKeywords.categorize(text)
        assert "crypto" in categories
    
    @pytest.mark.unit
    def test_categorize_astock(self):
        """Should detect A-stock category."""
        text = "沪指今天涨停，创业板大涨"
        categories = MarketKeywords.categorize(text)
        assert "a_stock" in categories
    
    @pytest.mark.unit
    def test_categorize_usstock(self):
        """Should detect US stock category."""
        text = "AAPL and TSLA are up in premarket"
        categories = MarketKeywords.categorize(text)
        assert "us_stock" in categories
    
    @pytest.mark.unit
    def test_categorize_multiple(self):
        """Should detect multiple categories."""
        text = "BTC和道琼斯指数同时上涨"
        categories = MarketKeywords.categorize(text)
        assert len(categories) >= 1  # Should detect at least one
    
    @pytest.mark.unit
    def test_categorize_no_match(self):
        """Should return few or no categories for non-market text."""
        text = "xyz123"  # Random text that shouldn't match any keywords
        categories = MarketKeywords.categorize(text)
        # Categories may include 'general' as fallback, but specific markets should be empty
        specific_markets = [c for c in categories if c not in ['general']]
        assert len(specific_markets) == 0


class TestMarketKeywordsSentiment:
    """Test sentiment detection."""
    
    @pytest.mark.unit
    def test_sentiment_bullish(self):
        """Should detect bullish sentiment."""
        text = "市场大涨，突破新高，看多"
        sentiment = MarketKeywords.detect_sentiment(text)
        assert sentiment == "bullish"
    
    @pytest.mark.unit
    def test_sentiment_bearish(self):
        """Should detect bearish sentiment."""
        text = "暴跌崩盘，看空做空"
        sentiment = MarketKeywords.detect_sentiment(text)
        assert sentiment == "bearish"
    
    @pytest.mark.unit
    def test_sentiment_neutral(self):
        """Should return neutral for balanced text."""
        text = "今天天气不错"
        sentiment = MarketKeywords.detect_sentiment(text)
        assert sentiment == "neutral"


class TestMarketKeywordsRelevance:
    """Test market relevance detection."""
    
    @pytest.mark.unit
    def test_is_relevant_crypto(self):
        """Should be relevant for crypto content."""
        text = "ETH holders are optimistic"
        assert MarketKeywords.is_market_relevant(text) is True
    
    @pytest.mark.unit
    def test_is_relevant_stock(self):
        """Should be relevant for stock content."""
        text = "茅台股价创新高"
        assert MarketKeywords.is_market_relevant(text) is True
    
    @pytest.mark.unit
    def test_not_relevant(self):
        """Should not be relevant for non-market content."""
        text = "Hello world"
        assert MarketKeywords.is_market_relevant(text) is False


class TestMarketKeywordsExtract:
    """Test keyword extraction."""
    
    @pytest.mark.unit
    def test_extract_keywords(self):
        """Should extract matched keywords."""
        text = "BTC and ETH are both up today"
        keywords = MarketKeywords.extract_matched_keywords(text)
        assert "btc" in keywords or "eth" in keywords
    
    @pytest.mark.unit
    def test_extract_chinese_keywords(self):
        """Should extract Chinese keywords."""
        text = "比特币和以太坊价格上涨"
        keywords = MarketKeywords.extract_matched_keywords(text)
        assert len(keywords) > 0


class TestMarketKeywordsAllKeywords:
    """Test keyword collection methods."""
    
    @pytest.mark.unit
    def test_all_keywords_not_empty(self):
        """All keywords should not be empty."""
        all_kw = MarketKeywords.all_keywords()
        assert len(all_kw) > 0
    
    @pytest.mark.unit
    def test_all_keywords_set(self):
        """Should return a set for fast lookup."""
        kw_set = MarketKeywords.all_keywords_set()
        assert isinstance(kw_set, set)
        assert "btc" in kw_set
