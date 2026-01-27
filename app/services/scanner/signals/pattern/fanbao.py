"""Strong Fanbao Signal - Strong stock reversal pattern."""

from app.services.scanner.base import SignalDetector, SignalResult
from app.services.scanner.registry import SignalRegistry
from app.services.scanner.utils import is_bullish_candle, is_bearish_candle, is_limit_up, scale_pct


@SignalRegistry.register
class StrongFanbaoSignal(SignalDetector):
    """强势股反包信号.
    
    条件:
    1. 强势背景: 过去10天内(不含今日)有过涨停(按板块阈值)
    2. 昨日调整: 昨日收阴线 (收盘 < 开盘)
    3. 今日反包: 今日收阳线，且收盘价 > 昨日开盘价 (实体反包)
    4. 力度确认: 今日涨幅 > 3%
    """
    
    signal_id = "strong_fanbao"
    display_name = "强势反包"
    icon = "↩️"
    group = "pattern"
    min_bars = 12
    priority = 86
    
    def detect(self, hist, stock_info) -> SignalResult:
        try:
            if len(hist) < 11:
                return SignalResult(triggered=False)
            
            today = hist.iloc[-1]
            yesterday = hist.iloc[-2]
            
            # 1. Check for limit up in last 10 days (excluding today)
            past_10 = hist.iloc[-12:-1]  # 10 days before today
            if len(past_10) < 2:
                return SignalResult(triggered=False)
            
            has_limit_up = False
            for i in range(1, len(past_10)):
                curr = past_10.iloc[i]
                prev = past_10.iloc[i-1]
                if is_limit_up(
                    prev['收盘'],
                    curr['收盘'],
                    code=stock_info.get("code"),
                    name=stock_info.get("name"),
                ):
                    has_limit_up = True
                    break
            
            if not has_limit_up:
                return SignalResult(triggered=False)
            
            # 2. Yesterday: bearish
            if not is_bearish_candle(yesterday['开盘'], yesterday['收盘']):
                return SignalResult(triggered=False)
            
            # 3. Today: bullish and engulfs yesterday's open
            if not is_bullish_candle(today['开盘'], today['收盘']):
                return SignalResult(triggered=False)
            
            if today['收盘'] <= yesterday['开盘']:
                return SignalResult(triggered=False)
            
            # 4. Today gain > 3% (board-aware)
            pct_change = (today['收盘'] - yesterday['收盘']) / yesterday['收盘']
            if pct_change < scale_pct(0.03, stock_info.get("code"), stock_info.get("name")):
                return SignalResult(triggered=False)
            
            return SignalResult(
                triggered=True,
                metadata={"gain_pct": round(pct_change * 100, 2)}
            )
            
        except Exception:
            return SignalResult(triggered=False)
