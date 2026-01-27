"""Small Bullish Pattern Signals - Various small bullish candle patterns."""

from app.services.scanner.base import SignalDetector, SignalResult
from app.services.scanner.registry import SignalRegistry
from app.services.scanner.utils import (
    is_bullish_candle, is_bearish_candle, calculate_body_percent,
    calculate_position_in_range, scale_pct
)


class SmallBullishBase(SignalDetector):
    """Base class for small bullish patterns."""
    group = "pattern"
    
    def is_small_bullish(self, open_price: float, close: float, stock_info: dict) -> bool:
        """Check if candle is small bullish (0.5% - 3% body, board-aware)."""
        if close <= open_price:
            return False
        body_pct = calculate_body_percent(open_price, close)
        code = stock_info.get("code")
        name = stock_info.get("name")
        min_body = scale_pct(0.5, code, name)
        max_body = scale_pct(3.0, code, name)
        return min_body <= body_pct <= max_body
    
    def is_at_bottom(self, hist, threshold: float = 0.4) -> bool:
        """Check if price is in lower part of range."""
        try:
            close_current = hist['收盘'].iloc[-1]
            high_n = hist['最高'].max()
            low_n = hist['最低'].min()
            position = calculate_position_in_range(close_current, high_n, low_n)
            return position < threshold
        except:
            return False


@SignalRegistry.register
class SmallBullish5Signal(SmallBullishBase):
    """底部连续5个小阳线信号."""
    
    signal_id = "small_bullish_5"
    display_name = "五连小阳"
    icon = "🌅"
    min_bars = 21
    priority = 70
    
    def detect(self, hist, stock_info) -> SignalResult:
        try:
            last_5 = hist.tail(5)
            if len(last_5) < 5:
                return SignalResult(triggered=False)
            
            prev_close = 0
            for i in range(5):
                row = last_5.iloc[i]
                if not self.is_small_bullish(row['开盘'], row['收盘'], stock_info):
                    return SignalResult(triggered=False)
                if i > 0 and row['收盘'] <= prev_close:
                    return SignalResult(triggered=False)
                prev_close = row['收盘']
            
            if not self.is_at_bottom(hist):
                return SignalResult(triggered=False)
            
            return SignalResult(triggered=True)
        except:
            return SignalResult(triggered=False)


@SignalRegistry.register
class SmallBullish4Signal(SmallBullishBase):
    """底部四连阳信号."""
    
    signal_id = "small_bullish_4"
    display_name = "四连小阳"
    icon = "🌅"
    min_bars = 21
    priority = 71
    
    def detect(self, hist, stock_info) -> SignalResult:
        try:
            last_4 = hist.tail(4)
            if len(last_4) < 4:
                return SignalResult(triggered=False)
            
            for i in range(4):
                row = last_4.iloc[i]
                if not self.is_small_bullish(row['开盘'], row['收盘'], stock_info):
                    return SignalResult(triggered=False)
            
            if not self.is_at_bottom(hist):
                return SignalResult(triggered=False)
            
            return SignalResult(triggered=True)
        except:
            return SignalResult(triggered=False)


@SignalRegistry.register
class SmallBullish4_1BearishSignal(SmallBullishBase):
    """四阳一阴信号."""
    
    signal_id = "small_bullish_4_1_bearish"
    display_name = "四阳一阴"
    icon = "🌅"
    min_bars = 21
    priority = 72
    
    def detect(self, hist, stock_info) -> SignalResult:
        try:
            last_5 = hist.tail(5)
            if len(last_5) < 5:
                return SignalResult(triggered=False)
            
            # First 4 days: small bullish
            for i in range(4):
                row = last_5.iloc[i]
                if not self.is_small_bullish(row['开盘'], row['收盘'], stock_info):
                    return SignalResult(triggered=False)
            
            # Today: bearish
            today = last_5.iloc[-1]
            if not is_bearish_candle(today['开盘'], today['收盘']):
                return SignalResult(triggered=False)
            
            if not self.is_at_bottom(hist):
                return SignalResult(triggered=False)
            
            return SignalResult(triggered=True)
        except:
            return SignalResult(triggered=False)


@SignalRegistry.register
class SmallBullish5_1BearishSignal(SmallBullishBase):
    """五阳一阴信号."""
    
    signal_id = "small_bullish_5_1_bearish"
    display_name = "五阳一阴"
    icon = "🌅"
    min_bars = 21
    priority = 73
    
    def detect(self, hist, stock_info) -> SignalResult:
        try:
            last_6 = hist.tail(6)
            if len(last_6) < 6:
                return SignalResult(triggered=False)
            
            # First 5 days: small bullish
            for i in range(5):
                row = last_6.iloc[i]
                if not self.is_small_bullish(row['开盘'], row['收盘'], stock_info):
                    return SignalResult(triggered=False)
            
            # Today: bearish
            today = last_6.iloc[-1]
            if not is_bearish_candle(today['开盘'], today['收盘']):
                return SignalResult(triggered=False)
            
            if not self.is_at_bottom(hist):
                return SignalResult(triggered=False)
            
            return SignalResult(triggered=True)
        except:
            return SignalResult(triggered=False)


@SignalRegistry.register
class SmallBullish3_1_1Signal(SmallBullishBase):
    """三阳一阴一阳信号."""
    
    signal_id = "small_bullish_3_1_bearish_1_bullish"
    display_name = "三阳一阴一阳"
    icon = "🌅"
    min_bars = 21
    priority = 74
    
    def detect(self, hist, stock_info) -> SignalResult:
        try:
            last_5 = hist.tail(5)
            if len(last_5) < 5:
                return SignalResult(triggered=False)
            
            # T-4 to T-2: small bullish
            for i in range(3):
                row = last_5.iloc[i]
                if not self.is_small_bullish(row['开盘'], row['收盘'], stock_info):
                    return SignalResult(triggered=False)
            
            # T-1: bearish
            yesterday = last_5.iloc[-2]
            if not is_bearish_candle(yesterday['开盘'], yesterday['收盘']):
                return SignalResult(triggered=False)
            
            # Today: bullish
            today = last_5.iloc[-1]
            if not is_bullish_candle(today['开盘'], today['收盘']):
                return SignalResult(triggered=False)
            
            if not self.is_at_bottom(hist):
                return SignalResult(triggered=False)
            
            return SignalResult(triggered=True)
        except:
            return SignalResult(triggered=False)


@SignalRegistry.register
class SmallBullish5In7Signal(SmallBullishBase):
    """七天五阳信号."""
    
    signal_id = "small_bullish_5_in_7"
    display_name = "七天五阳"
    icon = "🌅"
    min_bars = 21
    priority = 75
    
    def detect(self, hist, stock_info) -> SignalResult:
        try:
            last_7 = hist.tail(7)
            if len(last_7) < 7:
                return SignalResult(triggered=False)
            
            bullish_count = 0
            for i in range(7):
                row = last_7.iloc[i]
                if self.is_small_bullish(row['开盘'], row['收盘'], stock_info):
                    bullish_count += 1
            
            if bullish_count < 5:
                return SignalResult(triggered=False)
            
            if not self.is_at_bottom(hist):
                return SignalResult(triggered=False)
            
            return SignalResult(triggered=True, metadata={"bullish_count": bullish_count})
        except:
            return SignalResult(triggered=False)


@SignalRegistry.register
class SmallBullish6In7Signal(SmallBullishBase):
    """七天六阳信号."""
    
    signal_id = "small_bullish_6_in_7"
    display_name = "七天六阳"
    icon = "🌟"
    min_bars = 21
    priority = 76
    
    def detect(self, hist, stock_info) -> SignalResult:
        try:
            last_7 = hist.tail(7)
            if len(last_7) < 7:
                return SignalResult(triggered=False)
            
            bullish_count = 0
            for i in range(7):
                row = last_7.iloc[i]
                if is_bullish_candle(row['开盘'], row['收盘']):
                    bullish_count += 1
            
            if bullish_count < 6:
                return SignalResult(triggered=False)
            
            # Check trend up
            if last_7['收盘'].iloc[-1] <= last_7['收盘'].iloc[0]:
                return SignalResult(triggered=False)
            
            return SignalResult(triggered=True, metadata={"bullish_count": bullish_count})
        except:
            return SignalResult(triggered=False)
