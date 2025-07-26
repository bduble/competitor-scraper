import os
import requests
import uuid
from datetime import datetime
from supabase import create_client, Client

# ─── Supabase Setup ───────────────────────────────────────────────────────────

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_TABLE = "market_comps"

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("❌ SUPABASE_URL or SUPABASE_KEY environment variable is missing!")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ─── Cars.com Search Parameters ───────────────────────────────────────────────

ZIP_CODE = "76504"   # Temple, TX
RADIUS = 100
PAGE_SIZE = 100

def fetch_cars(page=1):
    url = (
        f"https://www.cars.com/shopping/results/"
        f"?zip={ZIP_CODE}&radius={RADIUS}&page={page}&page_size={PAGE_SIZE}&stock_type=all"
    )
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()

def parse_cars(results):
    cars = []
    for result in results.get("listings", []):
        # Defensive parsing for required fields
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
        # Upsert by 'inventory_id' to avoid duplicates
        supabase.table(SUPABASE_TABLE).upsert(v, on_conflict="inventory_id").execute()
        print(f"Pushed {v['inventory_id']} - {v['year']} {v['make']} {v['model']} @ ${v['price']}")

def main():
    total_found = 0
    page = 1
    while True:
        print(f"🔍 Fetching Cars.com page {page} ...")
        data = fetch_cars(page)
        cars = parse_cars(data)
        if not cars:
            print("✅ No more vehicles found.")
            break
        sync_to_supabase(cars)
        total_found += len(cars)
        if page >= data.get("total_page_count", 1):
            break
        page += 1
    print(f"✅ Complete. Total vehicles uploaded: {total_found}")

if __name__ == "__main__":
    main()
