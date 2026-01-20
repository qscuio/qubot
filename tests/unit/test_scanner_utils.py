"""
Unit tests for Scanner Utility Functions.

Tests pure calculation functions that don't require database access.
These are the core building blocks used by all signal detectors.
"""

import pytest
import numpy as np
import pandas as pd
from datetime import date, timedelta

from app.services.scanner.utils import (
    calculate_atr,
    calculate_obv,
    calculate_linreg_channel,
    detect_pivot_highs,
    detect_pivot_lows,
    calculate_position_in_range,
    calculate_volume_ratio,
    is_bullish_candle,
    is_bearish_candle,
    calculate_body_percent,
    calculate_daily_return,
    is_limit_up,
    resample_to_weekly,
    resample_to_monthly,
    calculate_ma,
    calculate_slope,
    calculate_mfi,
    calculate_cmf,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def simple_ohlcv_df():
    """Create a simple OHLCV DataFrame for testing."""
    dates = [date(2024, 1, i) for i in range(1, 22)]
    return pd.DataFrame({
        '日期': dates,
        '开盘': [10.0 + i * 0.1 for i in range(21)],
        '最高': [10.5 + i * 0.1 for i in range(21)],
        '最低': [9.5 + i * 0.1 for i in range(21)],
        '收盘': [10.2 + i * 0.1 for i in range(21)],
        '成交量': [100000 + i * 1000 for i in range(21)],
    })


@pytest.fixture
def trending_up_df():
    """Stock data with clear upward trend."""
    n = 30
    base = 10.0
    dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(n)]
    closes = [base + i * 0.5 for i in range(n)]  # Clear uptrend
    return pd.DataFrame({
        '日期': dates,
        '开盘': [c - 0.1 for c in closes],
        '最高': [c + 0.2 for c in closes],
        '最低': [c - 0.2 for c in closes],
        '收盘': closes,
        '成交量': [100000] * n,
    })


@pytest.fixture
def volatile_df():
    """Stock data with high volatility."""
    n = 20
    dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(n)]
    highs = [15.0, 12.0, 18.0, 10.0, 16.0] * 4
    lows = [8.0, 7.0, 10.0, 5.0, 9.0] * 4
    closes = [12.0, 9.0, 15.0, 7.0, 13.0] * 4
    opens = [10.0, 11.0, 12.0, 9.0, 8.0] * 4
    return pd.DataFrame({
        '日期': dates,
        '开盘': opens,
        '最高': highs,
        '最低': lows,
        '收盘': closes,
        '成交量': [200000, 150000, 300000, 100000, 250000] * 4,
    })


# ─────────────────────────────────────────────────────────────────────────────
# ATR Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestCalculateATR:
    """Tests for Average True Range calculation."""
    
    @pytest.mark.unit
    def test_atr_basic(self, simple_ohlcv_df):
        """ATR should return a positive value for valid data."""
        atr = calculate_atr(simple_ohlcv_df, period=14)
        assert atr > 0
        assert isinstance(atr, float)
    
    @pytest.mark.unit
    def test_atr_high_volatility(self, volatile_df):
        """ATR should be higher for volatile stocks."""
        atr_volatile = calculate_atr(volatile_df, period=14)
        # Volatile stock should have ATR > 2 given the price swings
        assert atr_volatile > 2.0
    
    @pytest.mark.unit
    def test_atr_insufficient_data(self):
        """ATR should return 0 for insufficient data."""
        df = pd.DataFrame({
            '最高': [10.0],
            '最低': [9.0],
            '收盘': [9.5],
        })
        atr = calculate_atr(df, period=14)
        assert atr == 0.0
    
    @pytest.mark.unit
    def test_atr_short_period(self, simple_ohlcv_df):
        """ATR with short period should still work."""
        atr = calculate_atr(simple_ohlcv_df, period=5)
        assert atr > 0


# ─────────────────────────────────────────────────────────────────────────────
# OBV Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestCalculateOBV:
    """Tests for On-Balance Volume calculation."""
    
    @pytest.mark.unit
    def test_obv_rising_prices(self):
        """OBV should increase when prices rise."""
        closes = np.array([10.0, 11.0, 12.0, 13.0, 14.0])
        volumes = np.array([100, 200, 300, 400, 500])
        
        obv = calculate_obv(closes, volumes)
        
        # OBV should be monotonically increasing
        assert all(obv[i] < obv[i+1] for i in range(len(obv)-1))
    
    @pytest.mark.unit
    def test_obv_falling_prices(self):
        """OBV should decrease when prices fall."""
        closes = np.array([14.0, 13.0, 12.0, 11.0, 10.0])
        volumes = np.array([100, 200, 300, 400, 500])
        
        obv = calculate_obv(closes, volumes)
        
        # OBV should be monotonically decreasing after first element
        assert all(obv[i] > obv[i+1] for i in range(len(obv)-1))
    
    @pytest.mark.unit
    def test_obv_flat_prices(self):
        """OBV should stay flat when prices don't change."""
        closes = np.array([10.0, 10.0, 10.0, 10.0])
        volumes = np.array([100, 200, 300, 400])
        
        obv = calculate_obv(closes, volumes)
        
        # All values should equal first volume
        assert all(obv[i] == 100 for i in range(len(obv)))
    
    @pytest.mark.unit
    def test_obv_length(self):
        """OBV should have same length as input."""
        closes = np.array([10.0, 11.0, 10.5, 12.0])
        volumes = np.array([100, 200, 150, 300])
        
        obv = calculate_obv(closes, volumes)
        
        assert len(obv) == len(closes)


# ─────────────────────────────────────────────────────────────────────────────
# Linear Regression Channel Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestCalculateLinregChannel:
    """Tests for Linear Regression Channel calculation."""
    
    @pytest.mark.unit
    def test_linreg_uptrend(self, trending_up_df):
        """Uptrend should have positive slope."""
        closes = trending_up_df['收盘']
        slope, mid, upper, lower = calculate_linreg_channel(closes, window=20)
        
        assert slope > 0
        assert upper >= mid >= lower
    
    @pytest.mark.unit
    def test_linreg_channel_bands(self, simple_ohlcv_df):
        """Upper should be above mid, lower below."""
        closes = simple_ohlcv_df['收盘']
        slope, mid, upper, lower = calculate_linreg_channel(closes, window=10)
        
        assert upper >= mid
        assert mid >= lower
    
    @pytest.mark.unit
    def test_linreg_insufficient_data(self):
        """Should return zeros for insufficient data."""
        closes = pd.Series([10.0, 11.0, 12.0])
        slope, mid, upper, lower = calculate_linreg_channel(closes, window=10)
        
        assert slope == 0.0
        assert mid == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Pivot Detection Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestPivotDetection:
    """Tests for pivot high/low detection."""
    
    @pytest.mark.unit
    def test_detect_pivot_high(self):
        """Should detect pivot high correctly."""
        # Pattern: 10, 11, 12, 15, 12, 11, 10 - pivot at index 3
        highs = np.array([10, 11, 12, 15, 12, 11, 10, 9, 8, 10])
        
        pivots = detect_pivot_highs(highs, left_bars=2, right_bars=2)
        
        assert len(pivots) >= 1
        assert any(p['idx'] == 3 for p in pivots)
        assert any(p['price'] == 15 for p in pivots)
    
    @pytest.mark.unit
    def test_detect_pivot_low(self):
        """Should detect pivot low correctly."""
        # Pattern: 15, 12, 10, 5, 10, 12, 15 - pivot at index 3
        lows = np.array([15, 12, 10, 5, 10, 12, 15, 16, 17, 15])
        
        pivots = detect_pivot_lows(lows, left_bars=2, right_bars=2)
        
        assert len(pivots) >= 1
        assert any(p['idx'] == 3 for p in pivots)
        assert any(p['price'] == 5 for p in pivots)
    
    @pytest.mark.unit
    def test_no_pivots_in_trend(self):
        """No pivots in pure trend."""
        # Monotonic increase - no pivot highs
        highs = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        
        pivots = detect_pivot_highs(highs, left_bars=2, right_bars=2)
        
        assert len(pivots) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Position in Range Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestPositionInRange:
    """Tests for position in range calculation."""
    
    @pytest.mark.unit
    def test_position_at_low(self):
        """Position at low should be 0."""
        pos = calculate_position_in_range(10.0, high=20.0, low=10.0)
        assert pos == 0.0
    
    @pytest.mark.unit
    def test_position_at_high(self):
        """Position at high should be 1."""
        pos = calculate_position_in_range(20.0, high=20.0, low=10.0)
        assert pos == 1.0
    
    @pytest.mark.unit
    def test_position_at_mid(self):
        """Position at midpoint should be 0.5."""
        pos = calculate_position_in_range(15.0, high=20.0, low=10.0)
        assert pos == 0.5
    
    @pytest.mark.unit
    def test_position_zero_range(self):
        """Zero range should return 0.5."""
        pos = calculate_position_in_range(10.0, high=10.0, low=10.0)
        assert pos == 0.5


# ─────────────────────────────────────────────────────────────────────────────
# Volume Ratio Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestVolumeRatio:
    """Tests for volume ratio calculation."""
    
    @pytest.mark.unit
    def test_volume_ratio_average(self):
        """Average volume should have ratio near 1."""
        volumes = np.array([100] * 25)
        ratio = calculate_volume_ratio(volumes, current_idx=-1, lookback=20)
        assert 0.9 <= ratio <= 1.1
    
    @pytest.mark.unit
    def test_volume_ratio_spike(self):
        """Volume spike should have ratio > 1."""
        volumes = np.array([100] * 20 + [500])  # Spike on last day
        ratio = calculate_volume_ratio(volumes, current_idx=-1, lookback=20)
        assert ratio > 4.0  # Should be ~5x
    
    @pytest.mark.unit
    def test_volume_ratio_low(self):
        """Low volume should have ratio < 1."""
        volumes = np.array([500] * 20 + [100])  # Drop on last day
        ratio = calculate_volume_ratio(volumes, current_idx=-1, lookback=20)
        assert ratio < 0.3  # Should be ~0.2x


# ─────────────────────────────────────────────────────────────────────────────
# Candle Pattern Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestCandlePatterns:
    """Tests for candle pattern functions."""
    
    @pytest.mark.unit
    def test_bullish_candle(self):
        """Close > Open is bullish."""
        assert is_bullish_candle(10.0, 11.0) is True
        assert is_bullish_candle(11.0, 10.0) is False
        assert is_bullish_candle(10.0, 10.0) is False
    
    @pytest.mark.unit
    def test_bearish_candle(self):
        """Close < Open is bearish."""
        assert is_bearish_candle(11.0, 10.0) is True
        assert is_bearish_candle(10.0, 11.0) is False
        assert is_bearish_candle(10.0, 10.0) is False
    
    @pytest.mark.unit
    def test_body_percent_positive(self):
        """Bullish candle has positive body percent."""
        pct = calculate_body_percent(10.0, 11.0)
        assert pct == 10.0  # 10% gain
    
    @pytest.mark.unit
    def test_body_percent_negative(self):
        """Bearish candle has negative body percent."""
        pct = calculate_body_percent(10.0, 9.0)
        assert pct == -10.0  # 10% loss
    
    @pytest.mark.unit
    def test_body_percent_zero_open(self):
        """Zero open price returns 0."""
        pct = calculate_body_percent(0.0, 10.0)
        assert pct == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Daily Return Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestDailyReturn:
    """Tests for daily return calculation."""
    
    @pytest.mark.unit
    def test_daily_return_gain(self):
        """Should calculate positive return."""
        ret = calculate_daily_return(100.0, 110.0)
        assert ret == 0.10  # 10%
    
    @pytest.mark.unit
    def test_daily_return_loss(self):
        """Should calculate negative return."""
        ret = calculate_daily_return(100.0, 90.0)
        assert ret == -0.10  # -10%
    
    @pytest.mark.unit
    def test_daily_return_zero_prev(self):
        """Zero prev_close returns 0."""
        ret = calculate_daily_return(0.0, 10.0)
        assert ret == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Limit Up Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestLimitUp:
    """Tests for limit up detection."""
    
    @pytest.mark.unit
    def test_limit_up_true(self):
        """Should detect limit up (>9.5% gain)."""
        # 10% gain is limit up
        assert is_limit_up(100.0, 110.0) is True
    
    @pytest.mark.unit
    def test_limit_up_borderline(self):
        """9.5% should be limit up, 9.4% should not."""
        assert is_limit_up(100.0, 109.6) is True  # 9.6% > 9.5%
        assert is_limit_up(100.0, 109.4) is False  # 9.4% < 9.5%
    
    @pytest.mark.unit
    def test_limit_up_custom_threshold(self):
        """Custom threshold should work."""
        # 20% gain with 15% threshold
        assert is_limit_up(100.0, 120.0, threshold=0.15) is True
        assert is_limit_up(100.0, 110.0, threshold=0.15) is False


# ─────────────────────────────────────────────────────────────────────────────
# Resampling Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestResampling:
    """Tests for data resampling functions."""
    
    @pytest.mark.unit
    def test_resample_to_weekly_reduces_rows(self, simple_ohlcv_df):
        """Weekly resampling should reduce row count."""
        weekly = resample_to_weekly(simple_ohlcv_df)
        assert len(weekly) < len(simple_ohlcv_df)
    
    @pytest.mark.unit
    def test_resample_to_weekly_aggregation(self, simple_ohlcv_df):
        """Weekly should use first open, last close, max high, min low."""
        weekly = resample_to_weekly(simple_ohlcv_df)
        
        # Check columns exist
        assert '开盘' in weekly.columns
        assert '收盘' in weekly.columns
        assert '最高' in weekly.columns
        assert '最低' in weekly.columns
        assert '成交量' in weekly.columns
    
    @pytest.mark.unit
    def test_resample_insufficient_data(self):
        """Should return original for insufficient data."""
        df = pd.DataFrame({
            '日期': [date(2024, 1, 1)],
            '开盘': [10.0],
            '收盘': [10.5],
            '最高': [11.0],
            '最低': [9.5],
            '成交量': [100000],
        })
        result = resample_to_weekly(df)
        assert len(result) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Moving Average Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestMovingAverage:
    """Tests for moving average calculation."""
    
    @pytest.mark.unit
    def test_ma_basic(self):
        """Basic MA calculation."""
        series = np.array([10.0, 11.0, 12.0, 13.0, 14.0])
        ma = calculate_ma(series, period=3)
        assert ma == 13.0  # avg of last 3: (12+13+14)/3
    
    @pytest.mark.unit
    def test_ma_insufficient_data(self):
        """MA with insufficient data returns 0."""
        series = np.array([10.0, 11.0])
        ma = calculate_ma(series, period=5)
        assert ma == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Slope Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSlope:
    """Tests for slope calculation."""
    
    @pytest.mark.unit
    def test_slope_uptrend(self):
        """Uptrend should have positive slope."""
        series = np.array([10.0, 11.0, 12.0, 13.0, 14.0])
        slope = calculate_slope(series, period=5)
        assert slope > 0
    
    @pytest.mark.unit
    def test_slope_downtrend(self):
        """Downtrend should have negative slope."""
        series = np.array([14.0, 13.0, 12.0, 11.0, 10.0])
        slope = calculate_slope(series, period=5)
        assert slope < 0
    
    @pytest.mark.unit
    def test_slope_flat(self):
        """Flat should have near-zero slope."""
        series = np.array([10.0, 10.0, 10.0, 10.0, 10.0])
        slope = calculate_slope(series, period=5)
        assert abs(slope) < 0.01


# ─────────────────────────────────────────────────────────────────────────────
# MFI Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestMFI:
    """Tests for Money Flow Index calculation."""
    
    @pytest.mark.unit
    def test_mfi_range(self):
        """MFI should be between 0 and 100."""
        n = 20
        highs = np.array([10.0 + i * 0.1 for i in range(n)])
        lows = np.array([9.0 + i * 0.1 for i in range(n)])
        closes = np.array([9.5 + i * 0.1 for i in range(n)])
        volumes = np.array([100000] * n)
        
        mfi = calculate_mfi(highs, lows, closes, volumes, period=14)
        
        assert 0 <= mfi <= 100
    
    @pytest.mark.unit
    def test_mfi_insufficient_data(self):
        """Insufficient data returns 50."""
        mfi = calculate_mfi(
            np.array([10.0]),
            np.array([9.0]),
            np.array([9.5]),
            np.array([100]),
            period=14
        )
        assert mfi == 50.0


# ─────────────────────────────────────────────────────────────────────────────
# CMF Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestCMF:
    """Tests for Chaikin Money Flow calculation."""
    
    @pytest.mark.unit
    def test_cmf_range(self):
        """CMF should be between -1 and 1."""
        n = 25
        highs = np.array([11.0] * n)
        lows = np.array([9.0] * n)
        closes = np.array([10.0] * n)  # Mid-range closes
        volumes = np.array([100000] * n)
        
        cmf = calculate_cmf(highs, lows, closes, volumes, period=20)
        
        assert -1 <= cmf <= 1
    
    @pytest.mark.unit
    def test_cmf_bullish(self):
        """Closes near highs should give positive CMF."""
        n = 25
        highs = np.array([11.0] * n)
        lows = np.array([9.0] * n)
        closes = np.array([10.9] * n)  # Close near high
        volumes = np.array([100000] * n)
        
        cmf = calculate_cmf(highs, lows, closes, volumes, period=20)
        
        assert cmf > 0.5
    
    @pytest.mark.unit
    def test_cmf_bearish(self):
        """Closes near lows should give negative CMF."""
        n = 25
        highs = np.array([11.0] * n)
        lows = np.array([9.0] * n)
        closes = np.array([9.1] * n)  # Close near low
        volumes = np.array([100000] * n)
        
        cmf = calculate_cmf(highs, lows, closes, volumes, period=20)
        
        assert cmf < -0.5
