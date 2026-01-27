"""Slow Bull Signals - Consecutive higher closes with limited gain."""

from app.services.scanner.base import SignalDetector, SignalResult
from app.services.scanner.registry import SignalRegistry
from app.services.scanner.utils import scale_pct


class SlowBullBase(SignalDetector):
    """Base class for slow bull patterns."""
    group = "pattern"
    
    def check_slow_bull(self, hist, days: int, max_gain: float = 0.20) -> bool:
        """Check for slow bull pattern.
        
        Args:
            hist: DataFrame
            days: Number of consecutive days
            max_gain: Maximum total gain (0.20 = 20%)
        """
        try:
            if len(hist) < days + 1:
                return False
            
            closes = hist['收盘'].values
            recent = closes[-(days+1):]
            
            # Check consecutive higher closes
            for i in range(1, len(recent)):
                if recent[i] <= recent[i-1]:
                    return False
            
            # Check total gain <= max_gain
            total_gain = (recent[-1] - recent[0]) / recent[0]
            return total_gain <= max_gain
            
        except:
            return False


@SignalRegistry.register
class SlowBull7Signal(SlowBullBase):
    """7天慢牛信号 - 连续7天收盘价上涨，总涨幅≤20%."""
    
    signal_id = "slow_bull_7"
    display_name = "7天慢牛"
    icon = "🐂"
    min_bars = 10
    priority = 80
    
    def detect(self, hist, stock_info) -> SignalResult:
        code = stock_info.get("code")
        name = stock_info.get("name")
        max_gain = scale_pct(0.20, code, name)
        triggered = self.check_slow_bull(hist, 7, max_gain=max_gain)
        if triggered:
            closes = hist['收盘'].values
            gain = (closes[-1] - closes[-8]) / closes[-8] * 100
            return SignalResult(triggered=True, metadata={"gain_pct": round(gain, 2)})
        return SignalResult(triggered=False)


@SignalRegistry.register
class SlowBull5Signal(SlowBullBase):
    """5天慢牛信号 - 连续5天收盘价上涨，总涨幅≤20%."""
    
    signal_id = "slow_bull_5"
    display_name = "5天慢牛"
    icon = "🐂"
    min_bars = 8
    priority = 81
    
    def detect(self, hist, stock_info) -> SignalResult:
        code = stock_info.get("code")
        name = stock_info.get("name")
        max_gain = scale_pct(0.20, code, name)
        triggered = self.check_slow_bull(hist, 5, max_gain=max_gain)
        if triggered:
            closes = hist['收盘'].values
            gain = (closes[-1] - closes[-6]) / closes[-6] * 100
            return SignalResult(triggered=True, metadata={"gain_pct": round(gain, 2)})
        return SignalResult(triggered=False)
