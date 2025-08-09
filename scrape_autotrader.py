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

# Bright Data proxy
BRIGHTDATA_PROXY = os.getenv("BRIGHTDATA_PROXY", "brd.superproxy.io:33335")
BRIGHTDATA_USER = os.getenv("BRIGHTDATA_USER", "brd-customer-XXX-zone-residential_proxy1")
BRIGHTDATA_PASS = os.getenv("BRIGHTDATA_PASS", "xxxxxxxxxxxxxxxx")

proxies = {
    "http": f"http://{BRIGHTDATA_USER}:{BRIGHTDATA_PASS}@{BRIGHTDATA_PROXY}",
    "https": f"http://{BRIGHTDATA_USER}:{BRIGHTDATA_PASS}@{BRIGHTDATA_PROXY}"
}

def get_proxy_dict():
    proxy_url = f"http://{BRIGHTDATA_USER}:{BRIGHTDATA_PASS}@{BRIGHTDATA_PROXY}"
    return {"http": proxy_url, "https": proxy_url}

def fetch_autotrader_page(page=1, retries=3):
    url = f"https://www.autotrader.com/cars-for-sale/all-cars?zip=76504&searchRadius=100&page={page}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    for attempt in range(retries):
        try:
            resp = requests.get(
                url,
                headers=headers,
                proxies=proxies,
                timeout=30,
                verify=False,
            )
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            print(f"Error: {e}")
            if attempt == retries - 1:
                print(
                    f"❌ Failed to fetch Autotrader page {page} after {retries} attempts."
                )
            else:
                time.sleep(2 * (attempt + 1))
    return ""

def parse_autotrader_listings(html):
    soup = BeautifulSoup(html, "html.parser")
    cars = []
    for card in soup.select('div.inventory-listing'):
        try:
            title = card.select_one('h2.text-bold').get_text(strip=True)
            price_elem = card.select_one('.first-price')
            price = int(price_elem.get_text(strip=True).replace("$", "").replace(",", "")) if price_elem else None
            mileage_elem = card.select_one('.item-card-specifications .text-bold')
            mileage = int(mileage_elem.get_text(strip=True).replace(",", "")) if mileage_elem else None
            link = card.select_one('a.inventory-listing-header')['href']
            url = f"https://www.autotrader.com{link}" if link else None

            title_parts = title.split(" ", 3)
            year = int(title_parts[0]) if len(title_parts) > 0 else None
            make = title_parts[1] if len(title_parts) > 1 else ""
            model = title_parts[2] if len(title_parts) > 2 else ""
            trim = title_parts[3] if len(title_parts) > 3 else ""
            inventory_id = str(uuid.uuid5(uuid.NAMESPACE_URL, url)) if url else str(uuid.uuid4())

            car = {
                "id": str(uuid.uuid4()),
                "inventory_id": inventory_id,
                "source": "autotrader.com",
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
        print(f"🔍 Fetching Autotrader page {page} ...")
        html = fetch_autotrader_page(page)
        if not html:
            break
        cars = parse_autotrader_listings(html)
        if not cars:
            print(f"✅ No more vehicles found (or page failed). Ending at page {page}.")
            break
        sync_to_supabase(cars)
        total_found += len(cars)
        page += 1
        time.sleep(2)
        # To avoid runaway, you can limit to N pages or parse for "next" button existence
        # if page > 10: break
    print(f"✅ Complete. Total vehicles uploaded: {total_found}")

if __name__ == "__main__":
    main()
