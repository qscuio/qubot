"""MA Bullish Signal - MA5 > MA10 > MA20 with golden cross."""

from app.services.scanner.base import SignalDetector, SignalResult
from app.services.scanner.registry import SignalRegistry


@SignalRegistry.register
class MABullishSignal(SignalDetector):
    """多头排列信号 - MA5 > MA10 > MA20 且金叉."""
    
    signal_id = "ma_bullish"
    display_name = "多头排列"
    icon = "📈"
    group = "trend"
    min_bars = 21
    priority = 40
    
    def detect(self, hist, stock_info) -> SignalResult:
        try:
            close = hist['收盘']
            
            ma5 = close.rolling(5).mean().iloc[-1]
            ma10 = close.rolling(10).mean().iloc[-1]
            ma20 = close.rolling(20).mean().iloc[-1]
            
            # Check for golden cross (MA5 crossed above MA10 today)
            ma5_prev = close.rolling(5).mean().iloc[-2]
            ma10_prev = close.rolling(10).mean().iloc[-2]
            
            bullish = ma5 > ma10 > ma20
            golden_cross = ma5 > ma10 and ma5_prev <= ma10_prev
            
            return SignalResult(triggered=bullish and golden_cross)
            
        except Exception:
            return SignalResult(triggered=False)
