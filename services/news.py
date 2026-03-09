import asyncio
import httpx
import os
from fastapi import WebSocket, WebSocketDisconnect

# GNews API requires a free API key, which should be in the .env file
# Provide fallback logic if the key is missing

GNEWS_API_URL = "https://gnews.io/api/v4/top-headlines"

# We'll map countries to their GNews country codes and rough coordinates to place markers
NEWS_REGIONS = [
    {"country": "us", "lat": 38.0, "lon": -97.0, "name": "United States"},
    {"country": "gb", "lat": 54.0, "lon": -2.0, "name": "United Kingdom"},
    {"country": "de", "lat": 51.0, "lon": 9.0, "name": "Germany"},
    {"country": "fr", "lat": 46.0, "lon": 2.0, "name": "France"},
    {"country": "in", "lat": 20.0, "lon": 77.0, "name": "India"},
    {"country": "jp", "lat": 36.0, "lon": 138.0, "name": "Japan"},
    {"country": "br", "lat": -14.0, "lon": -51.0, "name": "Brazil"},
    {"country": "au", "lat": -25.0, "lon": 133.0, "name": "Australia"},
    {"country": "pl", "lat": 52.0, "lon": 19.0, "name": "Poland"},
    {"country": "cn", "lat": 35.0, "lon": 105.0, "name": "China"}
]

async def fetch_news_data():
    api_key = os.getenv("GNEWS_API_KEY", "")
    if not api_key:
        return {"type": "error", "message": "GNEWS_API_KEY is missing from environment variables."}

    results = []
    
    # To save API calls and time, let's randomly pick 3-4 countries per cycle
    import random
    selected_regions = random.sample(NEWS_REGIONS, 4)
    
    async with httpx.AsyncClient() as client:
        for region in selected_regions:
            url = f"{GNEWS_API_URL}?category=general&lang=en&country={region['country']}&max=1&apikey={api_key}"
            try:
                response = await client.get(url, timeout=5.0)
                if response.status_code == 200:
                    data = response.json()
                    articles = data.get("articles", [])
                    if articles:
                        article = articles[0]
                        results.append({
                            "region": region["name"],
                            "latitude": region["lat"],
                            "longitude": region["lon"],
                            "title": article.get("title", ""),
                            "description": article.get("description", ""),
                            "url": article.get("url", ""),
                            "source": article.get("source", {}).get("name", "Unknown Source")
                        })
            except Exception as e:
                print(f"Error fetching news for {region['country']}: {e}")
                
    return {"type": "news_data", "data": results}

async def websocket_news_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    api_key = os.getenv("GNEWS_API_KEY", "")
    if not api_key:
        await websocket.send_json({"type": "info", "message": "GNews API Key missing. Skipping news fetch."})
        # Keep connection open but don't loop fetch
        try:
            while True:
                await asyncio.sleep(60)
        except:
            pass
        return

    await websocket.send_json({"type": "info", "message": "News connected"})
    try:
        while True:
            try:
                # Fetch fresh news
                response_dict = await fetch_news_data()
                if isinstance(response_dict, dict) and response_dict.get("data"):
                    await websocket.send_json(response_dict)
            except WebSocketDisconnect:
                print("News Client disconnected normally")
                break
            except Exception as e:
                print(f"News loop error: {e}")
                
            # Fetch news every 15 minutes to save API quota (free tier is usually limited per day)
            await asyncio.sleep(900)
    except Exception:
        pass
