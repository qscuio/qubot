from typing import Dict, Any
import numpy as np
import pandas as pd

from app.services.scanner.base import SignalDetector, SignalResult
from app.services.scanner.registry import SignalRegistry
from app.services.scanner.utils import scale_pct, scale_ratio_down


@SignalRegistry.register
class LongCycleReversalSignal(SignalDetector):
    """长周期刚逆转向上（硬过滤 + 评分）."""

    signal_id = "long_cycle_reversal"
    display_name = "长周期刚逆转"
    icon = "🧭"
    group = "comprehensive"
    enabled = True
    min_bars = 120
    priority = 56

    # Parameters (tunable)
    N_LONG = 120
    N_MID = 60
    N_SHORT = 20

    # Thresholds
    LOW_CONVERGE_THRESH = 0.04
    PRICE_NEAR_MA_LONG = 0.10
    PRICE_NEAR_MA_LONG_BEST = 0.06
    UP_VOL_RATIO = 0.9
    ROC_EXCLUDE = 0.30
    MA_LONG_DOWN_EXCLUDE = 0.98
    NEAR_HIGH_EXCLUDE = 0.10

    def detect(self, hist: pd.DataFrame, stock_info: Dict[str, Any]) -> SignalResult:
        try:
            if len(hist) < self.min_bars:
                return SignalResult(triggered=False)

            name = stock_info.get("name", "")
            code = stock_info.get("code", "")
            if "ST" in name or "退" in name:
                return SignalResult(triggered=False)

            opens = hist["开盘"].values.astype(float)
            closes = hist["收盘"].values.astype(float)
            highs = hist["最高"].values.astype(float)
            lows = hist["最低"].values.astype(float)
            vols = hist["成交量"].values.astype(float)

            idx = len(hist) - 1
            close = closes[idx]

            def _ma(arr, end_idx, window):
                if end_idx < window - 1:
                    return None
                start = end_idx - window + 1
                return float(np.mean(arr[start:end_idx + 1]))

            def _llv(arr, end_idx, window):
                if end_idx < window - 1:
                    return None
                return float(np.min(arr[end_idx - window + 1:end_idx + 1]))

            def _hhv(arr, end_idx, window):
                if end_idx < window - 1:
                    return None
                return float(np.max(arr[end_idx - window + 1:end_idx + 1]))

            def _slope(series, end_idx, k):
                if end_idx < k:
                    return None
                return float(series[end_idx] - series[end_idx - k])

            # Long MA series (for slope checks)
            ma_long_series = np.full(len(hist), np.nan)
            for i in range(self.N_LONG - 1, len(hist)):
                ma_long_series[i] = np.mean(closes[i - self.N_LONG + 1:i + 1])

            low_converge_thresh = scale_pct(self.LOW_CONVERGE_THRESH, code, name)
            price_near_ma_long = scale_pct(self.PRICE_NEAR_MA_LONG, code, name)
            price_near_ma_long_best = scale_pct(self.PRICE_NEAR_MA_LONG_BEST, code, name)
            roc_exclude = scale_pct(self.ROC_EXCLUDE, code, name)
            near_high_exclude = scale_pct(self.NEAR_HIGH_EXCLUDE, code, name)
            ma_long_down_exclude = scale_ratio_down(self.MA_LONG_DOWN_EXCLUDE, code, name)
            slope_ratio_min = scale_pct(0.003, code, name)

            # 1) Hard filters: downtrend ended
            llv40 = _llv(lows, idx, 40)
            llv120 = _llv(lows, idx, 120)
            cond_a = False
            if llv40 is not None and llv120 is not None and llv120 > 0:
                cond_a = abs(llv40 - llv120) / llv120 <= low_converge_thresh

            llv30 = _llv(lows, idx, 30)
            llv60_prev = _llv(lows, idx - 1, 60)
            cond_b = llv30 is not None and llv60_prev is not None and llv30 > llv60_prev

            # 2) Long MA turning
            slope_past = _slope(ma_long_series, idx, 20)
            slope_recent = _slope(ma_long_series, idx, 5)
            cond_c = (
                slope_past is not None and slope_recent is not None and
                slope_past < 0 and slope_recent >= 0
            )

            ma_long = ma_long_series[idx] if not np.isnan(ma_long_series[idx]) else None

            # 3) Price behavior
            cond_d = False
            score_d = 0.0
            if ma_long is not None and ma_long > 0:
                dist = abs(close - ma_long) / ma_long
                if dist <= price_near_ma_long:
                    cond_d = True
                    if dist <= price_near_ma_long_best:
                        score_d = 12.0
                    else:
                        score_d = 12.0 * (
                            (price_near_ma_long - dist) /
                            (price_near_ma_long - price_near_ma_long_best)
                        )

            llv10 = _llv(lows, idx, 10)
            llv20_prev = _llv(lows, idx - 1, 20)
            cond_e1 = llv10 is not None and llv20_prev is not None and llv10 > llv20_prev

            ma60 = _ma(closes, idx, self.N_MID)
            llv10_now = llv10
            cond_e2 = ma60 is not None and llv10_now is not None and close > ma60 and llv10_now >= ma60
            cond_e = cond_e1 or cond_e2

            # 4) Volume structure
            up_vol = 0.0
            down_vol = 0.0
            for j in range(idx - 19, idx + 1):
                if j <= 0:
                    continue
                if closes[j] > closes[j - 1]:
                    up_vol += vols[j]
                elif closes[j] < closes[j - 1]:
                    down_vol += vols[j]

            cond_f = down_vol > 0 and up_vol >= self.UP_VOL_RATIO * down_vol

            avg_up = None
            avg_down = None
            up_days = 0
            down_days = 0
            for j in range(idx - 19, idx + 1):
                if j <= 0:
                    continue
                if closes[j] > closes[j - 1]:
                    up_days += 1
                elif closes[j] < closes[j - 1]:
                    down_days += 1
            if up_days > 0:
                avg_up = up_vol / up_days
            if down_days > 0:
                avg_down = down_vol / down_days

            cond_g1 = avg_up is not None and avg_down is not None and avg_down < avg_up
            ma_vol10 = _ma(vols, idx, 10)
            ma_vol30 = _ma(vols, idx, 30)
            max_vol3 = _hhv(vols, idx, 3)
            cond_g2 = (
                ma_vol10 is not None and ma_vol30 is not None and
                ma_vol10 > ma_vol30 and
                max_vol3 is not None and max_vol3 <= ma_vol30 * 2.0
            )
            cond_g = cond_g1 or cond_g2

            # 5) Exclusions
            roc20 = None
            if idx >= 20 and closes[idx - 20] > 0:
                roc20 = close / closes[idx - 20] - 1
            x1 = roc20 is not None and roc20 > roc_exclude

            x2 = False
            if idx >= 10 and ma_long is not None and not np.isnan(ma_long_series[idx - 10]) and ma_long_series[idx - 10] > 0:
                x2 = ma_long / ma_long_series[idx - 10] < ma_long_down_exclude

            high60 = _hhv(highs, idx, 60)
            x3 = high60 is not None and close > 0 and (high60 - close) / close < near_high_exclude

            # Scoring
            score = 0.0

            # S_end_down (0-25)
            score += 12.0 if cond_a else 0.0
            score += 13.0 if cond_b else 0.0

            # S_ma_turn (0-30)
            score_ma_turn = 0.0
            if cond_c and ma_long is not None and ma_long > 0 and slope_recent is not None:
                slope_ratio = slope_recent / ma_long
                score_ma_turn = 30.0 if slope_ratio >= slope_ratio_min else 20.0
            score += score_ma_turn

            # S_price_behavior (0-25)
            score += score_d
            score += 13.0 if cond_e else 0.0

            # S_volume (0-20)
            if cond_f and cond_g:
                score += 20.0
            elif cond_f:
                score += 12.0
            elif cond_g:
                score += 8.0

            # Penalties
            if x1:
                score -= 30.0
            if x2:
                score -= 40.0
            if x3:
                score -= 15.0

            score = max(0.0, min(100.0, score))

            passed = cond_a and cond_b and (cond_c or score_ma_turn >= 20.0) and score >= 60.0
            if not passed:
                return SignalResult(triggered=False)

            return SignalResult(
                triggered=True,
                metadata={
                    "score": round(score, 2),
                    "cond_a": cond_a,
                    "cond_b": cond_b,
                    "cond_c": cond_c,
                    "cond_d": cond_d,
                    "cond_e": cond_e,
                    "cond_f": cond_f,
                    "cond_g": cond_g,
                    "x1": x1,
                    "x2": x2,
                    "x3": x3,
                },
            )
        except Exception:
            return SignalResult(triggered=False)
