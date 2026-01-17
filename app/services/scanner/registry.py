"""
Signal Registry - Auto-discovery and registration of signal detectors.

Provides a centralized registry for all signal detectors with:
- Decorator-based registration
- Signal lookup by ID or group
- Icon and name mappings for UI
"""

from typing import Dict, List, Type, Optional
from .base import SignalDetector


class SignalRegistry:
    """Singleton registry for signal detectors.
    
    Usage:
        # Register a signal
        @SignalRegistry.register
        class MySignal(SignalDetector):
            signal_id = "my_signal"
            ...
        
        # Get all signals
        signals = SignalRegistry.get_all()
        
        # Get by ID
        signal = SignalRegistry.get_by_id("my_signal")
    """
    
    _signals: Dict[str, SignalDetector] = {}
    
    @classmethod
    def register(cls, signal_class: Type[SignalDetector]) -> Type[SignalDetector]:
        """Decorator to register a signal detector class.
        
        Args:
            signal_class: SignalDetector subclass to register
            
        Returns:
            The same class (for decorator chaining)
            
        Raises:
            ValueError: If signal_id is missing or duplicate
        """
        instance = signal_class()
        
        if not instance.signal_id:
            raise ValueError(
                f"Signal {signal_class.__name__} must define signal_id"
            )
        
        if instance.signal_id in cls._signals:
            raise ValueError(
                f"Duplicate signal_id: {instance.signal_id}"
            )
        
        cls._signals[instance.signal_id] = instance
        return signal_class
    
    @classmethod
    def get_all(cls, enabled_only: bool = True) -> List[SignalDetector]:
        """Get all registered signals sorted by priority.
        
        Args:
            enabled_only: If True, only return enabled signals
            
        Returns:
            List of SignalDetector instances
        """
        signals = list(cls._signals.values())
        if enabled_only:
            signals = [s for s in signals if s.enabled]
        return sorted(signals, key=lambda s: s.priority)
    
    @classmethod
    def get_by_id(cls, signal_id: str) -> Optional[SignalDetector]:
        """Get signal by ID.
        
        Args:
            signal_id: Signal identifier
            
        Returns:
            SignalDetector instance or None
        """
        return cls._signals.get(signal_id)
    
    @classmethod
    def get_by_group(cls, group: str, enabled_only: bool = True) -> List[SignalDetector]:
        """Get signals by group.
        
        Args:
            group: Signal group name
            enabled_only: If True, only return enabled signals
            
        Returns:
            List of SignalDetector instances in the group
        """
        signals = [s for s in cls._signals.values() if s.group == group]
        if enabled_only:
            signals = [s for s in signals if s.enabled]
        return sorted(signals, key=lambda s: s.priority)
    
    @classmethod
    def get_signal_ids(cls) -> List[str]:
        """Get all registered signal IDs."""
        return list(cls._signals.keys())
    
    @classmethod
    def get_icons(cls) -> Dict[str, str]:
        """Get signal ID to icon mapping."""
        return {s.signal_id: s.icon for s in cls._signals.values()}
    
    @classmethod
    def get_names(cls) -> Dict[str, str]:
        """Get signal ID to display name mapping."""
        return {s.signal_id: s.display_name for s in cls._signals.values()}
    
    @classmethod
    def count(cls) -> int:
        """Get total number of registered signals."""
        return len(cls._signals)
    
    @classmethod
    def clear(cls) -> None:
        """Clear all registered signals (for testing)."""
        cls._signals.clear()


# Convenience alias
registry = SignalRegistry
