import asyncio
import akshare as ak
from datetime import datetime

async def test():
    print(f"Testing AkShare at {datetime.now()}")
    try:
        df = await asyncio.to_thread(ak.stock_zh_a_spot_em)
        if df is None or df.empty:
            print("❌ Result is empty")
        else:
            print(f"✅ Success! Got {len(df)} rows.")
            print(df.head(3))
    except Exception as e:
        print(f"❌ Exception: {e}")

if __name__ == "__main__":
    asyncio.run(test())
