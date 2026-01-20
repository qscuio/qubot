#!/usr/bin/env python3
"""
Stock Scanner Performance Profiler

This script profiles the scanner to identify performance bottlenecks without
modifying any existing production code.

Usage (run on VPS where the service is running):
    cd /path/to/qubot
    source .venv/bin/activate
    python scripts/profile_scanner.py [--full] [--signal SIGNAL_ID] [--stocks N]

Arguments:
    --full          Run full profile with all signals (takes longer)
    --signal ID     Profile specific signal only
    --stocks N      Limit to N stocks for faster testing (default: 500)
"""

import asyncio
import sys
import os
import time
import argparse
import cProfile
import pstats
import io
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(project_root, ".env"))
except ImportError:
    print("Warning: python-dotenv not installed, using existing env vars")


@dataclass
class TimingResult:
    """Store timing results for a phase."""
    name: str
    duration: float
    count: int = 1
    details: Dict = field(default_factory=dict)


class ScannerProfiler:
    """Profile stock scanner performance."""
    
    def __init__(self, stock_limit: int = 500, verbose: bool = True):
        self.stock_limit = stock_limit
        self.verbose = verbose
        self.timings: List[TimingResult] = []
        self.signal_timings: Dict[str, List[float]] = defaultdict(list)
        
    @contextmanager
    def timer(self, name: str, details: Dict = None):
        """Context manager for timing code blocks."""
        start = time.perf_counter()
        yield
        elapsed = time.perf_counter() - start
        self.timings.append(TimingResult(name, elapsed, 1, details or {}))
        if self.verbose:
            print(f"  ⏱️  {name}: {elapsed:.3f}s")

    async def profile_db_connection(self) -> bool:
        """Profile database connection time."""
        from app.core.database import db
        from app.core.config import settings
        
        print(f"     DATABASE_URL configured: {bool(settings.DATABASE_URL)}")
        
        with self.timer("Database Connection"):
            await db.connect()
        
        return db.pool is not None
    
    async def profile_stock_list_query(self) -> List[str]:
        """Profile fetching the stock list."""
        from app.core.database import db
        from app.core.timezone import china_today
        
        today = china_today()
        
        with self.timer("Fetch Stock List (DISTINCT codes)"):
            rows = await db.pool.fetch("""
                SELECT DISTINCT code
                FROM stock_history 
                WHERE date >= $1::date - INTERVAL '7 days'
                  AND code ~ '^[036]'
            """, today)
        
        codes = [r['code'] for r in rows]
        print(f"     📊 Found {len(codes)} stocks with recent data")
        
        if self.stock_limit and len(codes) > self.stock_limit:
            codes = codes[:self.stock_limit]
            print(f"     ⚠️  Limited to {self.stock_limit} stocks for profiling")
        
        return codes
    
    async def profile_history_batch_load(self, codes: List[str], limit: int = 150) -> Dict:
        """Profile batch history loading."""
        from app.core.database import db
        from collections import defaultdict
        import pandas as pd
        
        batch_size = 300
        total_codes = len(codes)
        total_batches = (total_codes + batch_size - 1) // batch_size
        min_rows = 21
        
        result = {}
        batch_times = []
        
        with self.timer("Total History Load", {"codes": total_codes, "batches": total_batches}):
            for batch_start in range(0, total_codes, batch_size):
                batch_codes = codes[batch_start:batch_start + batch_size]
                
                batch_start_time = time.perf_counter()
                
                rows = await db.pool.fetch("""
                    SELECT code, date, open, high, low, close, volume, turnover_rate
                    FROM (
                        SELECT code, date, open, high, low, close, volume, turnover_rate,
                               ROW_NUMBER() OVER (PARTITION BY code ORDER BY date DESC) AS rn
                        FROM stock_history
                        WHERE code = ANY($1)
                    ) t
                    WHERE rn <= $2
                    ORDER BY code, date DESC
                """, batch_codes, limit)
                
                # Process rows into DataFrames
                by_code = defaultdict(list)
                for row in rows:
                    by_code[row['code']].append(row)
                
                for code, code_rows in by_code.items():
                    if len(code_rows) >= min_rows:
                        df = pd.DataFrame([{
                            '日期': r['date'],
                            '开盘': float(r['open']),
                            '收盘': float(r['close']),
                            '最高': float(r['high']),
                            '最低': float(r['low']),
                            '成交量': float(r['volume']),
                            '换手率': float(r['turnover_rate']) if r['turnover_rate'] is not None else 0.0,
                        } for r in code_rows])
                        df = df.sort_values('日期').reset_index(drop=True)
                        result[code] = df
                
                batch_time = time.perf_counter() - batch_start_time
                batch_times.append(batch_time)
                
                # Yield to event loop
                await asyncio.sleep(0)
        
        if batch_times:
            avg_batch_time = sum(batch_times) / len(batch_times)
            print(f"     📦 Loaded {len(result)} valid stocks")
            print(f"     📦 Avg batch time: {avg_batch_time:.3f}s ({len(batch_times)} batches)")
        
        return result

    async def profile_individual_signals(self, stocks_data: Dict, stock_names: Dict, enabled_signals: List[str] = None):
        """Profile each signal's performance individually."""
        from app.services.scanner.registry import SignalRegistry
        
        signals = SignalRegistry.get_all(enabled_only=True)
        if enabled_signals:
            signals = [s for s in signals if s.signal_id in enabled_signals]
        
        print(f"\n📡 Profiling {len(signals)} signals individually...")
        print("=" * 60)
        
        signal_results = []
        
        for signal in signals:
            times = []
            matches = 0
            errors = 0
            
            start = time.perf_counter()
            
            for code, hist in stocks_data.items():
                name = stock_names.get(code, code)
                stock_info = {"code": code, "name": name}
                
                if len(hist) < signal.min_bars:
                    continue
                
                try:
                    sig_start = time.perf_counter()
                    result = signal.detect(hist, stock_info)
                    sig_time = time.perf_counter() - sig_start
                    times.append(sig_time)
                    
                    if result.triggered:
                        matches += 1
                except Exception as e:
                    errors += 1
            
            total_time = time.perf_counter() - start
            avg_time = sum(times) / len(times) if times else 0
            
            signal_results.append({
                'signal_id': signal.signal_id,
                'display_name': signal.display_name,
                'total_time': total_time,
                'avg_per_stock': avg_time,
                'stocks_checked': len(times),
                'matches': matches,
                'errors': errors,
            })
            
            # Store for aggregation
            self.signal_timings[signal.signal_id] = times
        
        # Sort by total time (slowest first)
        signal_results.sort(key=lambda x: x['total_time'], reverse=True)
        
        print("\n📊 Signal Performance (sorted by total time):")
        print("-" * 80)
        print(f"{'Signal':<35} {'Total(s)':<10} {'Avg(ms)':<10} {'Stocks':<8} {'Matches':<8}")
        print("-" * 80)
        
        for r in signal_results:
            print(f"{r['display_name']:<35} {r['total_time']:<10.3f} {r['avg_per_stock']*1000:<10.3f} {r['stocks_checked']:<8} {r['matches']:<8}")
        
        return signal_results
    
    async def profile_full_scan(self, stocks_data: Dict, stock_names: Dict, enabled_signals: List[str] = None):
        """Profile the run_scan function as a whole."""
        from app.services.scanner.runner import run_scan
        
        with self.timer("Full run_scan()", {"stocks": len(stocks_data), "signals": "all" if not enabled_signals else len(enabled_signals)}):
            results = await run_scan(
                stocks_data,
                stock_names,
                progress_callback=None,
                enabled_signals=enabled_signals
            )
        
        total_signals = sum(len(v) for v in results.values())
        print(f"     🎯 Found {total_signals} total signals")
        
        return results
    
    async def profile_top_gainers(self, stocks_data: Dict, stock_names: Dict):
        """Profile top gainers calculation."""
        from app.services.stock_scanner import StockScanner
        
        scanner = StockScanner()
        
        with self.timer("Calculate Top Gainers"):
            results = await scanner._calculate_top_gainers(stocks_data, stock_names)
        
        total = sum(len(v) for v in results.values())
        print(f"     📈 Calculated {total} top gainer entries")
        
        return results
    
    def print_summary(self):
        """Print timing summary."""
        print("\n" + "=" * 70)
        print("📋 PERFORMANCE SUMMARY")
        print("=" * 70)
        
        total_time = sum(t.duration for t in self.timings)
        
        # Group by phase
        print(f"\n{'Phase':<40} {'Time (s)':<12} {'%':<8}")
        print("-" * 60)
        
        for t in self.timings:
            pct = (t.duration / total_time * 100) if total_time > 0 else 0
            bar = "█" * int(pct / 5)
            print(f"{t.name:<40} {t.duration:<12.3f} {pct:<6.1f}% {bar}")
        
        print("-" * 60)
        print(f"{'TOTAL':<40} {total_time:<12.3f}")
        
        # Identify bottlenecks
        print("\n🔍 BOTTLENECK ANALYSIS:")
        print("-" * 60)
        
        sorted_timings = sorted(self.timings, key=lambda x: x.duration, reverse=True)
        for i, t in enumerate(sorted_timings[:3], 1):
            pct = (t.duration / total_time * 100) if total_time > 0 else 0
            print(f"  #{i} {t.name}: {t.duration:.3f}s ({pct:.1f}%)")
            if t.details:
                for k, v in t.details.items():
                    print(f"      - {k}: {v}")
        
        # Signal analysis if available
        if self.signal_timings:
            print("\n🐢 SLOWEST 5 SIGNALS (by total time per stock):")
            print("-" * 60)
            
            signal_totals = {
                sig_id: (sum(times), len(times), sum(times)/len(times) if times else 0)
                for sig_id, times in self.signal_timings.items()
            }
            sorted_signals = sorted(signal_totals.items(), key=lambda x: x[1][0], reverse=True)
            
            for sig_id, (total, count, avg) in sorted_signals[:5]:
                print(f"  {sig_id}: {total:.3f}s total, {avg*1000:.2f}ms avg per stock")
        
        # Recommendations
        print("\n💡 OPTIMIZATION RECOMMENDATIONS:")
        print("-" * 60)
        
        if self.timings:
            db_time = sum(t.duration for t in self.timings if "History Load" in t.name or "Stock List" in t.name)
            signal_time = sum(t.duration for t in self.timings if "Signal" in t.name or "run_scan" in t.name)
            
            if db_time > signal_time * 2:
                print("  ⚠️  Database I/O is the main bottleneck")
                print("     → Consider Redis caching (already implemented)")
                print("     → Consider preloading data at startup")
                print("     → Consider PostgreSQL query optimization (EXPLAIN ANALYZE)")
            elif signal_time > db_time * 2:
                print("  ⚠️  Signal computation is the main bottleneck")
                print("     → Consider Numba JIT for hot loops")
                print("     → Consider parallel signal execution")
                print("     → Consider Polars instead of Pandas")
            else:
                print("  ✅ Workload is balanced between I/O and computation")


async def main():
    parser = argparse.ArgumentParser(description="Profile stock scanner performance")
    parser.add_argument("--full", action="store_true", help="Run full scan with all signals")
    parser.add_argument("--signal", type=str, help="Profile specific signal only")
    parser.add_argument("--stocks", type=int, default=500, help="Limit stocks for testing (default: 500)")
    parser.add_argument("--cprofile", action="store_true", help="Also run cProfile for detailed breakdown")
    args = parser.parse_args()
    
    print("=" * 70)
    print("🔬 STOCK SCANNER PERFORMANCE PROFILER")
    print("=" * 70)
    print(f"Stock limit: {args.stocks}")
    print(f"Full scan: {args.full}")
    if args.signal:
        print(f"Target signal: {args.signal}")
    print()
    
    profiler = ScannerProfiler(stock_limit=args.stocks if not args.full else None)
    
    try:
        # Phase 1: Database connection
        print("\n📌 Phase 1: Database Connection")
        if not await profiler.profile_db_connection():
            print("❌ Failed to connect to database")
            print("   Make sure DATABASE_URL is set in .env or environment")
            return
        
        # Phase 2: Stock list query
        print("\n📌 Phase 2: Stock List Query")
        codes = await profiler.profile_stock_list_query()
        
        if not codes:
            print("❌ No stocks found")
            return
        
        # Phase 3: History batch load
        print("\n📌 Phase 3: History Data Loading")
        stocks_data = await profiler.profile_history_batch_load(codes)
        
        # Get stock names
        from app.core.database import db
        stock_names = {code: code for code in stocks_data.keys()}
        try:
            name_rows = await db.pool.fetch("""
                SELECT code, name FROM stock_info WHERE code = ANY($1)
            """, list(stocks_data.keys()))
            for row in name_rows:
                if row.get('name'):
                    stock_names[row['code']] = row['name']
        except Exception:
            pass
        
        # Phase 4: Signal profiling
        enabled_signals = [args.signal] if args.signal else None
        
        print("\n📌 Phase 4: Individual Signal Profiling")
        await profiler.profile_individual_signals(stocks_data, stock_names, enabled_signals)
        
        # Phase 5: Full scan (if requested or limited signals)
        if args.full or args.signal:
            print("\n📌 Phase 5: Full Scan Execution")
            await profiler.profile_full_scan(stocks_data, stock_names, enabled_signals)
        
        # Phase 6: Top gainers
        print("\n📌 Phase 6: Top Gainers Calculation")
        await profiler.profile_top_gainers(stocks_data, stock_names)
        
        # Print summary
        profiler.print_summary()
        
        # Optional: cProfile detailed breakdown
        if args.cprofile:
            print("\n" + "=" * 70)
            print("📊 CPROFILE DETAILED BREAKDOWN (top 30 functions)")
            print("=" * 70)
            
            pr = cProfile.Profile()
            pr.enable()
            
            # Run a quick scan for cProfile
            from app.services.scanner.runner import run_scan
            await run_scan(stocks_data, stock_names, enabled_signals=enabled_signals)
            
            pr.disable()
            s = io.StringIO()
            ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
            ps.print_stats(30)
            print(s.getvalue())
        
    except Exception as e:
        print(f"❌ Error during profiling: {e}")
        import traceback
        traceback.print_exc()
    finally:
        from app.core.database import db
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
