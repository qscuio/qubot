"""Breakout Signal - Price breaks 20-day high."""

from app.services.scanner.base import SignalDetector, SignalResult
from app.services.scanner.registry import SignalRegistry


@SignalRegistry.register
class BreakoutSignal(SignalDetector):
    """突破信号 - 收盘价创20日新高."""
    
    signal_id = "breakout"
    display_name = "突破信号"
    icon = "🔺"
    group = "momentum"
    min_bars = 21
    priority = 10
    
    def detect(self, hist, stock_info) -> SignalResult:
        try:
            close = hist['收盘'].iloc[-1]
            high_20 = hist['最高'].iloc[:-1].max()
            return SignalResult(triggered=close > high_20)
        except Exception:
            return SignalResult(triggered=False)
