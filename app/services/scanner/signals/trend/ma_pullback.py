"""MA Pullback Signals - Pullback to MA with confirmation."""

import pandas as pd
from app.services.scanner.base import SignalDetector, SignalResult
from app.services.scanner.registry import SignalRegistry
from app.services.scanner.utils import resample_to_weekly


class MAPullbackBase(SignalDetector):
    """Base class for MA pullback signals."""
    
    group = "trend"
    count_in_multi = True
    
    def __init__(self):
        self.ma_window = 5  # Override in subclasses
    
    def _get_tolerances(self, window: int, weekly: bool) -> tuple:
        # Tolerances are conservative to avoid signals far from the MA.
        if weekly:
            return 0.02, 0.06  # (touch_tol, close_max_bias)
        if window <= 5:
            return 0.012, 0.03
        if window <= 20:
            return 0.015, 0.04
        return 0.02, 0.05

    def _get_pullback_body_limit(self, window: int, weekly: bool) -> float:
        # Max body percent for doji/small bullish pullback candle.
        if weekly:
            return 1.2
        if window <= 5:
            return 0.6
        if window <= 20:
            return 0.8
        return 1.0

    def check_pullback(self, hist, window: int, weekly: bool = False) -> bool:
        """Check for MA pullback pattern.
        
        Conditions:
        1. MA trend up (current MA > 5 bars ago MA)
        2. Pullback day (yesterday): bearish OR doji/small bullish candle
           touching MA, close >= MA, and close not too far above MA.
        3. Today: bullish confirmation, close not too far above MA.
        4. Price was above MA before the pullback (avoid breakdowns).
        """
        try:
            if len(hist) < window + 6:
                return False
            
            close = hist['收盘']
            ma = close.rolling(window).mean()
            
            ma_curr = ma.iloc[-1]
            ma_5ago = ma.iloc[-6]
            if pd.isna(ma_curr) or pd.isna(ma_5ago) or ma_curr <= 0:
                return False

            touch_tol, close_max_bias = self._get_tolerances(window, weekly)
            pullback_body_limit = self._get_pullback_body_limit(window, weekly)
            
            # MA trend up
            if ma_curr <= ma_5ago:
                return False
            
            # Yesterday's data
            yesterday = hist.iloc[-2]
            ma_yesterday = ma.iloc[-2]
            if pd.isna(ma_yesterday) or ma_yesterday <= 0:
                return False
            
            # Yesterday: bearish or doji/small bullish candle
            y_open = yesterday['开盘']
            y_close = yesterday['收盘']
            if y_open <= 0:
                return False
            body_pct = abs((y_close - y_open) / y_open * 100)
            is_small_bull = y_close >= y_open and body_pct <= pullback_body_limit
            if not (y_close < y_open or is_small_bull):
                return False
            
            # Yesterday: touched MA (low <= MA*1.01) but closed above
            if abs(yesterday['最低'] - ma_yesterday) / ma_yesterday > touch_tol:
                return False
            if yesterday['收盘'] <= ma_yesterday:
                return False
            if yesterday['收盘'] > ma_yesterday * (1 + close_max_bias):
                return False

            # Ensure pullback came from above MA (avoid prolonged below-MA moves)
            prev = hist.iloc[-3]
            ma_prev = ma.iloc[-3]
            if not pd.isna(ma_prev) and prev['收盘'] < ma_prev:
                return False
            
            # Today: bullish confirmation
            today = hist.iloc[-1]
            if today['收盘'] <= today['开盘']:
                return False
            if today['收盘'] > ma_curr * (1 + close_max_bias):
                return False
            
            return True
            
        except Exception:
            return False


@SignalRegistry.register
class MAPullbackMA5Signal(MAPullbackBase):
    """5日线回踩信号."""
    
    signal_id = "pullback_ma5"
    display_name = "5日线回踩"
    icon = "↩️"
    min_bars = 15
    priority = 45
    
    def detect(self, hist, stock_info) -> SignalResult:
        return SignalResult(triggered=self.check_pullback(hist, 5))


@SignalRegistry.register
class MAPullbackMA20Signal(MAPullbackBase):
    """20日线回踩信号."""
    
    signal_id = "pullback_ma20"
    display_name = "20日线回踩"
    icon = "↩️"
    min_bars = 30
    priority = 46
    
    def detect(self, hist, stock_info) -> SignalResult:
        return SignalResult(triggered=self.check_pullback(hist, 20))


@SignalRegistry.register
class MAPullbackMA30Signal(MAPullbackBase):
    """30日线回踩信号."""
    
    signal_id = "pullback_ma30"
    display_name = "30日线回踩"
    icon = "↩️"
    min_bars = 40
    priority = 47
    
    def detect(self, hist, stock_info) -> SignalResult:
        return SignalResult(triggered=self.check_pullback(hist, 30))


@SignalRegistry.register
class MAPullbackMA5WeeklySignal(MAPullbackBase):
    """周线5周线回踩信号."""
    
    signal_id = "pullback_ma5_weekly"
    display_name = "5周线回踩"
    icon = "↩️"
    min_bars = 40  # Need enough daily data to form weekly
    priority = 48
    
    def detect(self, hist, stock_info) -> SignalResult:
        try:
            # Resample to weekly
            weekly = resample_to_weekly(hist)
            if len(weekly) < 10:
                return SignalResult(triggered=False)
            
            return SignalResult(triggered=self.check_pullback(weekly, 5, weekly=True))
            
        except Exception:
            return SignalResult(triggered=False)
