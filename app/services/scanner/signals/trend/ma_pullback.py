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
    
    def check_pullback(self, hist, window: int) -> bool:
        """Check for MA pullback pattern.
        
        Conditions:
        1. MA trend up (current MA > 5 days ago MA)
        2. Yesterday: bearish candle touching MA (low <= MA*1.01, close > MA)
        3. Today: bullish confirmation (close > open)
        """
        try:
            if len(hist) < window + 6:
                return False
            
            close = hist['收盘']
            ma = close.rolling(window).mean()
            
            ma_curr = ma.iloc[-1]
            ma_5ago = ma.iloc[-6]
            
            # MA trend up
            if ma_curr <= ma_5ago:
                return False
            
            # Yesterday's data
            yesterday = hist.iloc[-2]
            ma_yesterday = ma.iloc[-2]
            
            # Yesterday: bearish candle
            if yesterday['收盘'] >= yesterday['开盘']:
                return False
            
            # Yesterday: touched MA (low <= MA*1.01) but closed above
            if yesterday['最低'] > ma_yesterday * 1.01:
                return False
            if yesterday['收盘'] <= ma_yesterday:
                return False
            
            # Today: bullish confirmation
            today = hist.iloc[-1]
            if today['收盘'] <= today['开盘']:
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
            
            return SignalResult(triggered=self.check_pullback(weekly, 5))
            
        except Exception:
            return SignalResult(triggered=False)
