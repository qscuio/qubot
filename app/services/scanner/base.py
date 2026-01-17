"""
Signal Detector Base Classes.

This module defines the core abstractions for the modular signal detection system.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import pandas as pd


@dataclass
class SignalResult:
    """Result of signal detection.
    
    Attributes:
        triggered: Whether the signal was triggered
        metadata: Optional additional data (score, reason, etc.)
    """
    triggered: bool
    metadata: Optional[Dict[str, Any]] = field(default_factory=dict)


class SignalDetector(ABC):
    """Base class for all signal detectors.
    
    All signal detectors must inherit from this class and implement the detect() method.
    Signals are automatically registered when decorated with @SignalRegistry.register.
    
    Class Attributes:
        signal_id: Unique identifier for the signal (required)
        display_name: Human-readable name
        icon: Emoji icon for display
        group: Category group (pattern, volume, trend, momentum, board)
        enabled: Whether the signal is active
        min_bars: Minimum data history required (days)
        priority: Execution order (lower = earlier)
        count_in_multi: Include in multi-signal count
    
    Example:
        @SignalRegistry.register
        class MySignal(SignalDetector):
            signal_id = "my_signal"
            display_name = "My Signal"
            icon = "🔍"
            group = "pattern"
            
            def detect(self, hist, stock_info):
                # Detection logic
                return SignalResult(triggered=True)
    """
    
    # Required: Unique signal identifier
    signal_id: str = ""
    
    # Display name for UI
    display_name: str = ""
    
    # Emoji icon
    icon: str = "•"
    
    # Signal category
    group: str = "other"
    
    # Whether signal is active
    enabled: bool = True
    
    # Minimum data bars required
    min_bars: int = 21
    
    # Execution priority (lower = earlier)
    priority: int = 100
    
    # Include in multi-signal count
    count_in_multi: bool = True

    @abstractmethod
    def detect(self, hist: pd.DataFrame, stock_info: Dict[str, Any]) -> SignalResult:
        """Detect signal in stock data.
        
        Args:
            hist: DataFrame with columns: 收盘, 开盘, 最高, 最低, 成交量, 换手率
            stock_info: Dict with keys: code, name
        
        Returns:
            SignalResult with triggered state and optional metadata
        """
        pass
    
    def __repr__(self) -> str:
        return f"<Signal:{self.signal_id}>"
    
    def __str__(self) -> str:
        return f"{self.icon} {self.display_name}"
