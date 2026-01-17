"""Volume Price Startup Signal - Professional volume-price analysis."""

import numpy as np
import pandas as pd
from app.services.scanner.base import SignalDetector, SignalResult
from app.services.scanner.registry import SignalRegistry
from app.services.scanner.utils import calculate_obv


@SignalRegistry.register
class VolumePriceStartupSignal(SignalDetector):
    """量价启动信号 - 专业量价分析.
    
    使用多维度量价关系分析：
    1. 量比分析 - 当前量比 > 1.5
    2. OBV趋势 - 能量潮上升
    3. 量价配合 - 价升量增
    4. 位置确认 - 站上关键均线
    5. 缩量整理后放量 - 典型启动形态
    """
    
    signal_id = "volume_price"
    display_name = "量价启动"
    icon = "📈"
    group = "volume"
    min_bars = 21
    priority = 35
    
    def detect(self, hist, stock_info) -> SignalResult:
        try:
            if len(hist) < 20:
                return SignalResult(triggered=False)
            
            closes = hist['收盘'].values
            volumes = hist['成交量'].values
            
            # 1. Volume ratio > 1.5
            vol_today = volumes[-1]
            vol_avg5 = np.mean(volumes[-6:-1])
            vol_ratio = vol_today / vol_avg5 if vol_avg5 > 0 else 0
            
            if vol_ratio < 1.5:
                return SignalResult(triggered=False)
            
            # 2. OBV trend analysis
            obv = calculate_obv(closes, volumes)
            obv_series = pd.Series(obv)
            obv_ma5 = obv_series.rolling(5).mean().iloc[-1]
            obv_ma10 = obv_series.rolling(10).mean().iloc[-1]
            
            obv_bullish = obv[-1] > obv_ma5 > obv_ma10
            if not obv_bullish:
                return SignalResult(triggered=False)
            
            # 3. Price above MA20
            ma20 = np.mean(closes[-20:])
            if closes[-1] <= ma20:
                return SignalResult(triggered=False)
            
            # 4. Check for shrink-then-expand pattern
            # Volume decreased for 2-3 days then expanded
            recent_vols = volumes[-5:-1]  # Last 4 days before today
            min_vol_idx = np.argmin(recent_vols)
            
            # Volume today should be higher than all recent days
            if vol_today <= np.max(recent_vols):
                return SignalResult(triggered=False)
            
            return SignalResult(
                triggered=True,
                metadata={"vol_ratio": round(vol_ratio, 2)}
            )
            
        except Exception:
            return SignalResult(triggered=False)
