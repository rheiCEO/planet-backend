import requests
import json

try:
    url = "http://localhost:8000/api/country/POL/live?name=Poland"
    print(f"Biegam do: {url}")
    res = requests.get(url, timeout=15)
    print("Status:", res.status_code)
    try:
        data = res.json()
        print(json.dumps(data, indent=2))
    except BaseException as e:
        print("Nie udalo sie zdekodowac JSON:", e)
        print("Cialo odpowiedzi:", res.text)
except Exception as e:
    print("Ogolny bląd:", e)
