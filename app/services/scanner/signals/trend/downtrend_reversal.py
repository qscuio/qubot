"""Downtrend Reversal Signal - Failed breakdown pattern."""

import numpy as np
from app.services.scanner.base import SignalDetector, SignalResult
from app.services.scanner.registry import SignalRegistry
from app.services.scanner.utils import detect_pivot_highs, calculate_atr


@SignalRegistry.register
class DowntrendReversalSignal(SignalDetector):
    """下降趋势反转信号 - 假跌破后收盘站回.
    
    核心逻辑：
    1. 确认下降趋势存在（使用 pivot_highs 连线）
    2. 检测趋势线附近的"资金反应"：
       - FAILED_BREAKDOWN（假跌破：盘中破位，收盘站回）
       - 阳线触碰后反弹
    3. 成交量验证：反转当根 vol_ratio > 1
    """
    
    signal_id = "downtrend_reversal"
    display_name = "下降趋势反转"
    icon = "🔄"
    group = "trend"
    min_bars = 30
    priority = 60
    
    def detect(self, hist, stock_info) -> SignalResult:
        try:
            if len(hist) < 30:
                return SignalResult(triggered=False)
            
            closes = hist['收盘'].values
            highs = hist['最高'].values
            lows = hist['最低'].values
            volumes = hist['成交量'].values
            opens = hist['开盘'].values
            
            # 1. Detect pivot highs
            pivot_highs = detect_pivot_highs(highs, 3, 3)
            
            if len(pivot_highs) < 2:
                return SignalResult(triggered=False)
            
            # 2. Check descending pattern
            recent_pivots = pivot_highs[-3:] if len(pivot_highs) >= 3 else pivot_highs[-2:]
            if len(recent_pivots) < 2:
                return SignalResult(triggered=False)
            
            for i in range(len(recent_pivots) - 1):
                if recent_pivots[i]['price'] <= recent_pivots[i+1]['price']:
                    return SignalResult(triggered=False)
            
            # 3. Calculate ATR and epsilon
            atr = calculate_atr(hist, 14)
            epsilon = atr * 0.7
            
            # 4. Calculate trend line value
            p1, p2 = recent_pivots[-2], recent_pivots[-1]
            if p2['idx'] == p1['idx']:
                return SignalResult(triggered=False)
            
            slope = (p2['price'] - p1['price']) / (p2['idx'] - p1['idx'])
            current_idx = len(hist) - 1
            line_value = p2['price'] + slope * (current_idx - p2['idx'])
            
            if line_value <= 0:
                return SignalResult(triggered=False)
            
            # 5. Check for failed breakdown
            today_low = lows[-1]
            today_close = closes[-1]
            today_open = opens[-1]
            
            # Pattern 1: Broke below then recovered
            broke_below = today_low < line_value - epsilon
            recovered = today_close > line_value
            
            if broke_below and recovered:
                vol_avg = np.mean(volumes[-21:-1]) if len(volumes) > 21 else np.mean(volumes[:-1])
                vol_ratio = volumes[-1] / vol_avg if vol_avg > 0 else 0
                if vol_ratio > 1.0:
                    return SignalResult(
                        triggered=True,
                        metadata={"vol_ratio": round(vol_ratio, 2), "pattern": "failed_breakdown"}
                    )
            
            # Pattern 2: Bullish touch and bounce
            touched_zone = abs(today_low - line_value) <= epsilon
            is_bullish = today_close > today_open
            yesterday_close = closes[-2] if len(closes) > 1 else closes[-1]
            price_up = today_close > yesterday_close
            
            if touched_zone and is_bullish and price_up:
                vol_avg = np.mean(volumes[-21:-1]) if len(volumes) > 21 else np.mean(volumes[:-1])
                vol_ratio = volumes[-1] / vol_avg if vol_avg > 0 else 0
                if vol_ratio > 1.0:
                    return SignalResult(
                        triggered=True,
                        metadata={"vol_ratio": round(vol_ratio, 2), "pattern": "bullish_bounce"}
                    )
            
            return SignalResult(triggered=False)
            
        except Exception:
            return SignalResult(triggered=False)
