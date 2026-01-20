"""
Unit tests for Signal Detection Framework.

Tests the core signal detection infrastructure:
- SignalResult dataclass
- SignalDetector base class
- SignalRegistry registration and lookup
"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock
from datetime import date, timedelta

from app.services.scanner.base import SignalResult, SignalDetector
from app.services.scanner.registry import SignalRegistry


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_hist():
    """Sample stock history DataFrame."""
    n = 30
    dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(n)]
    return pd.DataFrame({
        '日期': dates,
        '开盘': [10.0 + i * 0.1 for i in range(n)],
        '收盘': [10.2 + i * 0.1 for i in range(n)],
        '最高': [10.5 + i * 0.1 for i in range(n)],
        '最低': [9.8 + i * 0.1 for i in range(n)],
        '成交量': [100000 + i * 1000 for i in range(n)],
        '换手率': [2.0 + i * 0.1 for i in range(n)],
    })


@pytest.fixture
def sample_stock_info():
    """Sample stock info dict."""
    return {"code": "000001", "name": "测试股票"}


@pytest.fixture
def clean_registry():
    """Provide a clean registry for each test."""
    # Save current state
    saved = SignalRegistry._signals.copy()
    SignalRegistry.clear()
    yield SignalRegistry
    # Restore original state
    SignalRegistry._signals = saved


# ─────────────────────────────────────────────────────────────────────────────
# SignalResult Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSignalResult:
    """Tests for SignalResult dataclass."""
    
    @pytest.mark.unit
    def test_signal_result_triggered(self):
        """Triggered result should have triggered=True."""
        result = SignalResult(triggered=True)
        assert result.triggered is True
        assert result.metadata == {}
    
    @pytest.mark.unit
    def test_signal_result_not_triggered(self):
        """Not triggered result should have triggered=False."""
        result = SignalResult(triggered=False)
        assert result.triggered is False
    
    @pytest.mark.unit
    def test_signal_result_with_metadata(self):
        """Result can include metadata."""
        result = SignalResult(
            triggered=True,
            metadata={"score": 85, "reason": "breakout"}
        )
        assert result.triggered is True
        assert result.metadata["score"] == 85
        assert result.metadata["reason"] == "breakout"


# ─────────────────────────────────────────────────────────────────────────────
# SignalDetector Base Class Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSignalDetector:
    """Tests for SignalDetector base class."""
    
    @pytest.mark.unit
    def test_detector_cannot_be_instantiated_directly(self):
        """Abstract class should not be directly instantiable for detect()."""
        # Creating instance works (no abstract __init__)
        # But calling detect() should fail
        class IncompleteSignal(SignalDetector):
            signal_id = "incomplete"
        
        with pytest.raises(TypeError):
            IncompleteSignal()  # Cannot instantiate without implementing detect
    
    @pytest.mark.unit
    def test_detector_with_implementation(self, sample_hist, sample_stock_info):
        """Properly implemented detector should work."""
        class TestSignal(SignalDetector):
            signal_id = "test_signal"
            display_name = "Test Signal"
            icon = "🧪"
            
            def detect(self, hist, stock_info):
                return SignalResult(triggered=True, metadata={"test": "data"})
        
        detector = TestSignal()
        result = detector.detect(sample_hist, sample_stock_info)
        
        assert result.triggered is True
        assert result.metadata["test"] == "data"
    
    @pytest.mark.unit
    def test_detector_default_values(self):
        """Detector should have sensible defaults."""
        class MinimalSignal(SignalDetector):
            signal_id = "minimal"
            
            def detect(self, hist, stock_info):
                return SignalResult(triggered=False)
        
        detector = MinimalSignal()
        
        assert detector.signal_id == "minimal"
        assert detector.enabled is True
        assert detector.min_bars == 21
        assert detector.priority == 100
        assert detector.count_in_multi is True
    
    @pytest.mark.unit
    def test_detector_repr_and_str(self):
        """String representations should be meaningful."""
        class DisplaySignal(SignalDetector):
            signal_id = "display_test"
            display_name = "Display Test"
            icon = "🎯"
            
            def detect(self, hist, stock_info):
                return SignalResult(triggered=False)
        
        detector = DisplaySignal()
        
        assert "display_test" in repr(detector)
        assert "🎯" in str(detector)
        assert "Display Test" in str(detector)


# ─────────────────────────────────────────────────────────────────────────────
# SignalRegistry Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSignalRegistry:
    """Tests for SignalRegistry singleton."""
    
    @pytest.mark.unit
    def test_register_signal(self, clean_registry):
        """Should register signal via decorator."""
        @clean_registry.register
        class TestSignal(SignalDetector):
            signal_id = "registered_test"
            display_name = "Registered Test"
            icon = "✅"
            
            def detect(self, hist, stock_info):
                return SignalResult(triggered=False)
        
        assert "registered_test" in clean_registry.get_signal_ids()
    
    @pytest.mark.unit
    def test_register_without_signal_id_fails(self, clean_registry):
        """Registration without signal_id should raise."""
        with pytest.raises(ValueError, match="must define signal_id"):
            @clean_registry.register
            class NoIdSignal(SignalDetector):
                display_name = "No ID"
                
                def detect(self, hist, stock_info):
                    return SignalResult(triggered=False)
    
    @pytest.mark.unit
    def test_duplicate_signal_id_fails(self, clean_registry):
        """Duplicate signal_id should raise."""
        @clean_registry.register
        class FirstSignal(SignalDetector):
            signal_id = "duplicate_test"
            
            def detect(self, hist, stock_info):
                return SignalResult(triggered=False)
        
        with pytest.raises(ValueError, match="Duplicate signal_id"):
            @clean_registry.register
            class SecondSignal(SignalDetector):
                signal_id = "duplicate_test"
                
                def detect(self, hist, stock_info):
                    return SignalResult(triggered=False)
    
    @pytest.mark.unit
    def test_get_by_id(self, clean_registry):
        """Should retrieve signal by ID."""
        @clean_registry.register
        class LookupSignal(SignalDetector):
            signal_id = "lookup_test"
            display_name = "Lookup Test"
            
            def detect(self, hist, stock_info):
                return SignalResult(triggered=False)
        
        signal = clean_registry.get_by_id("lookup_test")
        
        assert signal is not None
        assert signal.signal_id == "lookup_test"
        assert signal.display_name == "Lookup Test"
    
    @pytest.mark.unit
    def test_get_by_id_not_found(self, clean_registry):
        """Non-existent ID should return None."""
        signal = clean_registry.get_by_id("nonexistent")
        assert signal is None
    
    @pytest.mark.unit
    def test_get_all_enabled_only(self, clean_registry):
        """get_all with enabled_only should filter disabled."""
        @clean_registry.register
        class EnabledSignal(SignalDetector):
            signal_id = "enabled_signal"
            enabled = True
            
            def detect(self, hist, stock_info):
                return SignalResult(triggered=False)
        
        @clean_registry.register
        class DisabledSignal(SignalDetector):
            signal_id = "disabled_signal"
            enabled = False
            
            def detect(self, hist, stock_info):
                return SignalResult(triggered=False)
        
        enabled_signals = clean_registry.get_all(enabled_only=True)
        all_signals = clean_registry.get_all(enabled_only=False)
        
        assert len(enabled_signals) == 1
        assert len(all_signals) == 2
        assert enabled_signals[0].signal_id == "enabled_signal"
    
    @pytest.mark.unit
    def test_get_all_sorted_by_priority(self, clean_registry):
        """Signals should be sorted by priority (lower first)."""
        @clean_registry.register
        class LowPrioritySignal(SignalDetector):
            signal_id = "low_priority"
            priority = 200
            
            def detect(self, hist, stock_info):
                return SignalResult(triggered=False)
        
        @clean_registry.register
        class HighPrioritySignal(SignalDetector):
            signal_id = "high_priority"
            priority = 10
            
            def detect(self, hist, stock_info):
                return SignalResult(triggered=False)
        
        signals = clean_registry.get_all(enabled_only=False)
        
        assert signals[0].signal_id == "high_priority"
        assert signals[1].signal_id == "low_priority"
    
    @pytest.mark.unit
    def test_get_by_group(self, clean_registry):
        """Should filter by signal group."""
        @clean_registry.register
        class PatternSignal(SignalDetector):
            signal_id = "pattern_signal"
            group = "pattern"
            
            def detect(self, hist, stock_info):
                return SignalResult(triggered=False)
        
        @clean_registry.register
        class VolumeSignal(SignalDetector):
            signal_id = "volume_signal"
            group = "volume"
            
            def detect(self, hist, stock_info):
                return SignalResult(triggered=False)
        
        pattern_signals = clean_registry.get_by_group("pattern")
        volume_signals = clean_registry.get_by_group("volume")
        
        assert len(pattern_signals) == 1
        assert len(volume_signals) == 1
        assert pattern_signals[0].signal_id == "pattern_signal"
    
    @pytest.mark.unit
    def test_get_icons(self, clean_registry):
        """Should return icon mapping."""
        @clean_registry.register
        class IconSignal(SignalDetector):
            signal_id = "icon_signal"
            icon = "🚀"
            
            def detect(self, hist, stock_info):
                return SignalResult(triggered=False)
        
        icons = clean_registry.get_icons()
        
        assert icons["icon_signal"] == "🚀"
    
    @pytest.mark.unit
    def test_get_names(self, clean_registry):
        """Should return display name mapping."""
        @clean_registry.register
        class NameSignal(SignalDetector):
            signal_id = "name_signal"
            display_name = "Name Signal Display"
            
            def detect(self, hist, stock_info):
                return SignalResult(triggered=False)
        
        names = clean_registry.get_names()
        
        assert names["name_signal"] == "Name Signal Display"
    
    @pytest.mark.unit
    def test_count(self, clean_registry):
        """Should return correct count."""
        assert clean_registry.count() == 0
        
        @clean_registry.register
        class CountSignal(SignalDetector):
            signal_id = "count_signal"
            
            def detect(self, hist, stock_info):
                return SignalResult(triggered=False)
        
        assert clean_registry.count() == 1
    
    @pytest.mark.unit
    def test_clear(self, clean_registry):
        """Clear should remove all signals."""
        @clean_registry.register
        class ClearSignal(SignalDetector):
            signal_id = "clear_signal"
            
            def detect(self, hist, stock_info):
                return SignalResult(triggered=False)
        
        assert clean_registry.count() == 1
        clean_registry.clear()
        assert clean_registry.count() == 0


# ─────────────────────────────────────────────────────────────────────────────
# Integration Tests - Signal Detection Flow
# ─────────────────────────────────────────────────────────────────────────────

class TestSignalDetectionFlow:
    """Integration tests for the signal detection workflow."""
    
    @pytest.mark.unit
    def test_full_detection_flow(self, clean_registry, sample_hist, sample_stock_info):
        """Test complete flow: register -> get -> detect."""
        @clean_registry.register
        class BreakoutSignal(SignalDetector):
            signal_id = "test_breakout"
            display_name = "Test Breakout"
            icon = "🚀"
            group = "pattern"
            min_bars = 20
            
            def detect(self, hist, stock_info):
                # Simple check: close > 50-day high
                closes = hist['收盘'].values
                if len(closes) < self.min_bars:
                    return SignalResult(triggered=False)
                
                current = closes[-1]
                previous_high = max(closes[:-1])
                
                if current > previous_high:
                    return SignalResult(
                        triggered=True,
                        metadata={
                            "breakout_pct": (current / previous_high - 1) * 100
                        }
                    )
                return SignalResult(triggered=False)
        
        # Get signal from registry
        signal = clean_registry.get_by_id("test_breakout")
        assert signal is not None
        
        # Run detection
        result = signal.detect(sample_hist, sample_stock_info)
        
        # Should trigger (trending up data)
        assert result.triggered is True
        assert "breakout_pct" in result.metadata
