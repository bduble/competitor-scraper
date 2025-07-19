import os
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from supabase import create_client, Client

# ─── Load Supabase Environment Variables ──────────────────────────────────────

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

print(f"🔐 Supabase URL: {SUPABASE_URL}")
print(f"🔐 Supabase Key Loaded: {'Yes' if SUPABASE_KEY else 'No'}")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("❌ SUPABASE_URL or SUPABASE_KEY environment variable is missing!")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ─── Constants ────────────────────────────────────────────────────────────────

BASE_URL = "https://www.donringlerchevrolet.com"
INVENTORY_URL = f"{BASE_URL}/used-vehicles/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/115.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}


# ─── Utility Functions ────────────────────────────────────────────────────────

def parse_price(text):
    return int(re.sub(r"[^\d]", "", text)) if text else None

def parse_mileage(text):
    return int(re.sub(r"[^\d]", "", text)) if text else None

# ─── Vehicle Extraction ───────────────────────────────────────────────────────

def extract_vehicle_data(card):
    try:
        url = BASE_URL + card.select_one("a.vehicle-card-link")["href"]
        title = card.select_one(".title").get_text(strip=True)
        price = parse_price(card.select_one(".price").get_text())
        mileage = parse_mileage(card.select_one(".mileage").get_text())
        stock_tag = card.select_one(".stock-number")
        inventory_id = int(re.sub(r"[^\d]", "", stock_tag.get_text())) if stock_tag else None

        year, make, model, *trim_parts = title.split(" ")
        trim = " ".join(trim_parts)

        return {
            "inventory_id": inventory_id,
            "source": "donringlerchevrolet.com",
            "year": int(year),
            "make": make,
            "model": model,
            "trim": trim,
            "mileage": mileage,
            "price": price,
            "url": url,
            "created_at": datetime.utcnow().isoformat()
        }

    except Exception as e:
        print(f"[!] Failed to extract vehicle: {e}")
        return None

# ─── Fetch All Vehicles ───────────────────────────────────────────────────────

def fetch_inventory():
    print("🔍 Fetching inventory from Don Ringler...")
    all_vehicles = []
    page = 1

    while True:
        paged_url = f"{INVENTORY_URL}?page={page}"
        res = requests.get(paged_url, headers=HEADERS)

        if res.status_code != 200:
            print(f"❌ Failed to fetch page {page}: Status {res.status_code}")
            break

        soup = BeautifulSoup(res.text, "html.parser")
        cards = soup.select(".vehicle-card")

        if not cards:
            print(f"ℹ️ No vehicle cards found on page {page}. Ending pagination.")
            break

        for card in cards:
            v = extract_vehicle_data(card)
            if v:
                all_vehicles.append(v)

        print(f"→ Page {page}: {len(cards)} vehicles")
        page += 1

    return all_vehicles

# ─── Sync to Supabase ─────────────────────────────────────────────────────────

def sync_to_supabase(vehicles):
    print(f"🚚 Syncing {len(vehicles)} vehicles to Supabase...")
    for v in vehicles:
        print(f"Pushing {v['inventory_id']} - {v['year']} {v['make']} {v['model']} @ ${v['price']}")
        supabase.table("market_comps").upsert(v, on_conflict="inventory_id").execute()

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    vehicles = fetch_inventory()
    if not vehicles:
        print("⚠️ No vehicles found.")
        return
    sync_to_supabase(vehicles)
    print("✅ Done.")

if __name__ == "__main__":
    main()
