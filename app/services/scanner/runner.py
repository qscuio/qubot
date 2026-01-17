"""
Signal Scanner Runner - Executes signal detection across stocks.

Provides the main scanning function that:
- Loads data from database
- Runs all registered signals
- Aggregates results
- Supports progress callbacks
"""

import asyncio
from typing import Dict, List, Any, Optional, Callable
import pandas as pd

from app.core.logger import Logger
from .registry import SignalRegistry
from .base import SignalDetector

logger = Logger("ScannerRunner")


async def run_scan(
    stocks_data: Dict[str, pd.DataFrame],
    stock_names: Dict[str, str],
    progress_callback: Optional[Callable] = None,
    enabled_signals: Optional[List[str]] = None,
    batch_yield_interval: int = 10,
) -> Dict[str, List[Dict[str, Any]]]:
    """Execute signal detection across all stocks.
    
    Args:
        stocks_data: Dict mapping code -> DataFrame with OHLCV data
        stock_names: Dict mapping code -> display name
        progress_callback: Async callback(checked, total) for progress updates
        enabled_signals: List of signal IDs to run (None = all enabled)
        batch_yield_interval: Yield to event loop every N stocks
        
    Returns:
        Dict mapping signal_id -> list of matching stock dicts
    """
    # Get signals to run
    all_signals = SignalRegistry.get_all(enabled_only=True)
    
    if enabled_signals:
        signals = [s for s in all_signals if s.signal_id in enabled_signals]
    else:
        signals = all_signals
    
    if not signals:
        logger.warn("No signals registered or enabled")
        return {}
    
    logger.info(f"Running scan with {len(signals)} signals on {len(stocks_data)} stocks")
    
    # Initialize results
    results: Dict[str, List[Dict[str, Any]]] = {s.signal_id: [] for s in signals}
    results["multi_signal"] = []
    
    total = len(stocks_data)
    checked = 0
    skipped = 0
    
    for code, hist in stocks_data.items():
        name = stock_names.get(code, code)
        stock_info = {"code": code, "name": name}
        
        # Skip if insufficient data
        if len(hist) < 21:
            skipped += 1
            continue
        
        signal_count = 0
        
        # Run each signal
        for signal in signals:
            # Skip if not enough data for this signal
            if len(hist) < signal.min_bars:
                continue
            
            try:
                result = signal.detect(hist, stock_info)
                
                if result.triggered:
                    entry = {**stock_info}
                    if result.metadata:
                        entry.update(result.metadata)
                    results[signal.signal_id].append(entry)
                    
                    if signal.count_in_multi:
                        signal_count += 1
                        
            except Exception as e:
                logger.debug(f"Signal {signal.signal_id} error on {code}: {e}")
        
        # Multi-signal stock
        if signal_count >= 3:
            results["multi_signal"].append({
                **stock_info,
                "signal_count": signal_count
            })
        
        checked += 1
        
        # Progress callback
        if progress_callback and checked % 50 == 0:
            try:
                await progress_callback(checked, total)
            except Exception:
                pass
        
        # Yield to event loop periodically
        if checked % batch_yield_interval == 0:
            await asyncio.sleep(0)
    
    # Log summary
    total_signals = sum(len(v) for v in results.values())
    logger.info(f"Scan complete: {checked} stocks, {skipped} skipped, {total_signals} signals")
    
    # Final progress update
    if progress_callback:
        try:
            await progress_callback(total, total)
        except Exception:
            pass
    
    for sig_id, matches in results.items():
        if matches:
            logger.debug(f"  {sig_id}: {len(matches)} matches")
    
    return results


async def run_single_signal(
    signal_id: str,
    stocks_data: Dict[str, pd.DataFrame],
    stock_names: Dict[str, str],
    progress_callback: Optional[Callable] = None,
) -> List[Dict[str, Any]]:
    """Run a single signal across all stocks.
    
    Args:
        signal_id: ID of signal to run
        stocks_data: Dict mapping code -> DataFrame
        stock_names: Dict mapping code -> name
        progress_callback: Optional progress callback
        
    Returns:
        List of matching stock dicts
    """
    signal = SignalRegistry.get_by_id(signal_id)
    if not signal:
        logger.error(f"Signal not found: {signal_id}")
        return []
    
    results = await run_scan(
        stocks_data,
        stock_names,
        progress_callback,
        enabled_signals=[signal_id]
    )
    
    return results.get(signal_id, [])


def get_signal_info() -> Dict[str, Dict[str, Any]]:
    """Get metadata for all registered signals.
    
    Returns:
        Dict mapping signal_id -> {icon, name, group, enabled}
    """
    return {
        s.signal_id: {
            "icon": s.icon,
            "name": s.display_name,
            "group": s.group,
            "enabled": s.enabled,
            "min_bars": s.min_bars,
            "priority": s.priority,
        }
        for s in SignalRegistry.get_all(enabled_only=False)
    }
