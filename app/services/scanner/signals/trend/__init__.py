"""Trend Signals - MA, pullback, linear regression, and pivot-based signals."""
from .ma_bullish import MABullishSignal
from .ma_pullback import MAPullbackMA5Signal, MAPullbackMA20Signal, MAPullbackMA30Signal, MAPullbackMA5WeeklySignal
from .linreg import LinRegSupport5Signal, LinRegSupport10Signal, LinRegSupport20Signal
from .linreg import LinRegBreakout5Signal, LinRegBreakout10Signal, LinRegBreakout20Signal
from .downtrend_reversal import DowntrendReversalSignal
from .uptrend_breakout import UptrendBreakoutSignal
from .strong_pullback import StrongPullbackSignal
