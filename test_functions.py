import asyncio
import time
from services.country_data import fetch_stock, fetch_news, fetch_currency, get_live_country_data

async def main():
    print("Testing fetch_currency...")
    t0 = time.time()
    try:
        res = await asyncio.wait_for(fetch_currency("pln"), timeout=5)
        print("Currency:", res, f"Took {time.time()-t0:.2f}s")
    except Exception as e:
        print("Currency error:", e)

    print("Testing fetch_stock...")
    t0 = time.time()
    try:
        res = await asyncio.wait_for(fetch_stock("POL"), timeout=5)
        print("Stock:", res, f"Took {time.time()-t0:.2f}s")
    except Exception as e:
        print("Stock error:", e)

    print("Testing fetch_news...")
    t0 = time.time()
    try:
        res = await asyncio.wait_for(fetch_news("Poland"), timeout=5)
        print("News:", res, f"Took {time.time()-t0:.2f}s")
    except Exception as e:
        print("News error:", e)

if __name__ == "__main__":
    asyncio.run(main())
