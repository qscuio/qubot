"""
Unit tests for configuration module.

Tests environment variable parsing and settings validation.
"""

import os
import pytest
from unittest.mock import patch


class TestParseCommaList:
    """Test comma-separated list parsing."""
    
    @pytest.mark.unit
    def test_parse_simple_list(self):
        """Should parse simple comma-separated values."""
        from app.core.config import parse_comma_list
        result = parse_comma_list("a,b,c")
        assert result == ["a", "b", "c"]
    
    @pytest.mark.unit
    def test_parse_with_spaces(self):
        """Should strip whitespace."""
        from app.core.config import parse_comma_list
        result = parse_comma_list(" a , b , c ")
        assert result == ["a", "b", "c"]
    
    @pytest.mark.unit
    def test_parse_none_value(self):
        """Should treat 'none' as empty list."""
        from app.core.config import parse_comma_list
        result = parse_comma_list("none")
        assert result == []
    
    @pytest.mark.unit
    def test_parse_none_case_insensitive(self):
        """Should handle 'NONE' case insensitively."""
        from app.core.config import parse_comma_list
        result = parse_comma_list("NONE")
        assert result == []
    
    @pytest.mark.unit
    def test_parse_already_list(self):
        """Should return list as-is."""
        from app.core.config import parse_comma_list
        result = parse_comma_list(["x", "y"])
        assert result == ["x", "y"]
    
    @pytest.mark.unit
    def test_parse_empty_string(self):
        """Should handle empty string."""
        from app.core.config import parse_comma_list
        result = parse_comma_list("")
        assert result == []


class TestSettingsProperties:
    """Test Settings class properties."""
    
    @pytest.mark.unit
    def test_source_channels_list(self):
        """Should parse SOURCE_CHANNELS properly."""
        with patch.dict(os.environ, {"SOURCE_CHANNELS": "ch1,ch2,ch3"}):
            from app.core.config import Settings
            settings = Settings()
            assert settings.source_channels_list == ["ch1", "ch2", "ch3"]
    
    @pytest.mark.unit
    def test_keywords_list_none(self):
        """Should return empty list for 'none' keywords."""
        with patch.dict(os.environ, {"KEYWORDS": "none"}):
            from app.core.config import Settings
            settings = Settings()
            assert settings.keywords_list == []
    
    @pytest.mark.unit
    def test_allowed_users_list(self):
        """Should parse ALLOWED_USERS as integers."""
        with patch.dict(os.environ, {"ALLOWED_USERS": "123,456,789"}):
            from app.core.config import Settings
            settings = Settings()
            assert settings.allowed_users_list == [123, 456, 789]


class TestSettingsAIKey:
    """Test AI API key resolution."""
    
    @pytest.mark.unit
    def test_get_ai_key_groq(self):
        """Should return Groq key for groq provider."""
        with patch.dict(os.environ, {"GROQ_API_KEY": "groq-test-key"}):
            from app.core.config import Settings
            settings = Settings()
            key = settings.get_ai_key("groq")
            assert key == "groq-test-key"
    
    @pytest.mark.unit
    def test_get_ai_key_default_provider(self):
        """Should use default provider if none specified."""
        with patch.dict(os.environ, {
            "AI_PROVIDER": "gemini",
            "GEMINI_API_KEY": "gemini-test-key"
        }):
            from app.core.config import Settings
            settings = Settings()
            key = settings.get_ai_key()
            assert key == "gemini-test-key"


class TestSessionsJSON:
    """Test session JSON parsing."""
    
    @pytest.mark.unit
    def test_sessions_list_valid(self):
        """Should parse valid sessions JSON."""
        sessions = '[{"session":"abc","api_id":123,"api_hash":"xyz"}]'
        with patch.dict(os.environ, {"TG_SESSIONS_JSON": sessions}):
            from app.core.config import Settings
            settings = Settings()
            result = settings.sessions_list
            assert len(result) == 1
            assert result[0]["session"] == "abc"
    
    @pytest.mark.unit
    def test_sessions_list_invalid(self):
        """Should return empty list for invalid JSON."""
        with patch.dict(os.environ, {"TG_SESSIONS_JSON": "not-valid-json"}):
            from app.core.config import Settings
            settings = Settings()
            result = settings.sessions_list
            assert result == []
    
    @pytest.mark.unit
    def test_sessions_list_empty(self):
        """Should return empty list when not set."""
        with patch.dict(os.environ, {}, clear=True):
            from app.core.config import Settings
            settings = Settings()
            result = settings.sessions_list
            assert result == []
