"""Kuangbiao Signal - Two-stage scoring momentum signal."""

from app.services.scanner.base import SignalDetector, SignalResult
from app.services.scanner.registry import SignalRegistry
from app.services.scanner_utils import calculate_kuangbiao_score


@SignalRegistry.register
class KuangbiaoSignal(SignalDetector):
    """狂飙信号 - 两阶段评分动量信号."""
    
    signal_id = "kuangbiao"
    display_name = "狂飙启动"
    icon = "🏎️"
    group = "momentum"
    min_bars = 21
    priority = 15
    
    def detect(self, hist, stock_info) -> SignalResult:
        try:
            # Use the existing scoring function
            score_a, score_b = calculate_kuangbiao_score(hist, stock_info)
            
            # Thresholds for triggering
            if score_a >= 60 and score_b >= 50:
                return SignalResult(
                    triggered=True,
                    metadata={
                        "score_a": score_a,
                        "score_b": score_b,
                        "total_score": score_a + score_b
                    }
                )
            
            return SignalResult(triggered=False)
            
        except Exception:
            return SignalResult(triggered=False)
