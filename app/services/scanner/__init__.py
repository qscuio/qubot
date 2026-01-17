"""
Scanner Module - Modular signal detection system.

This package provides a pluggable architecture for stock signal detection:
- Each signal is a separate class inheriting from SignalDetector
- Signals auto-register using the @SignalRegistry.register decorator
- The runner executes all registered signals across stock data

Usage:
    from app.services.scanner import run_scan, SignalRegistry
    
    # Get all registered signals
    signals = SignalRegistry.get_all()
    
    # Run scan
    results = await run_scan(stocks_data, stock_names)
"""

from .base import SignalDetector, SignalResult
from .registry import SignalRegistry, registry
from .runner import run_scan, run_single_signal, get_signal_info

# Import all signals to trigger registration
from . import signals

__all__ = [
    # Base classes
    "SignalDetector",
    "SignalResult",
    
    # Registry
    "SignalRegistry",
    "registry",
    
    # Runner
    "run_scan",
    "run_single_signal",
    "get_signal_info",
]
