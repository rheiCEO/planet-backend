import httpx
import asyncio

async def test():
    async with httpx.AsyncClient() as client:
        # First get a plane callsign
        resp = await client.get("https://opensky-network.org/api/states/all")
        data = resp.json()
        for s in data['states'][:5]:
            callsign = s[1].strip() if s[1] else ""
            if callsign:
                print(f"Testing callsign: {callsign}")
                # Try routes API
                try:
                    route_resp = await client.get(f"https://opensky-network.org/api/routes?callsign={callsign}")
                    print(f"Status: {route_resp.status_code}")
                    print(route_resp.text)
                except Exception as e:
                    print(f"Error: {e}")
                break

asyncio.run(test())
