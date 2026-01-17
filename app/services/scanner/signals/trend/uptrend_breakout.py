"""Uptrend Breakout Signal - Breakout + pullback + confirmation."""

import numpy as np
from app.services.scanner.base import SignalDetector, SignalResult
from app.services.scanner.registry import SignalRegistry
from app.services.scanner.utils import detect_pivot_lows, calculate_atr


@SignalRegistry.register
class UptrendBreakoutSignal(SignalDetector):
    """上升趋势突破信号 - 突破 + 回踩确认.
    
    核心逻辑：
    1. 确认上升趋势存在（使用 pivot_lows 连线，递增）
    2. 趋势线上轨突破 + 回踩确认模式
    3. 成交量验证：突破放量，回踩缩量
    """
    
    signal_id = "uptrend_breakout"
    display_name = "上升趋势突破"
    icon = "🚀"
    group = "trend"
    min_bars = 30
    priority = 61
    
    def detect(self, hist, stock_info) -> SignalResult:
        try:
            if len(hist) < 30:
                return SignalResult(triggered=False)
            
            closes = hist['收盘'].values
            highs = hist['最高'].values
            lows = hist['最低'].values
            volumes = hist['成交量'].values
            
            # 1. Detect pivot lows
            pivot_lows = detect_pivot_lows(lows, 3, 3)
            
            if len(pivot_lows) < 2:
                return SignalResult(triggered=False)
            
            # 2. Check ascending pattern
            recent_pivots = pivot_lows[-3:] if len(pivot_lows) >= 3 else pivot_lows[-2:]
            if len(recent_pivots) < 2:
                return SignalResult(triggered=False)
            
            for i in range(len(recent_pivots) - 1):
                if recent_pivots[i]['price'] >= recent_pivots[i+1]['price']:
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
            
            # 5. Calculate upper rail (channel height)
            channel_heights = []
            for pl in recent_pivots:
                nearby_high = max(highs[max(0, pl['idx']-3):min(len(highs), pl['idx']+4)])
                channel_heights.append(nearby_high - pl['price'])
            
            channel_height = np.mean(channel_heights) if channel_heights else atr * 2
            upper_rail = line_value + channel_height
            
            # 6. Check breakout + pullback + confirmation
            vol_avg = np.mean(volumes[-21:-1]) if len(volumes) > 21 else np.mean(volumes[:-1])
            
            # Find breakout in last 5 bars
            breakout_bar = None
            for i in range(-5, -1):
                bar_close = closes[i]
                bar_vol_ratio = volumes[i] / vol_avg if vol_avg > 0 else 0
                if bar_close > upper_rail and bar_vol_ratio > 1.2:
                    breakout_bar = i
                    break
            
            if breakout_bar is None:
                return SignalResult(triggered=False)
            
            # Today: pullback + hold
            today_low = lows[-1]
            today_close = closes[-1]
            today_vol_ratio = volumes[-1] / vol_avg if vol_avg > 0 else 0
            
            # Pullback to zone
            pullback_to_zone = (abs(today_low - upper_rail) <= epsilon) or \
                              (today_low < upper_rail and today_low > line_value)
            
            # Shrink volume
            shrink_volume = today_vol_ratio < 1.0
            
            # Hold above
            held_above = today_close > upper_rail * 0.99
            
            if pullback_to_zone and shrink_volume and held_above:
                return SignalResult(
                    triggered=True,
                    metadata={
                        "breakout_bar": abs(breakout_bar),
                        "today_vol_ratio": round(today_vol_ratio, 2)
                    }
                )
            
            return SignalResult(triggered=False)
            
        except Exception:
            return SignalResult(triggered=False)
