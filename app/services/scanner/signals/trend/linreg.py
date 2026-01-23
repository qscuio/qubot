"""Linear Regression Channel Signals - Support and Breakout."""

import pandas as pd

from app.services.scanner.base import SignalDetector, SignalResult
from app.services.scanner.registry import SignalRegistry
from app.services.scanner.utils import calculate_linreg_channel, calculate_atr


class LinRegSupportBase(SignalDetector):
    """Base class for linreg support signals."""
    
    group = "trend"
    count_in_multi = True
    
    def check_support(self, hist, window: int) -> bool:
        """Check for support at lower rail of linreg channel.
        
        Conditions:
        1. Trend is UP (slope > 0)
        2. Low touched lower rail (ATR-adjusted)
        3. Close held above lower rail (ATR-adjusted)
        4. Pullback volume not expanding (optional)
        """
        try:
            if len(hist) < window + 2:
                return False
            
            close_series = hist['收盘']
            slope, mid, upper, lower = calculate_linreg_channel(close_series, window)
            
            # Trend must be rising
            if slope <= 0:
                return False
            
            atr = calculate_atr(hist, 14)
            if atr <= 0:
                return False

            # Today's data
            low_curr = hist['最低'].iloc[-1]
            close_curr = hist['收盘'].iloc[-1]
            volumes = hist['成交量']
            vol_curr = volumes.iloc[-1]
            
            # Touch support (low near or below lower rail) with ATR tolerance
            if low_curr > lower + 0.6 * atr:
                return False
            
            # Hold support (close above lower rail)
            if close_curr < lower - 0.3 * atr:
                return False

            # Optional: avoid distribution day on support touch
            if len(volumes) >= 11:
                vol_ma10 = volumes.iloc[-10:].mean()
                if vol_ma10 > 0 and vol_curr > vol_ma10 * 1.6:
                    return False

            # Optional: ensure short-term trend is still rising
            if len(hist) >= 25:
                ma20 = hist['收盘'].rolling(20).mean()
                ma20_curr = ma20.iloc[-1]
                ma20_5ago = ma20.iloc[-6]
                if not (pd.isna(ma20_curr) or pd.isna(ma20_5ago)) and ma20_curr <= ma20_5ago:
                    return False
            
            return True
            
        except Exception:
            return False


class LinRegBreakoutBase(SignalDetector):
    """Base class for linreg breakout signals."""
    
    group = "trend"
    count_in_multi = True
    
    def check_breakout(self, hist, window: int) -> bool:
        """Check for breakout above upper rail.
        
        Conditions:
        1. Trend is UP (slope > 0)
        2. Close > Upper rail (ATR-adjusted)
        3. Volume expansion vs recent average
        """
        try:
            if len(hist) < window + 2:
                return False
            
            close_series = hist['收盘']
            slope, mid, upper, lower = calculate_linreg_channel(close_series, window)
            
            # Trend must be rising
            if slope <= 0:
                return False
            
            atr = calculate_atr(hist, 14)
            if atr <= 0:
                return False

            # Breakout
            close_curr = hist['收盘'].iloc[-1]
            close_prev = hist['收盘'].iloc[-2]

            if close_curr <= upper + 0.2 * atr:
                return False

            # Ensure this is a fresh breakout (prev close not already above rail)
            prev_series = close_series.iloc[:-1]
            if len(prev_series) >= window:
                _, _, upper_prev, _ = calculate_linreg_channel(prev_series, window)
                if close_prev > upper_prev + 0.1 * atr:
                    return False

            # Volume confirmation
            volumes = hist['成交量']
            if len(volumes) >= 6:
                vol_ma5 = volumes.iloc[-6:-1].mean()
                if vol_ma5 > 0 and volumes.iloc[-1] <= vol_ma5 * 1.2:
                    return False

            # Optional: ensure MA20 still rising
            if len(hist) >= 25:
                ma20 = hist['收盘'].rolling(20).mean()
                ma20_curr = ma20.iloc[-1]
                ma20_5ago = ma20.iloc[-6]
                if not (pd.isna(ma20_curr) or pd.isna(ma20_5ago)) and ma20_curr <= ma20_5ago:
                    return False

            return True
            
        except Exception:
            return False


# Support signals
@SignalRegistry.register
class LinRegSupport5Signal(LinRegSupportBase):
    signal_id = "support_linreg_5"
    display_name = "5日趋势支撑"
    icon = "📉"
    min_bars = 10
    priority = 50
    
    def detect(self, hist, stock_info) -> SignalResult:
        return SignalResult(triggered=self.check_support(hist, 5))


@SignalRegistry.register
class LinRegSupport10Signal(LinRegSupportBase):
    signal_id = "support_linreg_10"
    display_name = "10日趋势支撑"
    icon = "📉"
    min_bars = 15
    priority = 51
    
    def detect(self, hist, stock_info) -> SignalResult:
        return SignalResult(triggered=self.check_support(hist, 10))


@SignalRegistry.register
class LinRegSupport20Signal(LinRegSupportBase):
    signal_id = "support_linreg_20"
    display_name = "20日趋势支撑"
    icon = "📉"
    min_bars = 25
    priority = 52
    
    def detect(self, hist, stock_info) -> SignalResult:
        return SignalResult(triggered=self.check_support(hist, 20))


# Breakout signals
@SignalRegistry.register
class LinRegBreakout5Signal(LinRegBreakoutBase):
    signal_id = "breakout_linreg_5"
    display_name = "突破5日趋势"
    icon = "🔼"
    min_bars = 10
    priority = 53
    
    def detect(self, hist, stock_info) -> SignalResult:
        return SignalResult(triggered=self.check_breakout(hist, 5))


@SignalRegistry.register
class LinRegBreakout10Signal(LinRegBreakoutBase):
    signal_id = "breakout_linreg_10"
    display_name = "突破10日趋势"
    icon = "🔼"
    min_bars = 15
    priority = 54
    
    def detect(self, hist, stock_info) -> SignalResult:
        return SignalResult(triggered=self.check_breakout(hist, 10))


@SignalRegistry.register
class LinRegBreakout20Signal(LinRegBreakoutBase):
    signal_id = "breakout_linreg_20"
    display_name = "突破20日趋势"
    icon = "🔼"
    min_bars = 25
    priority = 55
    
    def detect(self, hist, stock_info) -> SignalResult:
        return SignalResult(triggered=self.check_breakout(hist, 20))
