from typing import Dict, Any
import numpy as np
import pandas as pd

from app.services.scanner.base import SignalDetector, SignalResult
from app.services.scanner.registry import SignalRegistry
from app.services.scanner.utils import scale_pct, scale_ratio_up, scale_ratio_down


@SignalRegistry.register
class BottomQuickStartSignal(SignalDetector):
    """底部快启动扫描信号（压缩版逻辑）."""

    signal_id = "bottom_quick_start"
    display_name = "底部快启动"
    icon = "⚡"
    group = "comprehensive"
    enabled = True
    min_bars = 120
    priority = 55

    def detect(self, hist: pd.DataFrame, stock_info: Dict[str, Any]) -> SignalResult:
        try:
            if len(hist) < self.min_bars:
                return SignalResult(triggered=False)

            name = stock_info.get('name', '')
            code = stock_info.get('code', '')
            if 'ST' in name or '退' in name:
                return SignalResult(triggered=False)

            opens = hist['开盘'].values.astype(float)
            closes = hist['收盘'].values.astype(float)
            highs = hist['最高'].values.astype(float)
            lows = hist['最低'].values.astype(float)
            vols = hist['成交量'].values.astype(float)

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

            # ① 位置过滤
            low60 = _llv(lows, idx, 60)
            low120 = _llv(lows, idx, 120)
            ma60 = _ma(closes, idx, 60)
            high40 = _hhv(highs, idx, 40)
            low40 = _llv(lows, idx, 40)

            drop_ratio = None
            if high40 and high40 > 0:
                drop_ratio = (high40 - low40) / high40

            cond_pos1 = low60 is not None and close <= low60 * scale_ratio_up(1.15, code, name)
            cond_pos2 = low120 is not None and close <= low120 * scale_ratio_up(1.25, code, name)
            cond_pos3 = ma60 is not None and close <= ma60 * scale_ratio_up(1.08, code, name)
            cond_pos4 = drop_ratio is not None and drop_ratio >= scale_pct(0.3, code, name)
            cond_pos = (cond_pos1 + cond_pos2 + cond_pos3 + cond_pos4) >= 3

            # ② 有效小阳线计数（12日）
            small_up_cnt = 0
            down_cnt = 0
            rise_min = scale_pct(0.5, code, name)
            rise_max = scale_pct(2.5, code, name)
            for j in range(idx - 11, idx + 1):
                if j <= 0:
                    continue
                prev_c = closes[j - 1]
                rise = (closes[j] - prev_c) / prev_c * 100 if prev_c > 0 else 0
                rng = highs[j] - lows[j]
                body = closes[j] - opens[j]
                ma20v = _ma(vols, j, 20)

                if (
                    rise >= rise_min and rise <= rise_max and
                    rng > 0 and
                    body / rng >= 0.6 and
                    (highs[j] - closes[j]) <= body * 0.5 and
                    ma20v is not None and vols[j] <= ma20v * 1.2
                ):
                    small_up_cnt += 1

                if closes[j] < prev_c and vols[j] < vols[j - 1]:
                    down_cnt += 1

            range12 = None
            low12 = _llv(lows, idx, 12)
            high12 = _hhv(highs, idx, 12)
            if low12 and low12 > 0:
                range12 = (high12 - low12) / low12

            cond_box = small_up_cnt >= 4 and down_cnt <= 2 and range12 is not None and range12 <= scale_pct(0.12, code, name)

            # ③ 量能转强（10~30）
            vol10 = _ma(vols, idx, 10)
            vol30 = _ma(vols, idx, 30)
            hhv_vol10 = _hhv(vols, idx, 10)

            up_vol_sum = 0.0
            down_vol_sum = 0.0
            for j in range(idx - 9, idx + 1):
                if j <= 0:
                    continue
                if closes[j] > closes[j - 1]:
                    up_vol_sum += vols[j]
                elif closes[j] < closes[j - 1]:
                    down_vol_sum += vols[j]

            cond_vol = (
                vol10 is not None and vol30 is not None and
                vol10 > vol30 and
                hhv_vol10 is not None and vols[idx] <= hhv_vol10 and
                up_vol_sum > down_vol_sum
            )

            # ④ 时间临界信号
            bars_since_high20 = None
            if idx >= 19:
                window = highs[idx - 19:idx + 1]
                max_val = np.max(window)
                last_idx = np.where(window == max_val)[0][-1]
                bars_since_high20 = (len(window) - 1) - int(last_idx)

            ma5 = _ma(closes, idx, 5)
            ma10 = _ma(closes, idx, 10)
            ma20 = _ma(closes, idx, 20)
            ma20_prev = _ma(closes, idx - 5, 20)
            llv5 = _llv(lows, idx, 5)
            llv5_prev = _llv(lows, idx - 1, 5)

            cond_time1 = bars_since_high20 is not None and bars_since_high20 >= 15
            cond_time2 = ma5 is not None and ma10 is not None and ma5 > ma10
            cond_time3 = (
                ma20 is not None and ma20_prev is not None and ma20_prev > 0 and
                (ma20 / ma20_prev) > scale_ratio_down(0.998, code, name)
            )
            cond_time4 = llv5 is not None and llv5_prev is not None and llv5 > llv5_prev
            cond_time = (cond_time1 + cond_time2 + cond_time3 + cond_time4) >= 2

            # ⑤ 排除失败样本
            high60 = _hhv(highs, idx, 60)
            near_high = False
            if high60 is not None and close > 0:
                near_high = ((high60 - close) / close) < scale_pct(0.1, code, name)

            big_up = False
            if idx >= 10 and closes[idx - 10] > 0:
                big_up = (close / closes[idx - 10] - 1) > scale_pct(0.2, code, name)

            bad_bar_cnt = 0
            for j in range(idx - 9, idx + 1):
                if j < 0:
                    continue
                rng = highs[j] - lows[j]
                ma10v = _ma(vols, j, 10)
                if rng > 0 and ma10v is not None:
                    upper_shadow = (highs[j] - closes[j]) / rng
                    if upper_shadow > 0.6 and vols[j] > ma10v:
                        bad_bar_cnt += 1

            exclude = near_high or big_up or bad_bar_cnt >= 2

            triggered = cond_pos and cond_box and cond_vol and cond_time and not exclude
            if not triggered:
                return SignalResult(triggered=False)

            return SignalResult(
                triggered=True,
                metadata={
                    "score": int(cond_pos) + int(cond_box) + int(cond_vol) + int(cond_time),
                    "small_up_cnt": small_up_cnt,
                    "down_cnt": down_cnt,
                },
            )
        except Exception:
            return SignalResult(triggered=False)
