"""Volume Surge Signal - Volume > 5-day average × 2."""

from app.services.scanner.base import SignalDetector, SignalResult
from app.services.scanner.registry import SignalRegistry


@SignalRegistry.register
class VolumeSurgeSignal(SignalDetector):
    """放量信号 - 成交量 > 5日均量的2倍."""
    
    signal_id = "volume"
    display_name = "放量信号"
    icon = "📊"
    group = "volume"
    min_bars = 10
    priority = 30
    
    def detect(self, hist, stock_info) -> SignalResult:
        try:
            vol_today = hist['成交量'].iloc[-1]
            vol_avg5 = hist['成交量'].iloc[-6:-1].mean()
            
            triggered = vol_today > vol_avg5 * 2
            
            if triggered:
                return SignalResult(
                    triggered=True,
                    metadata={"vol_ratio": round(vol_today / vol_avg5, 2) if vol_avg5 > 0 else 0}
                )
            
            return SignalResult(triggered=False)
            
        except Exception:
            return SignalResult(triggered=False)
