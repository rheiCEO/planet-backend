import asyncio
import websockets
import json

async def test_endpoint(name, url):
    try:
        async with websockets.connect(url) as ws:
            print(f"[{name}] Connected.")
            msg1 = await ws.recv()
            print(f"[{name}] Msg 1: {msg1[:100]}...")
            msg2 = await ws.recv()
            print(f"[{name}] Msg 2: {msg2[:100]}...")
    except Exception as e:
        print(f"[{name}] ERROR: {e}")

async def main():
    await asyncio.gather(
        test_endpoint("FLIGHTS", "ws://127.0.0.1:8000/ws/flights"),
        test_endpoint("SHIPS", "ws://127.0.0.1:8000/ws/ships"),
        test_endpoint("CRISES", "ws://127.0.0.1:8000/ws/crises")
    )

if __name__ == "__main__":
    asyncio.run(main())
