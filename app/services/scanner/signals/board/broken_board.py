"""Broken Board Signals - Limit-up streak broken patterns."""

from app.services.scanner.base import SignalDetector, SignalResult
from app.services.scanner.registry import SignalRegistry
from app.services.scanner.utils import is_limit_up


class BrokenBoardBase(SignalDetector):
    """Base class for broken board signals."""
    group = "board"
    
    def check_limit_up(self, prev_close: float, close: float, stock_info: dict) -> bool:
        """Check if daily move is limit up (board-aware)."""
        return is_limit_up(
            prev_close,
            close,
            code=stock_info.get("code"),
            name=stock_info.get("name"),
        )


@SignalRegistry.register
class BrokenLimitUpStreakSignal(BrokenBoardBase):
    """连板断板信号 - T-2和T-1涨停，T不涨停."""
    
    signal_id = "broken_limit_up_streak"
    display_name = "连板断板"
    icon = "🏚️"
    min_bars = 5
    priority = 90
    
    def detect(self, hist, stock_info) -> SignalResult:
        try:
            if len(hist) < 4:
                return SignalResult(triggered=False)
            
            closes = hist['收盘'].values
            
            # T-2 and T-1 were limit up
            t_3_close = closes[-4]
            t_2_close = closes[-3]
            t_1_close = closes[-2]
            t_0_close = closes[-1]
            
            # T-2: limit up from T-3
            if not self.check_limit_up(t_3_close, t_2_close, stock_info):
                return SignalResult(triggered=False)
            
            # T-1: limit up from T-2
            if not self.check_limit_up(t_2_close, t_1_close, stock_info):
                return SignalResult(triggered=False)
            
            # T: NOT limit up
            if self.check_limit_up(t_1_close, t_0_close, stock_info):
                return SignalResult(triggered=False)
            
            return SignalResult(triggered=True)
            
        except Exception:
            return SignalResult(triggered=False)


@SignalRegistry.register
class YesterdayBrokenBoardSignal(BrokenBoardBase):
    """昨日断板信号 - T-3和T-2涨停，T-1不涨停."""
    
    signal_id = "yesterday_broken_board"
    display_name = "昨日断板"
    icon = "🏚️"
    min_bars = 5
    priority = 91
    
    def detect(self, hist, stock_info) -> SignalResult:
        try:
            if len(hist) < 5:
                return SignalResult(triggered=False)
            
            closes = hist['收盘'].values
            
            # T-3 and T-2 were limit up
            t_4_close = closes[-5]
            t_3_close = closes[-4]
            t_2_close = closes[-3]
            t_1_close = closes[-2]
            
            # T-3: limit up from T-4
            if not self.check_limit_up(t_4_close, t_3_close, stock_info):
                return SignalResult(triggered=False)
            
            # T-2: limit up from T-3
            if not self.check_limit_up(t_3_close, t_2_close, stock_info):
                return SignalResult(triggered=False)
            
            # T-1: NOT limit up (broken yesterday)
            if self.check_limit_up(t_2_close, t_1_close, stock_info):
                return SignalResult(triggered=False)
            
            return SignalResult(triggered=True)
            
        except Exception:
            return SignalResult(triggered=False)


@SignalRegistry.register
class DayBeforeYesterdayBrokenBoardSignal(BrokenBoardBase):
    """前日断板信号 - T-4和T-3涨停，T-2不涨停."""
    
    signal_id = "day_before_yesterday_broken_board"
    display_name = "前日断板"
    icon = "🏚️"
    min_bars = 6
    priority = 92
    
    def detect(self, hist, stock_info) -> SignalResult:
        try:
            if len(hist) < 6:
                return SignalResult(triggered=False)
            
            closes = hist['收盘'].values
            
            # T-4 and T-3 were limit up
            t_5_close = closes[-6]
            t_4_close = closes[-5]
            t_3_close = closes[-4]
            t_2_close = closes[-3]
            
            # T-4: limit up from T-5
            if not self.check_limit_up(t_5_close, t_4_close, stock_info):
                return SignalResult(triggered=False)
            
            # T-3: limit up from T-4
            if not self.check_limit_up(t_4_close, t_3_close, stock_info):
                return SignalResult(triggered=False)
            
            # T-2: NOT limit up (broken day before yesterday)
            if self.check_limit_up(t_3_close, t_2_close, stock_info):
                return SignalResult(triggered=False)
            
            return SignalResult(triggered=True)
            
        except Exception:
            return SignalResult(triggered=False)
