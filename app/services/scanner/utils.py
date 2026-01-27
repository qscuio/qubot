"""
Shared utility functions for signal detection.

Provides common calculations used across multiple signals:
- ATR (Average True Range)
- OBV (On-Balance Volume)
- Linear Regression Channel
- Pivot Detection
- Position in Range
"""

import numpy as np
from typing import List, Tuple, Dict, Any, Optional
import pandas as pd


def calculate_atr(hist: pd.DataFrame, period: int = 14) -> float:
    """Calculate Average True Range.
    
    Args:
        hist: DataFrame with 最高, 最低, 收盘 columns
        period: ATR period (default 14)
        
    Returns:
        ATR value
    """
    if len(hist) < 2:
        return 0.0
    
    highs = hist['最高'].values
    lows = hist['最低'].values
    closes = hist['收盘'].values
    
    trs = []
    for i in range(1, len(hist)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
        trs.append(tr)
    
    if len(trs) < period:
        return np.mean(trs) if trs else 0.0
    
    return np.mean(trs[-period:])


def calculate_obv(closes: np.ndarray, volumes: np.ndarray) -> np.ndarray:
    """Calculate On-Balance Volume.
    
    Args:
        closes: Array of close prices
        volumes: Array of volumes
        
    Returns:
        OBV array
    """
    obv = np.zeros(len(closes))
    obv[0] = volumes[0]
    
    for i in range(1, len(closes)):
        if closes[i] > closes[i-1]:
            obv[i] = obv[i-1] + volumes[i]
        elif closes[i] < closes[i-1]:
            obv[i] = obv[i-1] - volumes[i]
        else:
            obv[i] = obv[i-1]
    
    return obv


def calculate_linreg_channel(
    series: pd.Series, 
    window: int
) -> Tuple[float, float, float, float]:
    """Calculate Linear Regression Channel.
    
    Args:
        series: Price series (usually closes)
        window: Lookback window
        
    Returns:
        Tuple of (slope, mid, upper, lower) at current bar
    """
    try:
        if len(series) < window:
            return 0.0, 0.0, 0.0, 0.0
        
        y = series.iloc[-window:].values
        x = np.arange(window)
        
        # Linear regression: y = mx + b
        slope, intercept = np.polyfit(x, y, 1)
        
        # Predicted values
        y_pred = slope * x + intercept
        
        # Std dev of residuals
        residuals = y - y_pred
        std_dev = np.std(residuals)
        
        # Current values (at end of window)
        current_mid = slope * (window - 1) + intercept
        current_upper = current_mid + 2 * std_dev
        current_lower = current_mid - 2 * std_dev
        
        return slope, current_mid, current_upper, current_lower
    except Exception:
        return 0.0, 0.0, 0.0, 0.0


def detect_pivot_highs(
    highs: np.ndarray, 
    left_bars: int = 3, 
    right_bars: int = 3
) -> List[Dict[str, Any]]:
    """Detect pivot high points.
    
    Args:
        highs: Array of high prices
        left_bars: Left lookback bars
        right_bars: Right lookback bars
        
    Returns:
        List of dicts with 'idx' and 'price' keys
    """
    pivots = []
    
    for i in range(left_bars, len(highs) - right_bars):
        is_pivot = True
        for j in range(-left_bars, right_bars + 1):
            if j != 0 and highs[i + j] > highs[i]:
                is_pivot = False
                break
        if is_pivot:
            pivots.append({'idx': i, 'price': highs[i]})
    
    return pivots


def detect_pivot_lows(
    lows: np.ndarray, 
    left_bars: int = 3, 
    right_bars: int = 3
) -> List[Dict[str, Any]]:
    """Detect pivot low points.
    
    Args:
        lows: Array of low prices
        left_bars: Left lookback bars
        right_bars: Right lookback bars
        
    Returns:
        List of dicts with 'idx' and 'price' keys
    """
    pivots = []
    
    for i in range(left_bars, len(lows) - right_bars):
        is_pivot = True
        for j in range(-left_bars, right_bars + 1):
            if j != 0 and lows[i + j] < lows[i]:
                is_pivot = False
                break
        if is_pivot:
            pivots.append({'idx': i, 'price': lows[i]})
    
    return pivots


def calculate_position_in_range(
    current: float, 
    high: float, 
    low: float
) -> float:
    """Calculate position within a price range (0-1).
    
    Args:
        current: Current price
        high: Range high
        low: Range low
        
    Returns:
        Position as float (0 = at low, 1 = at high)
    """
    range_size = high - low
    if range_size <= 0:
        return 0.5
    return (current - low) / range_size


def calculate_volume_ratio(
    volumes: np.ndarray, 
    current_idx: int = -1, 
    lookback: int = 20
) -> float:
    """Calculate volume ratio vs average.
    
    Args:
        volumes: Array of volumes
        current_idx: Index of current bar (-1 for last)
        lookback: Average lookback period
        
    Returns:
        Volume ratio (1.0 = average)
    """
    if len(volumes) < lookback + 1:
        return 1.0
    
    current_vol = volumes[current_idx]
    
    if current_idx == -1:
        avg_vol = np.mean(volumes[-lookback-1:-1])
    else:
        start_idx = max(0, current_idx - lookback)
        avg_vol = np.mean(volumes[start_idx:current_idx])
    
    return current_vol / avg_vol if avg_vol > 0 else 1.0


def is_bullish_candle(open_price: float, close: float) -> bool:
    """Check if candle is bullish (close > open)."""
    return close > open_price


def is_bearish_candle(open_price: float, close: float) -> bool:
    """Check if candle is bearish (close < open)."""
    return close < open_price


def calculate_body_percent(open_price: float, close: float) -> float:
    """Calculate candle body as percentage of open.
    
    Returns:
        Body percentage (can be negative for bearish)
    """
    if open_price <= 0:
        return 0.0
    return (close - open_price) / open_price * 100


def calculate_daily_return(prev_close: float, close: float) -> float:
    """Calculate daily return percentage.
    
    Returns:
        Return as decimal (0.05 = 5%)
    """
    if prev_close <= 0:
        return 0.0
    return (close - prev_close) / prev_close


def get_board_multiplier(code: Optional[str], name: Optional[str]) -> float:
    """Return board-based volatility multiplier (主板=1x, 创业/科创=2x, 北交所=3x, ST=0.5x)."""
    if name and ("ST" in name or "*ST" in name):
        return 0.5
    if code and code.startswith("8") and len(code) == 6:
        return 3.0
    if code and (code.startswith("68") or code.startswith("30")):
        return 2.0
    return 1.0


def scale_pct(value: float, code: Optional[str], name: Optional[str]) -> float:
    """Scale a percentage threshold (decimal or percent units) by board multiplier."""
    return value * get_board_multiplier(code, name)


def scale_ratio_up(ratio: float, code: Optional[str], name: Optional[str]) -> float:
    """Scale an upward ratio like 1.15 (15% above) by board multiplier."""
    return 1 + (ratio - 1) * get_board_multiplier(code, name)


def scale_ratio_down(ratio: float, code: Optional[str], name: Optional[str]) -> float:
    """Scale a downward ratio like 0.98 (2% below) by board multiplier."""
    return 1 - (1 - ratio) * get_board_multiplier(code, name)


def get_limit_up_threshold(code: Optional[str], name: Optional[str]) -> float:
    """Get limit-up threshold as decimal based on board type."""
    if code and code.startswith("8") and len(code) == 6:
        return 0.295  # 北交所 30%
    if code and (code.startswith("68") or code.startswith("30")):
        return 0.195  # 科创板/创业板 20%
    if name and ("ST" in name or "*ST" in name):
        return 0.045  # ST 5%
    return 0.095  # 主板 10%


def is_limit_up(
    prev_close: float,
    close: float,
    threshold: Optional[float] = None,
    code: Optional[str] = None,
    name: Optional[str] = None,
) -> bool:
    """Check if stock hit limit up (涨停).
    
    Args:
        prev_close: Previous close
        close: Current close
        threshold: Limit up threshold (decimal). If None, infer by board.
        code: Stock code for board inference
        name: Stock name for ST inference
        
    Returns:
        True if limit up
    """
    if threshold is None:
        threshold = get_limit_up_threshold(code, name)
    return calculate_daily_return(prev_close, close) > threshold


def resample_to_weekly(hist: pd.DataFrame) -> pd.DataFrame:
    """Resample daily data to weekly.
    
    Args:
        hist: Daily DataFrame with 日期, 开盘, 收盘, 最高, 最低, 成交量
        
    Returns:
        Weekly DataFrame
    """
    if len(hist) < 5:
        return hist
    
    hist = hist.copy()
    hist['日期'] = pd.to_datetime(hist['日期'])
    hist = hist.set_index('日期')
    
    weekly = hist.resample('W').agg({
        '开盘': 'first',
        '收盘': 'last',
        '最高': 'max',
        '最低': 'min',
        '成交量': 'sum'
    }).dropna().reset_index()
    
    return weekly


def resample_to_monthly(hist: pd.DataFrame) -> pd.DataFrame:
    """Resample daily data to monthly.
    
    Args:
        hist: Daily DataFrame with 日期, 开盘, 收盘, 最高, 最低, 成交量
        
    Returns:
        Monthly DataFrame
    """
    if len(hist) < 20:
        return hist
    
    hist = hist.copy()
    hist['日期'] = pd.to_datetime(hist['日期'])
    hist = hist.set_index('日期')
    
    monthly = hist.resample('M').agg({
        '开盘': 'first',
        '收盘': 'last',
        '最高': 'max',
        '最低': 'min',
        '成交量': 'sum'
    }).dropna().reset_index()
    

def calculate_ma(series: np.ndarray, period: int) -> float:
    """Calculate Moving Average (Simple).
    
    Args:
        series: Data array
        period: Period
        
    Returns:
        Current MA value
    """
    if len(series) < period:
        return 0.0
    return np.mean(series[-period:])


def calculate_slope(series: np.ndarray, period: int) -> float:
    """Calculate linear regression slope.
    
    Args:
        series: Data array
        period: Lookback period
        
    Returns:
        Slope value
    """
    if len(series) < period:
        return 0.0
    
    y = series[-period:]
    x = np.arange(period)
    
    try:
        slope, _ = np.polyfit(x, y, 1)
        return slope
    except:
        return 0.0


def calculate_mfi(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    volumes: np.ndarray,
    period: int = 14
) -> float:
    """Calculate Money Flow Index (MFI).
    
    Args:
        highs: High prices
        lows: Low prices
        closes: Close prices
        volumes: Volumes
        period: Period (default 14)
        
    Returns:
        Current MFI value (0-100)
    """
    if len(closes) < period + 1:
        return 50.0
        
    # Typical Price
    tp = (highs + lows + closes) / 3
    
    # Raw Money Flow
    rmf = tp * volumes
    
    # Positive/Negative Flow
    pos_flow = []
    neg_flow = []
    
    # Calculate for the last 'period' days relative to the end of the array
    # We need period+1 data points to calculate `period` changes.
    # We only care about the MFI at the very end.
    
    target_tp = tp[-(period+1):]
    target_rmf = rmf[-(period+1):]
    
    current_pos_sum = 0.0
    current_neg_sum = 0.0
    
    for i in range(1, len(target_tp)):
        if target_tp[i] > target_tp[i-1]:
            current_pos_sum += target_rmf[i]
        elif target_tp[i] < target_tp[i-1]:
            current_neg_sum += target_rmf[i]
            
    if current_neg_sum == 0:
        return 100.0
        
    mfr = current_pos_sum / current_neg_sum
    mfi = 100 - (100 / (1 + mfr))
    return mfi


def calculate_cmf(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    volumes: np.ndarray,
    period: int = 20
) -> float:
    """Calculate Chaikin Money Flow (CMF).
    
    Args:
        highs: High prices
        lows: Low prices
        closes: Close prices
        volumes: Volumes
        period: Period (default 20)
        
    Returns:
        Current CMF value
    """
    if len(closes) < period:
        return 0.0
        
    # Slice last 'period' elements
    h = highs[-period:]
    l = lows[-period:]
    c = closes[-period:]
    v = volumes[-period:]
    
    vol_sum = np.sum(v)
    
    if vol_sum == 0:
        return 0.0
        
    mf_vol_sum = 0.0
    
    for i in range(len(c)):
        range_hl = h[i] - l[i]
        if range_hl == 0:
            continue
            
        mfm = ((c[i] - l[i]) - (h[i] - c[i])) / range_hl
        mf_vol_sum += mfm * v[i]
        
    return mf_vol_sum / vol_sum
