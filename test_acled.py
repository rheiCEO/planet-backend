import httpx
import asyncio
import json

async def test_acled():
    url = "https://api.acleddata.com/acled/read"
    params = {
        "limit": 5,
        "format": "json"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=10.0)
            print(f"Status Code: {response.status_code}")
            data = response.json()
            print(json.dumps(data, indent=2))
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_acled())
