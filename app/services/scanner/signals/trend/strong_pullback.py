"""Strong Pullback Signal - 强势股回踩确认."""

from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd

from app.services.scanner.base import SignalDetector, SignalResult
from app.services.scanner.registry import SignalRegistry
from app.services.scanner.utils import calculate_atr, detect_pivot_lows, scale_pct


@SignalRegistry.register
class StrongPullbackSignal(SignalDetector):
    """强势股回踩信号（A股日线）.

    核心逻辑：
    1) 趋势过滤：MA20>MA60>MA120，MA60斜率上行，收盘在MA60上方，低点抬高
    2) 重要支撑：均线/突破价/VWAP60 至少两类共振
    3) 健康回踩：回撤 3%-10%，缩量，收盘不破MA60
    4) 触发：站回MA20并放量（或箱体突破）
    """

    signal_id = "strong_pullback"
    display_name = "强势股回踩"
    icon = "🧲"
    group = "trend"
    min_bars = 160
    priority = 62

    lookback_breakout = 60
    swing_k = 3
    require_breakout_jump = True

    def detect(self, hist: pd.DataFrame, stock_info: Dict[str, Any]) -> SignalResult:
        try:
            if len(hist) < self.min_bars:
                return SignalResult(triggered=False)

            close = hist['收盘'].astype(float)
            high = hist['最高'].astype(float)
            low = hist['最低'].astype(float)
            vol = hist['成交量'].astype(float)

            ma20 = close.rolling(20).mean()
            ma60 = close.rolling(60).mean()
            ma120 = close.rolling(120).mean()

            if pd.isna(ma120.iloc[-1]) or pd.isna(ma60.iloc[-1]) or pd.isna(ma20.iloc[-1]):
                return SignalResult(triggered=False)

            atr14 = calculate_atr(hist, 14)
            if atr14 <= 0:
                return SignalResult(triggered=False)

            # Trend filter
            trend_ok, sl1_price, sl2_price = self._trend_filter(close, low, ma20, ma60, ma120)
            if not trend_ok:
                return SignalResult(triggered=False)

            code = stock_info.get("code")
            name = stock_info.get("name")

            # Support score
            breakout_jump_min = scale_pct(0.05, code, name)
            breakout_price = self._find_recent_breakout(close, vol, breakout_jump_min)
            vwap60 = self._calculate_vwap(high, low, close, vol, 60)
            support_score, support_hits = self._support_score(
                low.iloc[-1],
                close.iloc[-1],
                ma20.iloc[-1],
                ma60.iloc[-1],
                breakout_price,
                vwap60,
                atr14
            )
            support_ok = support_score >= 2

            min_dd = scale_pct(0.03, code, name)
            max_dd = scale_pct(0.10, code, name)
            box_range_max = scale_pct(0.04, code, name)

            # Pullback health
            pullback_ok = self._pullback_ok(close, vol, ma60.iloc[-1], min_dd, max_dd)

            # Trigger
            trigger, trigger_name = self._trigger(
                close, high, low, vol, ma20, atr14, box_range_max
            )

            buy_signal = trend_ok and support_ok and pullback_ok and trigger

            stop_price = self._calc_stop(ma60.iloc[-1], breakout_price, sl1_price, atr14)

            return SignalResult(
                triggered=buy_signal,
                metadata={
                    "support_score": support_score,
                    "support_hits": support_hits,
                    "breakout_price": round(breakout_price, 3) if breakout_price else None,
                    "vwap60": round(vwap60, 3) if vwap60 else None,
                    "trigger": trigger_name,
                    "stop": round(stop_price, 3) if stop_price else None,
                    "dd20": round(self._dd20(close), 4),
                    "vol_shrink": self._vol_shrink_ok(vol),
                }
            )
        except Exception:
            return SignalResult(triggered=False)

    def _trend_filter(
        self,
        close: pd.Series,
        low: pd.Series,
        ma20: pd.Series,
        ma60: pd.Series,
        ma120: pd.Series,
    ) -> Tuple[bool, Optional[float], Optional[float]]:
        ma20_last = float(ma20.iloc[-1])
        ma60_last = float(ma60.iloc[-1])
        ma120_last = float(ma120.iloc[-1])

        if not (ma20_last > ma60_last > ma120_last):
            return False, None, None

        if close.iloc[-1] <= ma60_last:
            return False, None, None

        # MA60 slope (20 bars)
        ma60_tail = ma60.iloc[-20:]
        if ma60_tail.isna().any():
            return False, None, None
        slope = np.polyfit(np.arange(20), ma60_tail.values, 1)[0]
        if slope <= 0:
            return False, None, None

        # Swing lows: SL1 > SL2
        pivot_lows = detect_pivot_lows(low.values, self.swing_k, self.swing_k)
        if len(pivot_lows) < 2:
            return False, None, None
        sl1 = pivot_lows[-1]
        sl2 = pivot_lows[-2]
        if sl1['price'] <= sl2['price']:
            return False, None, None

        return True, float(sl1['price']), float(sl2['price'])

    def _find_recent_breakout(
        self,
        close: pd.Series,
        vol: pd.Series,
        breakout_jump_min: float,
    ) -> Optional[float]:
        if len(close) < 40:
            return None

        start = max(20, len(close) - self.lookback_breakout)
        end = len(close) - 1  # exclude today

        for idx in range(end - 1, start - 1, -1):
            prev20_high = close.iloc[idx - 20:idx].max()
            if close.iloc[idx] <= prev20_high:
                continue
            vol_ma = vol.iloc[idx - 20:idx].mean()
            if pd.isna(vol_ma) or vol_ma <= 0:
                continue
            if vol.iloc[idx] <= 1.8 * vol_ma:
                continue
            if self.require_breakout_jump:
                prev_close = close.iloc[idx - 1]
                if prev_close <= 0 or (close.iloc[idx] / prev_close - 1) <= breakout_jump_min:
                    continue
            return float(close.iloc[idx])

        return None

    def _calculate_vwap(
        self,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        vol: pd.Series,
        window: int,
    ) -> Optional[float]:
        if len(close) < window:
            return None

        typical = (high + low + close) / 3.0
        vol_sum = vol.rolling(window).sum()
        pv_sum = (typical * vol).rolling(window).sum()
        vwap = pv_sum / vol_sum.replace(0, np.nan)
        value = vwap.iloc[-1]
        if pd.isna(value) or value <= 0:
            return None
        return float(value)

    def _support_score(
        self,
        low_last: float,
        close_last: float,
        ma20_last: float,
        ma60_last: float,
        breakout_price: Optional[float],
        vwap60: Optional[float],
        atr14: float,
    ) -> Tuple[int, Dict[str, bool]]:
        tol = 0.5 * atr14
        touch_ma20 = abs(low_last - ma20_last) <= tol
        touch_ma60 = abs(low_last - ma60_last) <= 0.8 * atr14
        touch_bo = False
        if breakout_price:
            touch_bo = abs(low_last - breakout_price) <= 0.8 * atr14
        touch_vwap = False
        if vwap60:
            touch_vwap = abs(close_last - vwap60) <= 0.4 * atr14

        hits = {
            "ma20": touch_ma20,
            "ma60": touch_ma60,
            "breakout": touch_bo,
            "vwap60": touch_vwap,
        }
        score = sum(1 for v in hits.values() if v)
        return score, hits

    def _dd20(self, close: pd.Series) -> float:
        if len(close) < 20:
            return 0.0
        hhv = close.iloc[-20:].max()
        if hhv <= 0:
            return 0.0
        return float((hhv - close.iloc[-1]) / hhv)

    def _vol_shrink_ok(self, vol: pd.Series) -> bool:
        if len(vol) < 10:
            return False
        vol_ma3 = vol.rolling(3).mean().iloc[-1]
        vol_ma10 = vol.rolling(10).mean().iloc[-1]
        if pd.isna(vol_ma3) or pd.isna(vol_ma10) or vol_ma10 <= 0:
            return False
        return vol_ma3 < 0.75 * vol_ma10

    def _pullback_ok(self, close: pd.Series, vol: pd.Series, ma60_last: float, min_dd: float, max_dd: float) -> bool:
        dd20 = self._dd20(close)
        if dd20 < min_dd or dd20 > max_dd:
            return False
        if close.iloc[-1] < ma60_last:
            return False
        if not self._vol_shrink_ok(vol):
            return False
        return True

    def _trigger(
        self,
        close: pd.Series,
        high: pd.Series,
        low: pd.Series,
        vol: pd.Series,
        ma20: pd.Series,
        atr14: float,
        box_range_max: float,
    ) -> Tuple[bool, str]:
        if len(close) < 6:
            return False, ""

        close_prev = close.iloc[-2]
        close_last = close.iloc[-1]
        ma20_prev = ma20.iloc[-2]
        ma20_last = ma20.iloc[-1]
        vol_last = vol.iloc[-1]
        vol_ma5 = vol.iloc[-6:-1].mean() if len(vol) >= 6 else vol.rolling(5).mean().iloc[-1]

        if pd.isna(ma20_prev) or pd.isna(ma20_last) or pd.isna(vol_ma5) or vol_ma5 <= 0:
            return False, ""

        t1 = (
            close_prev <= ma20_prev + 0.2 * atr14
            and close_last > ma20_last
            and vol_last > 1.2 * vol_ma5
        )

        box_high = high.iloc[-5:].max()
        box_low = low.iloc[-5:].min()
        box_range = (box_high - box_low) / box_low if box_low > 0 else 1.0
        box_high_prev = high.iloc[-6:-1].max()

        t2 = (
            box_range <= box_range_max
            and close_last > box_high_prev
            and vol_last > 1.3 * vol_ma5
        )

        if t1:
            return True, "T1"
        if t2:
            return True, "T2"
        return False, ""

    def _calc_stop(
        self,
        ma60_last: float,
        breakout_price: Optional[float],
        swing_low: Optional[float],
        atr14: float,
    ) -> Optional[float]:
        candidates = [ma60_last]
        if breakout_price:
            candidates.append(breakout_price)
        if swing_low:
            candidates.append(swing_low)
        if not candidates:
            return None
        base = min(candidates)
        return base - atr14
