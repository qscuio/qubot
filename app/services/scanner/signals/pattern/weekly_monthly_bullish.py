"""Weekly and Monthly Consecutive Bullish Signals."""

from app.services.scanner.base import SignalDetector, SignalResult
from app.services.scanner.registry import SignalRegistry
from app.services.scanner.utils import resample_to_weekly, resample_to_monthly


class ConsecutiveBullishBase(SignalDetector):
    """Base class for consecutive bullish patterns."""
    group = "pattern"
    
    def check_consecutive_bullish(self, hist, n_bars: int, check_low_position: bool = False) -> bool:
        """Check for N consecutive bullish bars.
        
        Args:
            hist: DataFrame (daily, weekly, or monthly)
            n_bars: Number of consecutive bullish bars required
            check_low_position: If True, check if starting from low position (below 20-period MA)
        """
        try:
            if len(hist) < n_bars + (20 if check_low_position else 0):
                return False
            
            # If checking low position, verify the first bar is below MA20
            if check_low_position:
                closes = hist['收盘']
                ma20 = closes.rolling(20).mean()
                # First bar of the pattern should be below MA20
                first_bar_idx = -(n_bars + 1)
                if closes.iloc[first_bar_idx] >= ma20.iloc[first_bar_idx]:
                    return False
            
            # Check last N bars are all bullish (close > open)
            for i in range(-n_bars, 0):
                bar = hist.iloc[i]
                if bar['收盘'] <= bar['开盘']:
                    return False
            
            return True
            
        except:
            return False


# ═══════════════════════════════════════════════════════════════════════════
# Weekly Signals
# ═══════════════════════════════════════════════════════════════════════════

@SignalRegistry.register
class LowWeekly2BullishSignal(ConsecutiveBullishBase):
    """低位周线两连阳 - 低位周线连续2根阳线."""
    
    signal_id = "low_weekly_2_bullish"
    display_name = "低位周线两连阳"
    icon = "📊"
    min_bars = 60  # Need enough daily data for weekly resampling and MA20
    priority = 60
    
    def detect(self, hist, stock_info) -> SignalResult:
        try:
            weekly = resample_to_weekly(hist)
            if len(weekly) < 22:  # Need 20 for MA + 2 for pattern
                return SignalResult(triggered=False)
            
            triggered = self.check_consecutive_bullish(weekly, 2, check_low_position=True)
            return SignalResult(triggered=triggered)
        except:
            return SignalResult(triggered=False)


@SignalRegistry.register
class Weekly3BullishSignal(ConsecutiveBullishBase):
    """低位周线三连阳 - 低位周线连续3根阳线."""
    
    signal_id = "weekly_3_bullish"
    display_name = "低位周线三连阳"
    icon = "📈"
    min_bars = 60  # Need enough daily data for weekly resampling and MA20
    priority = 61
    
    def detect(self, hist, stock_info) -> SignalResult:
        try:
            weekly = resample_to_weekly(hist)
            if len(weekly) < 23:  # Need 20 for MA + 3 for pattern
                return SignalResult(triggered=False)
            
            triggered = self.check_consecutive_bullish(weekly, 3, check_low_position=True)
            return SignalResult(triggered=triggered)
        except:
            return SignalResult(triggered=False)


@SignalRegistry.register
class Weekly4BullishSignal(ConsecutiveBullishBase):
    """低位周线四连阳 - 低位周线连续4根阳线."""
    
    signal_id = "weekly_4_bullish"
    display_name = "低位周线四连阳"
    icon = "🚀"
    min_bars = 70  # Need enough daily data for weekly resampling and MA20
    priority = 62
    
    def detect(self, hist, stock_info) -> SignalResult:
        try:
            weekly = resample_to_weekly(hist)
            if len(weekly) < 24:  # Need 20 for MA + 4 for pattern
                return SignalResult(triggered=False)
            
            triggered = self.check_consecutive_bullish(weekly, 4, check_low_position=True)
            return SignalResult(triggered=triggered)
        except:
            return SignalResult(triggered=False)


# ═══════════════════════════════════════════════════════════════════════════
# Monthly Signals
# ═══════════════════════════════════════════════════════════════════════════

@SignalRegistry.register
class LowMonthly2BullishSignal(ConsecutiveBullishBase):
    """低位月线两连阳 - 低位月线连续2根阳线."""
    
    signal_id = "low_monthly_2_bullish"
    display_name = "低位月线两连阳"
    icon = "📅"
    min_bars = 500  # Need enough daily data for monthly resampling and MA20
    priority = 63
    
    def detect(self, hist, stock_info) -> SignalResult:
        try:
            monthly = resample_to_monthly(hist)
            if len(monthly) < 22:  # Need 20 for MA + 2 for pattern
                return SignalResult(triggered=False)
            
            triggered = self.check_consecutive_bullish(monthly, 2, check_low_position=True)
            return SignalResult(triggered=triggered)
        except:
            return SignalResult(triggered=False)


@SignalRegistry.register
class Monthly3BullishSignal(ConsecutiveBullishBase):
    """低位月线3连阳 - 低位月线连续3根阳线."""
    
    signal_id = "monthly_3_bullish"
    display_name = "低位月线3连阳"
    icon = "🌙"
    min_bars = 600  # Need enough daily data for monthly resampling and MA20
    priority = 64
    
    def detect(self, hist, stock_info) -> SignalResult:
        try:
            monthly = resample_to_monthly(hist)
            if len(monthly) < 23:  # Need 20 for MA + 3 for pattern
                return SignalResult(triggered=False)
            
            triggered = self.check_consecutive_bullish(monthly, 3, check_low_position=True)
            return SignalResult(triggered=triggered)
        except:
            return SignalResult(triggered=False)


@SignalRegistry.register
class Monthly4BullishSignal(ConsecutiveBullishBase):
    """低位月线四连阳 - 低位月线连续4根阳线."""
    
    signal_id = "monthly_4_bullish"
    display_name = "低位月线四连阳"
    icon = "🌕"
    min_bars = 700  # Need enough daily data for monthly resampling and MA20
    priority = 65
    
    def detect(self, hist, stock_info) -> SignalResult:
        try:
            monthly = resample_to_monthly(hist)
            if len(monthly) < 24:  # Need 20 for MA + 4 for pattern
                return SignalResult(triggered=False)
            
            triggered = self.check_consecutive_bullish(monthly, 4, check_low_position=True)
            return SignalResult(triggered=triggered)
        except:
            return SignalResult(triggered=False)
