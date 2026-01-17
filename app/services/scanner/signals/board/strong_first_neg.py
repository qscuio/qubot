"""Strong First Negative Signal - Strong stock's first bearish day."""

import numpy as np
from app.services.scanner.base import SignalDetector, SignalResult
from app.services.scanner.registry import SignalRegistry
from app.services.scanner.utils import is_bullish_candle, is_bearish_candle


@SignalRegistry.register
class StrongFirstNegativeSignal(SignalDetector):
    """强势股首阴信号.
    
    条件:
    1. 强势: 近20日涨幅 > 30%
    2. 首阴: 昨日(T-1)是阳线, 今日(T)是阴线
    """
    
    signal_id = "strong_first_negative"
    display_name = "强势首阴"
    icon = "⚡"
    group = "board"
    min_bars = 21
    priority = 93
    
    def detect(self, hist, stock_info) -> SignalResult:
        try:
            if len(hist) < 21:
                return SignalResult(triggered=False)
            
            closes = hist['收盘'].values
            opens = hist['开盘'].values
            
            # 1. Strong: 20-day gain > 30%
            close_20_ago = closes[-21]
            close_today = closes[-1]
            gain_20d = (close_today - close_20_ago) / close_20_ago
            
            if gain_20d <= 0.30:
                return SignalResult(triggered=False)
            
            # 2. Yesterday: bullish
            if not is_bullish_candle(opens[-2], closes[-2]):
                return SignalResult(triggered=False)
            
            # 3. Today: bearish (first negative)
            if not is_bearish_candle(opens[-1], closes[-1]):
                return SignalResult(triggered=False)
            
            return SignalResult(
                triggered=True,
                metadata={"gain_20d_pct": round(gain_20d * 100, 2)}
            )
            
        except Exception:
            return SignalResult(triggered=False)
