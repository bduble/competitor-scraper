import os
import requests
import uuid
from datetime import datetime
from supabase import create_client, Client
import time
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ─── Supabase Setup ───────────────────────────────────────────────────────────

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_TABLE = "market_comps"

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("❌ SUPABASE_URL or SUPABASE_KEY environment variable is missing!")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

proxies = {
    "http": f"http://{BRIGHTDATA_USER}:{BRIGHTDATA_PASS}@{BRIGHTDATA_PROXY}",
    "https": f"http://{BRIGHTDATA_USER}:{BRIGHTDATA_PASS}@{BRIGHTDATA_PROXY}"
}

# ─── Cars.com Search Parameters ───────────────────────────────────────────────

ZIP_CODE = "76504"   # Temple, TX
RADIUS = 100
PAGE_SIZE = 100

def fetch_cars(page=1, retries=3):
    url = (
        f"https://www.cars.com/shopping/results/"
        f"?zip={ZIP_CODE}&radius={RADIUS}&page={page}&page_size={PAGE_SIZE}&stock_type=all"
    )
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/124.0.0.0 Safari/537.36"
    }
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, proxies=proxies, timeout=90, verify=False)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.ReadTimeout:
            print(f"Timeout (attempt {attempt}/{retries}) for page {page}. Retrying...")
            time.sleep(2 * attempt)
        except Exception as e:
            print(f"Error fetching page {page}: {e}")
            if attempt == retries:
                print(f"❌ Failed to fetch page {page} after {retries} attempts.")
                return {}
            time.sleep(2 * attempt)
    return {}

def parse_cars(results):
    cars = []
    for result in results.get("listings", []):
        inventory_id = result.get("id")
        year = result.get("year")
        make = result.get("make")
        model = result.get("model")
        trim = result.get("trim")
        mileage = result.get("mileage")
        price = result.get("list_price")
        url = "https://www.cars.com/vehicledetail/" + str(inventory_id)
        car = {
            "id": str(uuid.uuid4()),
            "inventory_id": inventory_id,
            "source": "cars.com",
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
        print(f"🔍 Fetching Cars.com page {page} ...")
        data = fetch_cars(page)
        cars = parse_cars(data)
        if not cars:
            print(f"✅ No more vehicles found (or page failed). Ending at page {page}.")
            break
        sync_to_supabase(cars)
        total_found += len(cars)
        # Check if we're done (Cars.com returns total pages in response)
        if page >= data.get("total_page_count", 1):
            break
        page += 1
        time.sleep(2)  # Throttle between pages
    print(f"✅ Complete. Total vehicles uploaded: {total_found}")

if __name__ == "__main__":
    main()
