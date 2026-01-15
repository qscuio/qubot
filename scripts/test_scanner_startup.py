import asyncio
import sys
import os
from pprint import pprint

# Add project root to path
sys.path.append(os.getcwd())

async def test_startup_scanner():
    try:
        from app.services.stock_scanner import StockScanner
        from app.core.database import db
        from app.core.config import settings
        from app.core.logger import Logger
        
        # Configure logger to output to console
        import logging
        logging.basicConfig(level=logging.INFO)
        
        # Connect to DB
        await db.connect()
        
        scanner = StockScanner()
        
        # Run scan
        print("\n🚀 Starting Startup Phase Scanner Test...\n")
        signals = await scanner.scan_all_stocks(force=True)
        
        startup_candidates = signals.get("startup_candidate", [])
        
        print(f"\n📊 Found {len(startup_candidates)} Startup Candidates:\n")
        
        if startup_candidates:
            # Print details for first 5 candidates
            _, pd = scanner._get_libs()
            
            # Fetch history for verification
            codes = [s['code'] for s in startup_candidates[:15]]
            hist_map = await scanner._get_local_history_batch(codes)
            
            for s in startup_candidates:
                code = s['code']
                name = s['name']
                print(f"🔹 {code} {name}")
                
                if code in hist_map:
                    df = hist_map[code]
                    print(f"   Last Close: {df['收盘'].iloc[-1]}")
                    print(f"   Last Vol: {df['成交量'].iloc[-1]}")
                    print(f"   Turnover: {df['换手率'].iloc[-1]}%")
                    
                    # Verify key metrics
                    closes = df['收盘']
                    ma20 = closes.rolling(20).mean().iloc[-1]
                    ma60 = closes.rolling(60).mean().iloc[-1]
                    ma200 = closes.rolling(200).mean().iloc[-1] if len(closes) >= 200 else float('nan')
                    
                    print(f"   MA20: {ma20:.2f}, MA60: {ma60:.2f}, MA200: {ma200:.2f}")
                    print("-" * 40)

        print("\n✅ Test Complete")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await db.disconnect()

if __name__ == "__main__":
    asyncio.run(test_startup_scanner())
