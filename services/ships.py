import asyncio
import json
import websockets
import os
from dotenv import load_dotenv
from fastapi import WebSocket, WebSocketDisconnect

load_dotenv()

SHIPS_CACHE = []

async def maintain_ships_cache():
    global SHIPS_CACHE
    AIS_API_KEY = os.getenv("AIS_API_KEY", "")
    if not AIS_API_KEY:
        print("AIS_API_KEY not configured. Ships layer disabled.")
        return

    # Connect to aisstream.io
    url = "wss://stream.aisstream.io/v0/stream"
    
    # We subscribe to multiple specific regional bounding boxes to maximize free-tier global coverage
    # Format: [[SouthWestLat, SouthWestLon], [NorthEastLat, NorthEastLon]]
    subscribe_message = {
        "APIKey": AIS_API_KEY,
        "BoundingBoxes": [
            [[-60, -180], [75, -30]], # Americas (North & South) & Eastern Pacific
            [[-40, -30],  [65, 50]],  # Europe, Africa, Mediterranean
            [[-50, 50],   [60, 120]], # Indian Ocean, Southeast Asia
            [[-50, 120],  [65, 180]], # East Asia, Australia, Western Pacific
        ],
        "FilterMessageTypes": ["PositionReport"]
    }

    try:
        async with websockets.connect(url) as ais_ws:
            await ais_ws.send(json.dumps(subscribe_message))
            
            # We'll maintain a stateful dictionary of active ships to prevent UI blinking
            active_ships = {}
            last_send_time = asyncio.get_event_loop().time()
            
            async for message_str in ais_ws:
                msg = json.loads(message_str)
                if msg.get("MessageType") == "PositionReport":
                    report = msg.get("Message", {}).get("PositionReport", {})
                    meta = msg.get("MetaData", {})
                    
                    if report and meta:
                        mmsi = meta.get("MMSI")
                        ship_data = {
                            "mmsi": mmsi,
                            "name": meta.get("ShipName", "Unknown Vessel").strip(),
                            "latitude": report.get("Latitude"),
                            "longitude": report.get("Longitude"),
                            "cog": report.get("Cog", 0), # Course over ground (heading)
                            "sog": report.get("Sog", 0)  # Speed over ground
                        }
                        
                        # Only keep valid coordinates
                        if ship_data["latitude"] and ship_data["longitude"] and ship_data["latitude"] <= 90:
                            if mmsi in active_ships:
                                del active_ships[mmsi]
                            active_ships[mmsi] = ship_data
                            
                            # Keep dict size bounded (e.g., max 3000 ships)
                            if len(active_ships) > 3000:
                                # Remove the oldest (first item inserted)
                                active_ships.pop(next(iter(active_ships)))
                
                # Send batch every 2 seconds
                current_time = asyncio.get_event_loop().time()
                if current_time - last_send_time > 2.0 and active_ships:
                    # Send up to 2000 recent ships to keep UI responsive
                    SHIPS_CACHE = list(active_ships.values())[-2000:]
                    last_send_time = current_time
                    
    except Exception as e:
        print(f"Error connecting to AIS Stream: {e}")
        await asyncio.sleep(5)

async def websocket_ships_endpoint(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_json({"type": "info", "message": "Ships connected"})
    try:
        while True:
            try:
                await websocket.send_json({"type": "ships_data", "data": SHIPS_CACHE})
            except WebSocketDisconnect:
                print("Ships Client disconnected normally")
                break
            except Exception as e:
                print(f"Ships WS error: {e}")
                
            await asyncio.sleep(2)
    except Exception:
        pass
