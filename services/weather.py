import asyncio
import httpx
from fastapi import WebSocket, WebSocketDisconnect

WEATHER_CACHE = []

# Open-Meteo is free for non-commercial use and doesn't require an API key
# We will pull data for key coordinates around the world to visualize "Storms" or high precipitation.
# Let's define a grid of coordinates to check (e.g. major capitals/regions to keep it light)
WEATHER_POINTS = [
    {"lat": 52.2297, "lon": 21.0122,  "name": "Warsaw"},
    {"lat": 40.7128, "lon": -74.0060, "name": "New York"},
    {"lat": 51.5074, "lon": -0.1278,  "name": "London"},
    {"lat": 35.6762, "lon": 139.6503, "name": "Tokyo"},
    {"lat": -33.8688, "lon": 151.2093,"name": "Sydney"},
    {"lat": 1.3521,  "lon": 103.8198, "name": "Singapore"},
    {"lat": -23.5505, "lon": -46.6333,"name": "Sao Paulo"},
    {"lat": 28.6139, "lon": 77.2090,  "name": "New Delhi"},
    {"lat": 55.7558, "lon": 37.6173,  "name": "Moscow"},
    {"lat": -1.2921, "lon": 36.8219,  "name": "Nairobi"},
    # Add random ocean points to simulate maritime weather
    {"lat": 30.0,    "lon": -45.0,    "name": "North Atlantic"},
    {"lat": -20.0,   "lon": -80.0,    "name": "South Pacific"},
    {"lat": 15.0,    "lon": 65.0,     "name": "Arabian Sea"}
]

async def fetch_weather_data():
    results = []
    
    # Open-Meteo allows batching multiple coordinates in one request to save connections
    lats = ",".join([str(p["lat"]) for p in WEATHER_POINTS])
    lons = ",".join([str(p["lon"]) for p in WEATHER_POINTS])
    
    # We'll fetch current precipitation (mm) and wind speed (km/h)
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lats}&longitude={lons}&current=precipitation,wind_speed_10m&timezone=auto"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=10.0)
            response.raise_for_status()
            data = response.json()
            
            # Open-Meteo returns a list if multiple coords are passed
            if isinstance(data, list):
                for i, loc in enumerate(data):
                    current = loc.get("current", {})
                    precip = current.get("precipitation", 0)
                    wind = current.get("wind_speed_10m", 0)
                    
                    results.append({
                        "name": WEATHER_POINTS[i]["name"],
                        "latitude": WEATHER_POINTS[i]["lat"],
                        "longitude": WEATHER_POINTS[i]["lon"],
                        "precipitation": precip,
                        "wind_speed": wind,
                        # Classify severity
                        "severity": "High" if precip > 10 or wind > 50 else ("Medium" if precip > 2 or wind > 30 else "Low")
                    })
            
            return {"type": "weather_data", "data": results}
        except Exception as e:
            print(f"Error fetching weather data: {e}")
            return {"type": "error", "message": str(e)}

async def update_weather_cache():
    global WEATHER_CACHE
    while True:
        try:
            weather_data = await fetch_weather_data()
            if weather_data.get("type") == "weather_data":
                WEATHER_CACHE = weather_data.get("data", [])
                print(f"Updated WEATHER_CACHE: {len(WEATHER_CACHE)} regions")
        except Exception as e:
            print(f"Weather cache update error: {e}")
        await asyncio.sleep(1800) # Every 30 minutes for weather

async def websocket_weather_endpoint(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_json({"type": "info", "message": "Weather connected"})
    try:
        while True:
            try:
                await websocket.send_json({"type": "weather_data", "data": WEATHER_CACHE})
            except WebSocketDisconnect:
                print("Weather Client disconnected normally")
                break
            except Exception as e:
                print(f"Weather WS error: {e}")
                
            await asyncio.sleep(60)
    except Exception:
        pass
