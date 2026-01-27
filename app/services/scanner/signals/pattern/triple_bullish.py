"""Triple Bullish Shrink Breakout Signal - 三阳一缩一放."""

from app.services.scanner.base import SignalDetector, SignalResult
from app.services.scanner.registry import SignalRegistry
from app.services.scanner.utils import is_bullish_candle, calculate_body_percent, scale_pct


@SignalRegistry.register
class TripleBullishShrinkBreakoutSignal(SignalDetector):
    """三阳一缩一放信号.
    
    模式:
    1. T-4 到 T-2 (3天): 连续小阳线 (0.5% < 实体 < 4%)
    2. T-1 (1天): 缩量小阴或十字星 (Vol < T-2 Vol)
    3. T (今日): 放量实体突破 (Vol > T-1 Vol * 1.5, 收盘 > T-1最高, 实体饱满)
    """
    
    signal_id = "triple_bullish_shrink_breakout"
    display_name = "蓄势爆发"
    icon = "🔥"
    group = "pattern"
    min_bars = 10
    priority = 85
    
    def detect(self, hist, stock_info) -> SignalResult:
        try:
            if len(hist) < 5:
                return SignalResult(triggered=False)
            
            # Get last 5 days
            t_4 = hist.iloc[-5]
            t_3 = hist.iloc[-4]
            t_2 = hist.iloc[-3]
            t_1 = hist.iloc[-2]  # Yesterday
            t_0 = hist.iloc[-1]  # Today
            
            # 1. T-4 to T-2: small bullish (0.5% < body < 4%, board-aware)
            code = stock_info.get("code")
            name = stock_info.get("name")
            min_body = scale_pct(0.5, code, name)
            max_body = scale_pct(4.0, code, name)
            for bar in [t_4, t_3, t_2]:
                body_pct = calculate_body_percent(bar['开盘'], bar['收盘'])
                if not (min_body < body_pct < max_body):
                    return SignalResult(triggered=False)
            
            # 2. T-1: shrink volume (Vol < T-2 Vol)
            if t_1['成交量'] >= t_2['成交量']:
                return SignalResult(triggered=False)
            
            # 3. Today: volume breakout
            # Vol > T-1 Vol * 1.5
            if t_0['成交量'] <= t_1['成交量'] * 1.5:
                return SignalResult(triggered=False)
            
            # Close > T-1 High
            if t_0['收盘'] <= t_1['最高']:
                return SignalResult(triggered=False)
            
            # Solid body (body/range > 0.6)
            body = abs(t_0['收盘'] - t_0['开盘'])
            range_today = t_0['最高'] - t_0['最低']
            if range_today > 0 and body / range_today < 0.6:
                return SignalResult(triggered=False)
            
            vol_ratio = t_0['成交量'] / t_1['成交量'] if t_1['成交量'] > 0 else 0
            
            return SignalResult(
                triggered=True,
                metadata={"vol_ratio": round(vol_ratio, 2)}
            )
            
        except Exception:
            return SignalResult(triggered=False)
