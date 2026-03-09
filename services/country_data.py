import httpx
import time
import asyncio
import feedparser
from urllib.parse import quote_plus
from bs4 import BeautifulSoup

# Caches slowniki w RAM
NEWS_CACHE = {}
STOCK_CACHE = {}
TOURISM_CACHE = {}
CURRENCY_CACHE_TIMESTAMP = 0.0
CURRENCY_CACHE_DATA = {}

# Cache Triggers (TTL in seconds)
NEWS_TTL = 300  # 5 minut dla wiadomosci
STOCK_TTL = 300 # 5 minut dla sesji gieldowych
CURRENCY_TTL = 86400 # 24 godziny dla JSON walut
TOURISM_TTL = 604800 # Tydzień dla miejscówek

# Currency URL (Free, no-auth raw JSON from CDN)
CURRENCY_API_URL = "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json"

# Slownik Stock Indices (Top gospodarki by ISO Alpha-3)
STOCK_INDICES = {
    "USA": "^GSPC", "GBR": "^FTSE", "DEU": "^GDAXI", "FRA": "^FCHI", 
    "JPN": "^N225", "POL": "^WIG20", "CHN": "000001.SS", "CAN": "^GSPTSE", 
    "AUS": "^AXJO", "BRA": "^BVSP", "IND": "^BSESN", "ITA": "FTSEMIB.MI",
    "ESP": "^IBEX", "KOR": "^KS11", "MEX": "^MXX", "NLD": "^AEX",
    "CHE": "^SSMI", "SWE": "^OMX", "ZAF": "^J203.JO", "TUR": "XU100.IS"
}

async def fetch_currency(currency_code: str):
    global CURRENCY_CACHE_TIMESTAMP, CURRENCY_CACHE_DATA
    now = time.time()
    
    # Odswiez plik JSON z pelnymi kursami jesli starszy niz 24h
    if now - CURRENCY_CACHE_TIMESTAMP > CURRENCY_TTL or not CURRENCY_CACHE_DATA:
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(CURRENCY_API_URL, timeout=10.0)
                resp.raise_for_status()
                data = resp.json()
                CURRENCY_CACHE_DATA = data.get("usd", {})
                CURRENCY_CACHE_TIMESTAMP = now
            except Exception as e:
                print(f"Currency fetch error: {e}")
                
    # Zwrocenie pozadanej pary z JSON'a
    code = currency_code.lower()
    rates = CURRENCY_CACHE_DATA
    if code in rates:
        return {"code": currency_code.upper(), "rate": round(rates[code], 4), "base": "USD"}
    return None

async def fetch_stock(iso: str):
    now = time.time()
    
    # Check Cache 5 min
    if iso in STOCK_CACHE and (now - STOCK_CACHE[iso]["timestamp"] < STOCK_TTL):
        return STOCK_CACHE[iso]["data"]
        
    ticker = STOCK_INDICES.get(iso)
    if not ticker:
        data = {"ticker": None, "current": 0, "change_pct": 0, "message": "Brak głownych notowań publicznych"}
        STOCK_CACHE[iso] = {"timestamp": now, "data": data}
        return data

    try:
        url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=2d"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers, timeout=5.0)
            if resp.status_code == 200:
                body = resp.json()
                res = body.get("chart", {}).get("result", [])
                if res and res[0].get("meta"):
                    meta = res[0]["meta"]
                    current = meta.get("regularMarketPrice", 0)
                    prev_close = meta.get("chartPreviousClose", 0)
                    
                    if current == 0 and prev_close == 0:
                        data = {"ticker": ticker, "current": 0, "change_pct": 0, "message": "Brak precyzyjnych notowań"}
                    else:
                        change = 0 if prev_close == 0 else ((current - prev_close) / prev_close) * 100
                        data = {
                            "ticker": ticker, 
                            "current": round(current, 2), 
                            "change_pct": round(change, 2)
                        }
                else:
                    data = {"ticker": ticker, "current": 0, "change_pct": 0, "message": "Brak rynków"}
            else:
                 data = {"ticker": ticker, "current": 0, "change_pct": 0, "message": f"Niedostępne ({resp.status_code})"}
                 
    except Exception as e:
        print(f"Stock fetch error for {iso}: {e}")
        data = {"ticker": ticker, "current": 0, "change_pct": 0, "message": "Pobieranie przerwane"}
        
    # Zapamietaj wynik
    STOCK_CACHE[iso] = {"timestamp": now, "data": data}
    return data

async def fetch_category_news(client, country_name: str, category_keyword: str, limit: int = 15):
    query = quote_plus(f"{country_name} {category_keyword}")
    rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
    
    results = []
    # Prog 7 dni wstecz w sekundach (Unix Epoch) - Pomoze zapelnic Sport
    time_threshold = time.time() - (7 * 24 * 3600)
    
    try:
        resp = await client.get(rss_url, timeout=10.0)
        xml_data = resp.text
        
        loop = asyncio.get_event_loop()
        feed = await loop.run_in_executor(None, feedparser.parse, xml_data)
        
        for entry in feed.entries:
            # Uzywaj limitu zapisanego artykułami niepustymi i swiezymi
            if len(results) >= limit:
                break
                
            # Filtruj wiadomosci, ktore sa starsze niz 3 dni
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                entry_time = time.mktime(entry.published_parsed)
                if entry_time < time_threshold:
                    continue # Za stare
                    
            # Safely get source
            source = getattr(entry, 'source', None)
            source_title = getattr(source, 'title', "Google News") if source else "Google News"
            
            results.append({
                "title": entry.title,
                "link": entry.link,
                "published": entry.published,
                "source": source_title
            })
    except Exception as e:
        print(f"News fetch error for {query}: {e}")
        
    return results

async def fetch_news(country_name: str):
    iso_key = country_name.lower()
    now = time.time()
    
    # Check cache 5 min
    if iso_key in NEWS_CACHE and (now - NEWS_CACHE[iso_key]["timestamp"] < NEWS_TTL):
        return NEWS_CACHE[iso_key]["data"]

    # 4 Równoległe zapytania dla wypełnienia 10-15 najistotniejszych wieści (zabezpieczone limiterem do 7 dni)
    async with httpx.AsyncClient() as client:
        task_econ = fetch_category_news(client, country_name, "economy OR business", 12)
        task_poli = fetch_category_news(client, country_name, "politics OR government", 10)
        task_ent = fetch_category_news(client, country_name, "entertainment OR gossip OR culture", 8)
        task_sport = fetch_category_news(client, country_name, "sports OR national team OR athletes", 12)
        
        econ_news, poli_news, ent_news, sport_news = await asyncio.gather(task_econ, task_poli, task_ent, task_sport)

    data = {
        "economy": econ_news,
        "politics": poli_news,
        "entertainment": ent_news,
        "sports": sport_news
    }
        
    NEWS_CACHE[iso_key] = {"timestamp": now, "data": data}
    return data

async def fetch_tourism(country_name: str):
    iso_key = country_name.lower()
    now = time.time()
    
    if iso_key in TOURISM_CACHE and (now - TOURISM_CACHE[iso_key]["timestamp"] < TOURISM_TTL):
        return TOURISM_CACHE[iso_key]["data"]

    # Wikipedia REST API: Szukanie Landamrków i atrakcji
    url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch=Landmarks%20in%20{quote_plus(country_name)}&utf8=&format=json&srlimit=8"
    
    results = []
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=10.0)
            if resp.status_code == 200:
                data = resp.json()
                search_res = data.get("query", {}).get("search", [])
                
                for item in search_res:
                    title = item.get("title", "")
                    snippet = item.get("snippet", "")
                    # Czyszczenie HTML tagów z zajawki Wikipedii
                    clean_snippet = BeautifulSoup(snippet, "html.parser").get_text()
                    
                    # Filtrujemy ogólne artykuły i zgarniamy rzeczywiste miejsca
                    if "Tourism in" not in title and "List of" not in title:
                        results.append({"title": title, "snippet": clean_snippet + "..."})
    except Exception as e:
        print(f"Tourism fetch error for {country_name}: {e}")
        
    results = results[:5] # Max 5 perel turystyki
    TOURISM_CACHE[iso_key] = {"timestamp": now, "data": results}
    return results

async def get_live_country_data(iso: str, name: str, currency: str | None = None):
    # Wykonuj rownolegle jako Asynchro!
    stock_task = asyncio.create_task(fetch_stock(iso))
    news_task = asyncio.create_task(fetch_news(name))
    tourism_task = asyncio.create_task(fetch_tourism(name))
    
    if currency:
        currency_task = asyncio.create_task(fetch_currency(currency))
        stock_data, news_data, tourism_data, currency_data = await asyncio.gather(
            stock_task, news_task, tourism_task, currency_task
        )
    else:
        stock_data, news_data, tourism_data = await asyncio.gather(
            stock_task, news_task, tourism_task
        )
        currency_data = None
        
    return {
        "stock": stock_data,
        "news": news_data,
        "tourism": tourism_data,
        "currency": currency_data
    }
