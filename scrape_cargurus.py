import os
import requests
from bs4 import BeautifulSoup
import uuid
from datetime import datetime
from supabase import create_client, Client
import time
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Supabase setup
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_TABLE = "market_comps"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Bright Data proxy settings
BRIGHTDATA_PROXY = os.getenv("BRIGHTDATA_PROXY", "brd.superproxy.io:33335")
BRIGHTDATA_USER = os.getenv("BRIGHTDATA_USER", "brd-customer-XXX-zone-residential_proxy1")
BRIGHTDATA_PASS = os.getenv("BRIGHTDATA_PASS", "xxxxxxxxxxxxxxxx")

def get_proxy_dict():
    proxy_url = f"http://{BRIGHTDATA_USER}:{BRIGHTDATA_PASS}@{BRIGHTDATA_PROXY}"
    return {
        "http": proxy_url,
        "https": proxy_url,
    }

def fetch_cars(page=1, retries=3):
    url = (
        f"https://www.cargurus.com/Cars/inventorylisting/viewDetailsFilterViewInventoryListing.action"
        f"?zip=76504&distance=100&sortDir=ASC&sourceContext=carGurusHomePageModel&startYear=1981"
        f"&maxPrice=1000000&showNegotiable=true&sortType=DEAL_SCORE&entitySelectingHelper.selectedEntity=c24666"
        f"&page={page}"
    )
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, proxies=proxies, timeout=90, verify=False)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            print(f"Error fetching page {page}: {e}")
            if attempt == retries:
                print(f"❌ Failed to fetch page {page} after {retries} attempts.")
                return ""
            time.sleep(2 * attempt)
    return ""

def parse_cars(html):
    soup = BeautifulSoup(html, "html.parser")
    cars = []
    # Cargurus wraps cars in <div class="cg-dealFinder-result-wrap"> and other containers
    for card in soup.select('div.listing-search-list-item'):
        try:
            title = card.select_one('.listing-title').get_text(strip=True)
            price = card.select_one('.listing-price').get_text(strip=True)
            price = int(price.replace("$", "").replace(",", ""))
            mileage = card.select_one('.listing-mileage').get_text(strip=True)
            mileage = int(mileage.replace("miles", "").replace(",", "").strip())
            url = "https://www.cargurus.com" + card.select_one('a')['href']
            # Attempt to split year, make, model, trim
            title_parts = title.split(" ", 3)
            year = int(title_parts[0])
            make = title_parts[1]
            model = title_parts[2]
            trim = title_parts[3] if len(title_parts) > 3 else ""
            inventory_id = str(uuid.uuid5(uuid.NAMESPACE_URL, url))  # No ID? Hash the URL

            car = {
                "id": str(uuid.uuid4()),
                "inventory_id": inventory_id,
                "source": "cargurus.com",
                "year": year,
                "make": make,
                "model": model,
                "trim": trim,
                "mileage": mileage,
                "price": price,
                "url": url,
                "created_at": datetime.utcnow().isoformat(),
            }
            cars.append(car)
        except Exception as e:
            print(f"❌ Error parsing vehicle: {e}")
    return cars

def sync_to_supabase(vehicles):
    print(f"🚚 Syncing {len(vehicles)} vehicles to Supabase...")
    for v in vehicles:
        try:
            supabase.table(SUPABASE_TABLE).upsert(v, on_conflict="inventory_id").execute()
            print(f"Pushed {v['inventory_id']} - {v['year']} {v['make']} {v['model']} @ ${v['price']}")
        except Exception as e:
            print(f"❌ Error uploading {v['inventory_id']}: {e}")

def main():
    total_found = 0
    page = 1
    while True:
        print(f"🔍 Fetching Cargurus page {page} ...")
        html = fetch_cars(page)
        if not html:
            break
        cars = parse_cars(html)
        if not cars:
            print(f"✅ No more vehicles found (or page failed). Ending at page {page}.")
            break
        sync_to_supabase(cars)
        total_found += len(cars)
        page += 1
        time.sleep(2)
        # Optional: stop after N pages, or parse "next page" logic from HTML
        # if page > 10: break
    print(f"✅ Complete. Total vehicles uploaded: {total_found}")

if __name__ == "__main__":
    main()
