from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import json
import asyncio
import httpx
from dotenv import load_dotenv
import os
import requests
from bs4 import BeautifulSoup
from geopy.geocoders import Nominatim

from services.weather import update_weather_cache
from services.ships import maintain_ships_cache
from services.country_data import get_live_country_data
from services.iss import router as iss_router

load_dotenv()

# Global Caches
FLIGHTS_CACHE = []
CRISES_CACHE = []
CONFLICTS_CACHE = []

# OpenSky API endpoint for all states (bounding box can be added later)
OPENSKY_URL = "https://opensky-network.org/api/states/all"
# GDACS API (Crises and Disasters)
GDACS_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/MAP?eventlist=ALL"

async def update_flights_cache():
    global FLIGHTS_CACHE
    while True:
        try:
            flight_data = await fetch_flight_data()
            if flight_data.get("type") == "flight_data":
                FLIGHTS_CACHE = flight_data.get("data", [])
                print(f"Updated FLIGHTS_CACHE: {len(FLIGHTS_CACHE)} planes")
        except Exception as e:
            print(f"Flights cache update error: {e}")
        await asyncio.sleep(300) # Every 5 minutes

async def update_crises_cache():
    global CRISES_CACHE
    while True:
        try:
            crises_data = await fetch_gdacs_data()
            if crises_data.get("type") == "crises_data":
                CRISES_CACHE = crises_data.get("data", [])
                print(f"Updated CRISES_CACHE: {len(CRISES_CACHE)} events")
        except Exception as e:
            print(f"Crises cache update error: {e}")
        await asyncio.sleep(900) # Every 15 minutes

async def fetch_wiki_conflicts():
    url = "https://en.wikipedia.org/wiki/List_of_ongoing_armed_conflicts"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
    }
    try:
        res = requests.get(url, headers=headers)
        res.raise_for_status()

        soup = BeautifulSoup(res.text, 'html.parser')
        tables = soup.find_all('table', {'class': 'wikitable'})
        
        raw_conflicts = []
        import re
        
        for table in tables:
            rows = table.find_all('tr')
            for row in rows[1:]:
                cols = row.find_all('td')
                if len(cols) >= 3:
                    # Find the first real link in the conflict column to avoid concatenating sub-conflicts
                    a_tag = cols[1].find('a')
                    if a_tag and a_tag.get('href', '').startswith('/wiki/'):
                        conflict_name = a_tag.text.strip()
                        wiki_url = "https://en.wikipedia.org" + a_tag['href']
                    else:
                        conflict_name = cols[1].text.strip().split('\n')[0] # Fallback to first line
                        wiki_url = f"https://en.wikipedia.org/wiki/{conflict_name.replace(' ', '_')}"
                        
                    location = cols[3].text.strip() if len(cols) > 3 else cols[2].text.strip()
                    
                    conflict_name = re.sub(r'\[\d+\]', '', conflict_name)
                    location = re.sub(r'\[\d+\]', '', location)
                    location = location.replace('\n', ', ')
                    
                    if conflict_name and location:
                        raw_conflicts.append({
                            "name": conflict_name,
                            "location": location,
                            "url": wiki_url
                        })
                        
        print(f"Scraped {len(raw_conflicts)} conflicts from Wikipedia.")
        
        # Geocode locations
        geolocator = Nominatim(user_agent="planet_tracker_conflicts")
        geocoded_results = []
        
        # Limit to first 40 major conflicts to respect Nominatim free usage limits (1 req/s)
        for c in raw_conflicts[:40]:
            # Clean up complex locations like "Myanmar India Bangladesh" -> "Myanmar"
            primary_location = c['location'].split(',')[0].split(' ')[0] 
            try:
                location_data = geolocator.geocode(primary_location)
                if location_data:
                    geocoded_results.append({
                        "name": c['name'],
                        "location": c['location'],
                        "url": c['url'],
                        "latitude": location_data.latitude,
                        "longitude": location_data.longitude
                    })
                await asyncio.sleep(1.1) # Respect Nominatim usage policy
            except Exception as geo_e:
                print(f"Geocoding failed for {primary_location}: {geo_e}")
                
        return {"type": "conflicts_data", "data": geocoded_results}
        
    except Exception as e:
        print(f"Error fetching wiki conflicts: {e}")
        return {"type": "error", "message": str(e)}

async def update_conflicts_cache():
    global CONFLICTS_CACHE
    while True:
        try:
            print("Fetching Wikipedia Conflicts...")
            data = await fetch_wiki_conflicts()
            if data.get("type") == "conflicts_data":
                CONFLICTS_CACHE = data.get("data", [])
                print(f"Updated CONFLICTS_CACHE: {len(CONFLICTS_CACHE)} conflicts geocoded.")
        except Exception as e:
            print(f"Conflicts cache update error: {e}")
        await asyncio.sleep(43200) # Every 12 hours (Wars don't change by the minute)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Create background tasks for caching
    task_flights = asyncio.create_task(update_flights_cache())
    task_crises = asyncio.create_task(update_crises_cache())
    task_conflicts = asyncio.create_task(update_conflicts_cache())
    task_weather = asyncio.create_task(update_weather_cache())
    task_ships = asyncio.create_task(maintain_ships_cache())
    
    yield
    
    # Shutdown: Cancel background tasks
    task_flights.cancel()
    task_crises.cancel()
    task_conflicts.cancel()
    task_weather.cancel()
    task_ships.cancel()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(iss_router)

async def fetch_flight_data():
    async with httpx.AsyncClient() as client:
        try:
            # We add a small timeout. Note: OpenSky public API has rate limits (100 req/day for unauthenticated, or every 10 seconds for anonymous).
            # To avoid rapid blocking, we should fetch no more than once every 10-15 seconds.
            response = await client.get(OPENSKY_URL, timeout=10.0)
            response.raise_for_status()
            data = response.json()
            
            # Extract a subset of planes for testing performance
            states = data.get("states", [])
            
            results = []
            if states:
                # Cap to 1000 flights to prevent exceeding 1MB WebSocket max_size limitation
                for s in states[:1000]:
                    # OpenSky state vector format:
                    # 0: icao24, 1: callsign, 2: origin_country...
                    if s[5] is not None and s[6] is not None:
                        results.append({
                            "icao": s[0],
                            "callsign": s[1].strip() if s[1] else "Unknown",
                            "origin_country": s[2],
                            "longitude": s[5],
                            "latitude": s[6],
                            "altitude": s[7] if s[7] is not None else 0,
                            "velocity": s[9] if s[9] is not None else 0,
                            "true_track": s[10] if s[10] is not None else 0
                        })
            return {"type": "flight_data", "data": results}
        except Exception as e:
            print(f"Error fetching data: {e}")
            return {"type": "error", "message": str(e)}

@app.websocket("/ws/flights")
async def websocket_flights_endpoint(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_json({"type": "info", "message": "Flights connected"})
    try:
        while True:
            try:
                # Send the globally cached data instead of making a new request
                await websocket.send_json({"type": "flight_data", "data": FLIGHTS_CACHE})
            except WebSocketDisconnect:
                print("Flight Client disconnected normally")
                break
            except Exception as e:
                print(f"Flights WS error: {e}")
                
            await asyncio.sleep(15)
    except Exception:
        pass

# GDACS API (Crises and Disasters)
GDACS_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/MAP?eventlist=ALL"

async def fetch_gdacs_data():
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(GDACS_URL, timeout=10.0)
            response.raise_for_status()
            data = response.json()
            features = data.get("features", [])
            results = []
            
            for f in features:
                coords = f.get("geometry", {}).get("coordinates", [])
                if not coords or len(coords) < 2:
                    continue # Skip events with missing locations to avoid Null Island ghost markers
                
                props = f.get("properties", {})
                
                results.append({
                    "id": props.get("eventid"),
                    "name": props.get("name"),
                    "type": props.get("eventtype"),
                    "severity": props.get("alertlevel"),
                    "description": props.get("htmldescription"),
                    "longitude": coords[0],
                    "latitude": coords[1]
                })
                
            return {"type": "crises_data", "data": results}
        except Exception as e:
            print(f"Error fetching GDACS data: {e}")
            return {"type": "error", "message": str(e)}

from services.ships import websocket_ships_endpoint

@app.websocket("/ws/crises")
async def websocket_crises_endpoint(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_json({"type": "info", "message": "Crises connected"})
    try:
        while True:
            try:
                await websocket.send_json({"type": "crises_data", "data": CRISES_CACHE})
            except WebSocketDisconnect:
                print("Crises Client disconnected normally")
                break
            except Exception as e:
                print(f"Crises WS error: {e}")
                
            await asyncio.sleep(60)
    except Exception:
        pass

@app.websocket("/ws/conflicts")
async def websocket_conflicts_endpoint(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_json({"type": "info", "message": "Conflicts connected"})
    try:
        while True:
            try:
                await websocket.send_json({"type": "conflicts_data", "data": CONFLICTS_CACHE})
            except WebSocketDisconnect:
                print("Conflicts Client disconnected normally")
                break
            except Exception as e:
                print(f"Conflicts WS error: {e}")
                
            await asyncio.sleep(60)
    except Exception:
        pass

@app.websocket("/ws/ships")
async def ships_endpoint(websocket: WebSocket):
    await websocket_ships_endpoint(websocket)

from services.weather import websocket_weather_endpoint

@app.websocket("/ws/weather")
async def weather_endpoint(websocket: WebSocket):
    await websocket_weather_endpoint(websocket)

from services.news import websocket_news_endpoint

@app.websocket("/ws/news")
async def news_endpoint(websocket: WebSocket):
    await websocket_news_endpoint(websocket)

@app.get("/")
def read_root():
    return {"message": "Globe Tracker API is running"}

@app.get("/api/country/{iso}/live")
async def country_live_data(iso: str, name: str, currency: str | None = None):
    # Pobierz dane z backendowego smart cache / publicznych api
    data = await get_live_country_data(iso, name, currency)
    return {"type": "country_live_data", "data": data}
