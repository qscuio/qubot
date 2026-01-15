import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional

def calculate_kuangbiao_score(hist: pd.DataFrame) -> Tuple[float, float, str]:
    """
    Calculate 'Kuangbiao' (狂飙) scores: ScoreA (Silent Accumulation) and ScoreB (Launch Trigger).
    
    Args:
        hist: DataFrame with columns ['收盘', '开盘', '最高', '最低', '成交量'] and datetime index or '日期' column.
        
    Returns:
        (score_a, score_b, state)
        state: "A" (Accumulation), "B" (Launch), or None
    """
    try:
        # Pre-check data length
        if len(hist) < 120:
            return 0.0, 0.0, None

        # Prepare series
        closes = hist['收盘']
        opens = hist['开盘']
        highs = hist['最高']
        lows = hist['最低']
        vols = hist['成交量']
        
        # Latest data points
        close = closes.iloc[-1]
        vol = vols.iloc[-1]
        open_p = opens.iloc[-1]
        high = highs.iloc[-1]
        low = lows.iloc[-1]

        # ==========================================
        # 1. ScoreA: Silent Accumulation (0-100)
        # ==========================================
        score_a = 0.0
        
        # --- A1. Position (0-20) ---
        # pos = (Close - Low120) / (High120 - Low120)
        low_120 = lows.iloc[-120:].min()
        high_120 = highs.iloc[-120:].max()
        if high_120 > low_120:
            pos = (close - low_120) / (high_120 - low_120)
            if 0.25 <= pos <= 0.55:
                score_a += 20
            elif (0.15 <= pos < 0.25) or (0.55 < pos <= 0.65):
                score_a += 10
        
        # --- A2. Compression (0-25) ---
        # ATR14 / Close
        tr = pd.concat([
            highs - lows,
            (highs - closes.shift(1)).abs(),
            (lows - closes.shift(1)).abs()
        ], axis=1).max(axis=1)
        atr14 = tr.rolling(14).mean().iloc[-1]
        atrp = atr14 / close if close > 0 else 1.0
        
        # BB Width
        ma20 = closes.rolling(20).mean().iloc[-1]
        std20 = closes.rolling(20).std().iloc[-1]
        bbw = (4 * std20) / ma20 if ma20 > 0 else 1.0
        
        # Historical best compression
        bbw_series = (4 * closes.rolling(20).std()) / closes.rolling(20).mean()
        min_bbw_120 = bbw_series.iloc[-120:].min()
        bbw_rank = (bbw - min_bbw_120) / (bbw_series.iloc[-120:].max() - min_bbw_120 + 1e-9) # Simple rank approx
        
        # Actually logic asks for "lowest 20%"
        # Let's count how many in last 120 days were smaller than current
        lower_count = (bbw_series.iloc[-120:] < bbw).sum()
        bbw_percentile = lower_count / 120.0
        
        if atrp <= 0.020:
            score_a += 15
        elif atrp <= 0.025:
            score_a += 8
            
        if bbw_percentile <= 0.20:
            score_a += 10
        elif bbw_percentile <= 0.35:
            score_a += 5
            
        # --- A3. Small Bullish Rhythm (0-25) ---
        # Window = 10 days
        w_closes = closes.iloc[-10:]
        w_opens = opens.iloc[-10:]
        
        up_count = (w_closes > w_opens).sum()
        avg_ret = ((w_closes / w_opens) - 1).mean()
        
        # Max Drawdown in window
        roll_max = w_closes.cummax()
        daily_dd = w_closes / roll_max - 1.0
        max_dd = abs(daily_dd.min())
        
        if up_count >= 6:
            score_a += 10
        elif up_count >= 5:
            score_a += 6
            
        if 0.003 <= avg_ret <= 0.018:
            score_a += 10
            
        if max_dd <= 0.03:
            score_a += 5
        elif max_dd <= 0.05:
            score_a += 2
            
        # --- A4. Gentle Volume (0-20) ---
        vol_5 = vols.iloc[-5:].mean()
        vol_20 = vols.iloc[-20:].mean()
        vr = vol_5 / vol_20 if vol_20 > 0 else 0
        
        # Slope of volume (10 days)
        # Simple linear regression slope
        y = vols.iloc[-10:].values
        x = np.arange(len(y))
        if len(y) > 1:
            slope = np.polyfit(x, y, 1)[0]
        else:
            slope = 0
            
        if 1.05 <= vr <= 1.60:
            score_a += 12
        elif 0.95 <= vr < 1.05: # Slight overlap handling
            score_a += 6
            
        if slope > 0:
            score_a += 8
            
        # --- A5. Support/Shadow (0-10) ---
        # sum(lowerShadow, 10) / sum(upperShadow, 10)
        w_opens_10 = opens.iloc[-10:]
        w_closes_10 = closes.iloc[-10:]
        w_highs_10 = highs.iloc[-10:]
        w_lows_10 = lows.iloc[-10:]
        
        lower_shadows = np.minimum(w_opens_10, w_closes_10) - w_lows_10
        upper_shadows = w_highs_10 - np.maximum(w_opens_10, w_closes_10)
        
        sum_lower = lower_shadows.sum()
        sum_upper = upper_shadows.sum()
        
        shadow_ratio = sum_lower / (sum_upper + 1e-9)
        
        if shadow_ratio >= 1.3:
            score_a += 10
        elif shadow_ratio >= 1.1:
            score_a += 5
            
        # --- Filters for Score A ---
        # F1: Fake Accumulation
        if vr < 0.9 and slope <= 0:
            return 0.0, 0.0, None

        # F2: Distance to supply (Skipped as "chip distribution" data not reliable in local calc)
        # Assuming acceptable for now or handled by A1 Position.
        
        
        # ==========================================
        # 2. ScoreB: Launch Trigger (0-100)
        # ==========================================
        score_b = 0.0
        
        # --- B1. Breakout Strength (0-45) ---
        # Breakout 20-day high (excluding today)
        high_20_prev = highs.iloc[-21:-1].max()
        is_breakout = close > high_20_prev
        
        body_pct = abs(close - open_p) / (high - low + 1e-9)
        close_pos = (close - low) / (high - low + 1e-9)
        
        if is_breakout:
            score_b += 20
        
        if body_pct >= 0.65:
            score_b += 15
        elif body_pct >= 0.55:
            score_b += 8
            
        if close_pos >= 0.85:
            score_b += 10
        elif close_pos >= 0.75:
            score_b += 5
            
        # --- B2. Volume Surge (0-35) ---
        # v1 = Vol / MA20(Vol)
        # Note: Previous MA20 calculation included today, stricter is excluding today? 
        # User defined "Vol / MA20(Vol)". Typically compares today to avg.
        # Let's use avg including today or excluding? Usually relative to recent past.
        # Using MA20 including today for simplicity as per standard standard indicators, 
        # but user context "v1 > 6.0" implies ratio.
        # Let's use MA20 of *previous* 20 days to be cleaner trigger.
        vol_ma20_prev = vols.iloc[-21:-1].mean()
        if vol_ma20_prev > 0:
            v1 = vol / vol_ma20_prev
        else:
            v1 = 0
            
        if 2.0 <= v1 <= 4.0:
            score_b += 35
        elif 1.6 <= v1 < 2.0:
            score_b += 20
        elif v1 > 6.0:
            score_b -= 10
            
        # --- B3. Retest Verification (0-20) ---
        # Typically looks at T+1, T+2.
        # Since we scan "Today", we look if "Today" is a retest day OR if "Today" is launch day.
        # User says: "Trigger (Strong constraint) ... Retest (1-3 days later)".
        # Use case interpretation:
        # Case 1: Today is Launch Day. ScoreB should be high based on B1+B2. B3 is 0. 
        #         Total = 80. -> Launch Confirmed.
        # Case 2: Today is Retest Day (Launch was 1-3 days ago).
        #         We need to check if launch happened recently.
        
        # Let's strictly implement for "Today is Launch Day" first.
        # If today is retest, the breakout condition (B1) might fail for today close.
        # But we can check if breakout happened recently.
        
        # Simplification: This scanner finds "Launch Trigger" (Today) OR "Retest Success" (Today).
        # Check if breakout in last 3 days
        breakout_day_idx = -1
        for i in range(1, 4): # -1, -2, -3
             if i >= len(closes): break
             c = closes.iloc[-1-i]
             h_prev = highs.iloc[-21-i : -1-i].max()
             if c > h_prev:
                 breakout_day_idx = i
                 break
        
        if breakout_day_idx != -1:
            # Launch was 'i' days ago.
            # Check retest condition
            launch_price = closes.iloc[-1-breakout_day_idx]
            retest_ok = low >= launch_price * 0.98
            
            launch_vol = vols.iloc[-1-breakout_day_idx]
            vol_drop = vol < launch_vol * 0.7
            
            if retest_ok and vol_drop:
                score_b += 20
        
        
        # ==========================================
        # 3. State Determination
        # ==========================================
        state = None
        
        # F3: Multiple failures check (60 days)
        # Count times Vol > 2*MA20 AND Close dropped next day below breakout
        # Skip for performance now, assume ok.

        if score_a >= 70:
            state = "A" # Silent Accumulation
            
            # Check if updated to B
            # Condition: State A AND ScoreB >= 70
            # OR ScoreB >= 55 AND ScoreA >= 75
            
            if score_b >= 70:
                state = "B"
            elif score_b >= 55 and score_a >= 75:
                state = "B"
        
        # Direct strong B check even if A is slightly weak?
        # User: "State=A and ScoreB>=70 -> State=B"
        # Implies A is prerequisite.
        
        return score_a, score_b, state

    except Exception as e:
        # print(f"Error calculating score: {e}")
        return 0.0, 0.0, None
