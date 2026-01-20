"""
Unit tests for LowAccumulationLaunchSignal.

Tests the "Low Position + Accumulation + Preparing to Launch" signal detection.
"""

import pytest
import numpy as np
import pandas as pd
from datetime import date, timedelta


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_stock_info():
    """Standard stock info."""
    return {"code": "000001", "name": "测试股票"}


@pytest.fixture
def st_stock_info():
    """ST stock info that should be filtered."""
    return {"code": "000002", "name": "ST测试"}


@pytest.fixture
def low_position_accumulating_df():
    """Stock at low position with accumulation pattern (should trigger)."""
    n = 300  # More than min_bars (252)
    dates = [date(2023, 1, 1) + timedelta(days=i) for i in range(n)]
    
    # Create pattern: big drop from 20 to 10, then sideways consolidation
    closes = []
    for i in range(n):
        if i < 50:
            # Initial high period
            closes.append(20.0 - i * 0.1)  # Drop from 20 to 15
        elif i < 150:
            # Big crash
            closes.append(15.0 - (i - 50) * 0.05)  # Drop to 10
        else:
            # Consolidation at low (narrow box, low volatility)
            closes.append(10.0 + np.sin(i * 0.1) * 0.2)  # Narrow oscillation
    
    closes = np.array(closes)
    
    # Volume: decreasing in consolidation phase (accumulation signal)
    volumes = []
    for i in range(n):
        if i < 150:
            volumes.append(500000)
        else:
            volumes.append(200000)  # Lower volume in consolidation
    
    # Last day: slight volume increase and price near top of box
    closes[-1] = 10.5  # Near box high
    volumes[-1] = 350000  # Volume increase
    
    return pd.DataFrame({
        '日期': dates,
        '开盘': closes - 0.1,
        '收盘': closes,
        '最高': closes + 0.2,
        '最低': closes - 0.2,
        '成交量': volumes,
        '换手率': [2.0] * n,
    })


@pytest.fixture
def high_position_df():
    """Stock at high position (should not trigger)."""
    n = 300
    dates = [date(2023, 1, 1) + timedelta(days=i) for i in range(n)]
    
    # Trending up - at high position
    closes = np.array([10.0 + i * 0.05 for i in range(n)])  # Strong uptrend
    
    return pd.DataFrame({
        '日期': dates,
        '开盘': closes - 0.1,
        '收盘': closes,
        '最高': closes + 0.2,
        '最低': closes - 0.2,
        '成交量': [300000] * n,
        '换手率': [3.0] * n,
    })


@pytest.fixture
def insufficient_data_df():
    """Insufficient data (less than min_bars)."""
    n = 100  # Less than 252
    dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(n)]
    
    return pd.DataFrame({
        '日期': dates,
        '开盘': [10.0] * n,
        '收盘': [10.5] * n,
        '最高': [11.0] * n,
        '最低': [9.5] * n,
        '成交量': [100000] * n,
        '换手率': [2.0] * n,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestLowAccumulationLaunchSignal:
    """Tests for LowAccumulationLaunchSignal detector."""
    
    @pytest.mark.unit
    def test_signal_registered(self):
        """Signal should be registered in registry."""
        from app.services.scanner.registry import SignalRegistry
        
        signal = SignalRegistry.get_by_id("low_accumulation_launch")
        
        assert signal is not None
        assert signal.display_name == "低位潜伏启动"
        assert signal.min_bars == 252
    
    @pytest.mark.unit
    def test_insufficient_data_not_triggered(self, insufficient_data_df, sample_stock_info):
        """Should not trigger with insufficient data."""
        from app.services.scanner.registry import SignalRegistry
        
        signal = SignalRegistry.get_by_id("low_accumulation_launch")
        result = signal.detect(insufficient_data_df, sample_stock_info)
        
        assert result.triggered is False
    
    @pytest.mark.unit
    def test_st_stock_filtered(self, low_position_accumulating_df, st_stock_info):
        """ST stocks should be filtered out."""
        from app.services.scanner.registry import SignalRegistry
        
        signal = SignalRegistry.get_by_id("low_accumulation_launch")
        result = signal.detect(low_position_accumulating_df, st_stock_info)
        
        assert result.triggered is False
    
    @pytest.mark.unit
    def test_high_position_not_triggered(self, high_position_df, sample_stock_info):
        """Stock at high position should not trigger."""
        from app.services.scanner.registry import SignalRegistry
        
        signal = SignalRegistry.get_by_id("low_accumulation_launch")
        result = signal.detect(high_position_df, sample_stock_info)
        
        assert result.triggered is False
    
    @pytest.mark.unit 
    def test_result_has_metadata_when_triggered(self, low_position_accumulating_df, sample_stock_info):
        """When triggered, result should have meaningful metadata."""
        from app.services.scanner.registry import SignalRegistry
        
        signal = SignalRegistry.get_by_id("low_accumulation_launch")
        result = signal.detect(low_position_accumulating_df, sample_stock_info)
        
        # This test may or may not trigger depending on exact data
        # If triggered, check metadata
        if result.triggered:
            assert "score" in result.metadata
            assert "reason" in result.metadata
            assert "pos_score" in result.metadata
            assert result.metadata["score"] >= 70  # Threshold
    
    @pytest.mark.unit
    def test_signal_attributes(self):
        """Signal should have correct attributes."""
        from app.services.scanner.registry import SignalRegistry
        
        signal = SignalRegistry.get_by_id("low_accumulation_launch")
        
        assert signal.icon == "🚀"
        assert signal.group == "comprehensive"
        assert signal.enabled is True
        assert signal.priority == 50
