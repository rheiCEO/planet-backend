import requests
from bs4 import BeautifulSoup
import json

def fetch_conflicts():
    url = "https://en.wikipedia.org/wiki/List_of_ongoing_armed_conflicts"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        res = requests.get(url, headers=headers)
        res.raise_for_status()

        soup = BeautifulSoup(res.text, 'html.parser')
        tables = soup.find_all('table', {'class': 'wikitable'})
        
        conflicts = []
        for table in tables:
            rows = table.find_all('tr')
            for row in rows[1:]:
                cols = row.find_all('td')
                if len(cols) >= 3:
                    conflict_name = cols[1].text.strip()
                    location = cols[3].text.strip() if len(cols) > 3 else cols[2].text.strip()
                    
                    import re
                    conflict_name = re.sub(r'\[\d+\]', '', conflict_name)
                    location = re.sub(r'\[\d+\]', '', location)
                    
                    if conflict_name and location:
                        conflicts.append({
                            "conflict": conflict_name,
                            "location": location.replace('\n', ', ')
                        })

        for i, c in enumerate(conflicts[:15]):
            print(f"{i+1}. {c['location']} ---> {c['conflict']}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fetch_conflicts()
