import asyncio
import sys
import os
from pprint import pprint

# Add project root to path
sys.path.append(os.getcwd())

async def test_kuangbiao_scanner():
    try:
        from app.services.stock_scanner import StockScanner
        from app.core.database import db
        from app.services.scanner_utils import calculate_kuangbiao_score
        
        # Configure logger to output to console
        import logging
        logging.basicConfig(level=logging.INFO)
        
        # Connect to DB
        await db.connect()
        
        scanner = StockScanner()
        
        # Run scan
        print("\n🏎️ Starting Kuangbiao Scanner Test...\n")
        
        # We will scan ALL stocks but filter for Kuangbiao locally to show details for candidates
        # Re-using scan_all_stocks logic but focused
        
        # Fetch recent active stocks
        from app.core.timezone import china_today
        today = china_today()
        
        rows = await db.pool.fetch("""
            SELECT DISTINCT code
            FROM stock_history 
            WHERE date >= $1::date - INTERVAL '7 days'
              AND code ~ '^[036]'
        """, today)
        
        codes = [r['code'] for r in rows]
        print(f"📊 Found {len(codes)} stocks to scan.")
        
        # Get history
        # scan_all_stocks uses batching, let's do small batch for test or full if feasible
        # Just use scanner method if possible to test integration
        signals = await scanner.scan_all_stocks(force=True)
        
        kb_signals = signals.get("kuangbiao", [])
        print(f"\n🔥 Found {len(kb_signals)} Kuangbiao Signals:\n")
        
        if kb_signals:
            # Print details
            _, pd = scanner._get_libs()
            
            # Fetch history for verification details
            codes_to_check = [s['code'] for s in kb_signals]
            hist_map = await scanner._get_local_history_batch(codes_to_check)
            
            for s in kb_signals:
                code = s['code']
                name = s['name']
                print(f"🔹 {code} {name}")
                print(f"   Score A: {s.get('score_a', 'N/A')}")
                print(f"   Score B: {s.get('score_b', 'N/A')}")
                
                if code in hist_map:
                    df = hist_map[code]
                    # Verify manually by re-calc
                    sa, sb, st = calculate_kuangbiao_score(df)
                    print(f"   [Re-Calc] A: {sa}, B: {sb}, State: {st}")
                    print("-" * 40)
        else:
            print("No signals found. Trying to find high Score A candidates (Silent Accumulation)...")
             # Manual check for potential candidates
            _, pd = scanner._get_libs()
            sample_codes = codes[:500] # Check first 500
            hist_map = await scanner._get_local_history_batch(sample_codes)
            
            for code, df in hist_map.items():
                if len(df) < 120: continue
                sa, sb, st = calculate_kuangbiao_score(df)
                if sa >= 60:
                     print(f"👀 Watch Candidate: {code} ScoreA={sa} ScoreB={sb}")

        print("\n✅ Test Complete")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        # import traceback
        # traceback.print_exc()
    finally:
        await db.disconnect()

if __name__ == "__main__":
    asyncio.run(test_kuangbiao_scanner())
