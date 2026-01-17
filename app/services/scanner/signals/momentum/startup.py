"""Startup Candidate Signal - Early stage startup detection."""

import numpy as np
from app.services.scanner.base import SignalDetector, SignalResult
from app.services.scanner.registry import SignalRegistry


@SignalRegistry.register
class StartupCandidateSignal(SignalDetector):
    """启动阶段信号 - 主力开始试盘/建仓."""
    
    signal_id = "startup_candidate"
    display_name = "启动关注"
    icon = "🚀"
    group = "momentum"
    min_bars = 60
    priority = 20
    
    def detect(self, hist, stock_info) -> SignalResult:
        """
        核心思想: 主力开始试盘 / 建仓 → 情绪尚未扩散 → 波动率和成交量刚抬头
        
        指标体系:
        1. 趋势过滤: Close < MA200, MA20 > MA60, MA60走平或向上
        2. 量能异动: 1.8x < Volume < 3.5x MA20(Vol)
        3. 形态突破: Close > 20日最高, 实体/振幅 > 0.6
        4. 资金行为: 3% < 换手率 < 10%
        """
        try:
            if len(hist) < 60:
                return SignalResult(triggered=False)
            
            closes = hist['收盘'].values
            volumes = hist['成交量'].values
            highs = hist['最高'].values
            lows = hist['最低'].values
            opens = hist['开盘'].values
            
            # Calculate MAs
            ma20 = np.mean(closes[-20:])
            ma60 = np.mean(closes[-60:])
            
            # 1. Trend filter: MA20 > MA60
            if ma20 <= ma60:
                return SignalResult(triggered=False)
            
            # 2. Volume surge: 1.8x < Vol < 3.5x
            vol_today = volumes[-1]
            vol_ma20 = np.mean(volumes[-20:])
            vol_ratio = vol_today / vol_ma20 if vol_ma20 > 0 else 0
            
            if not (1.8 < vol_ratio < 3.5):
                return SignalResult(triggered=False)
            
            # 3. Breakout: Close > 20-day high
            close_today = closes[-1]
            high_20 = np.max(highs[-21:-1])
            
            if close_today <= high_20:
                return SignalResult(triggered=False)
            
            # 4. Solid body: body/range > 0.6
            open_today = opens[-1]
            high_today = highs[-1]
            low_today = lows[-1]
            
            body = abs(close_today - open_today)
            range_today = high_today - low_today
            
            if range_today > 0 and body / range_today < 0.6:
                return SignalResult(triggered=False)
            
            # 5. Turnover filter (if available)
            if '换手率' in hist.columns:
                turnover = hist['换手率'].iloc[-1]
                if turnover < 3 or turnover > 10:
                    return SignalResult(triggered=False)
            
            return SignalResult(
                triggered=True,
                metadata={"vol_ratio": round(vol_ratio, 2)}
            )
            
        except Exception:
            return SignalResult(triggered=False)
