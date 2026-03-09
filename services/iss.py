import requests
import logging
from fastapi import APIRouter

router = APIRouter()
logger = logging.getLogger(__name__)

# Free API for live ISS position
ISS_API_URL = "https://api.wheretheiss.at/v1/satellites/25544"

@router.get("/api/iss")
def get_iss_location():
    """
    Fetches the current live latitude, longitude, and altitude of the International Space Station.
    """
    try:
        response = requests.get(ISS_API_URL, timeout=5.0)
        response.raise_for_status()
        data = response.json()
        
        return {
                "name": "International Space Station",
                "latitude": data.get("latitude"),
                "longitude": data.get("longitude"),
                "altitude_km": data.get("altitude"),
                "velocity_kmh": data.get("velocity"),
                "visibility": data.get("visibility")
            }
    except Exception as e:
        logger.error(f"Error fetching ISS location: {e}")
        # Return a fallback or empty dictionary if the api fails
        return {"error": str(e)}
