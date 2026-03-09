import httpx
import asyncio

async def test_gdacs():
    url = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/MAP?eventlist=ALL"
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url)
            data = resp.json()
            features = data.get("features", [])
            print(f"Loaded {len(features)} active crises from GDACS")
            if features:
                for i in range(min(5, len(features))):
                    f = features[i]
                    print("Sample event:", f['properties']['name'], "- Type:", f['properties']['eventtype'], "- Alert:", f['properties'].get('alertlevel'))
        except Exception as e:
            print(f"Error: {e}")

asyncio.run(test_gdacs())
