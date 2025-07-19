import requests
from bs4 import BeautifulSoup
from datetime import datetime
from supabase import create_client, Client
import re

# Supabase config (can also be set with Render env vars)
import os
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

BASE_URL = "https://www.donringlerchevrolet.com"
INVENTORY_URL = f"{BASE_URL}/used-vehicles/"

HEADERS = {"User-Agent": "Mozilla/5.0"}

def parse_price(text):
    return int(re.sub(r"[^\d]", "", text)) if text else None

def parse_mileage(text):
    return int(re.sub(r"[^\d]", "", text)) if text else None

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

def fetch_inventory():
    print("🔍 Fetching inventory from Don Ringler...")
    all_vehicles = []
    page = 1
    while True:
        paged_url = f"{INVENTORY_URL}?page={page}"
        res = requests.get(paged_url, headers=HEADERS)
        if res.status_code != 200 or "No vehicles found" in res.text:
            break
        soup = BeautifulSoup(res.text, "html.parser")
        cards = soup.select(".vehicle-card")
        if not cards:
            break
        for card in cards:
            v = extract_vehicle_data(card)
            if v:
                all_vehicles.append(v)
        print(f"→ Page {page}: {len(cards)} vehicles")
        page += 1
    return all_vehicles

def sync_to_supabase(vehicles):
    print(f"🚚 Syncing {len(vehicles)} vehicles to Supabase...")
    for v in vehicles:
        print(f"Pushing {v['inventory_id']} - {v['year']} {v['make']} {v['model']} @ ${v['price']}")
        supabase.table("market_comps").upsert(v, on_conflict="inventory_id").execute()

def main():
    vehicles = fetch_inventory()
    if not vehicles:
        print("⚠️ No vehicles found.")
        return
    sync_to_supabase(vehicles)
    print("✅ Done.")

if __name__ == "__main__":
    main()
