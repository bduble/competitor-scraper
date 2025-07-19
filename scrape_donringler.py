import os
import re
from datetime import datetime
from bs4 import BeautifulSoup
from supabase import create_client, Client
from playwright.sync_api import sync_playwright

# ─── Load Supabase Environment Variables ──────────────────────────────

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
BRIGHTDATA_PROXY = os.getenv("BRIGHTDATA_PROXY")      # e.g. brd.superproxy.io:33335
BRIGHTDATA_USER = os.getenv("BRIGHTDATA_USER")
BRIGHTDATA_PASS = os.getenv("BRIGHTDATA_PASS")

print(f"🔐 Supabase URL: {SUPABASE_URL}")
print(f"🔐 Supabase Key Loaded: {'Yes' if SUPABASE_KEY else 'No'}")
print(f"🌍 Using BrightData Proxy: {BRIGHTDATA_PROXY}")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("❌ SUPABASE_URL or SUPABASE_KEY environment variable is missing!")
if not BRIGHTDATA_PROXY or not BRIGHTDATA_USER or not BRIGHTDATA_PASS:
    raise ValueError("❌ BrightData proxy env variables missing!")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ─── Constants ───────────────────────────────────────────────────────

BASE_URL = "https://www.donringlerchevrolet.com"
INVENTORY_URL = f"{BASE_URL}/used-vehicles/"

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
    print("🔍 Fetching inventory with Playwright + BrightData Proxy...")
    all_vehicles = []
    with sync_playwright() as p:
        # Proxy dict for Playwright
        proxy_settings = {
            "server": f"http://{BRIGHTDATA_PROXY}",
            "username": BRIGHTDATA_USER,
            "password": BRIGHTDATA_PASS
        }
        browser = p.chromium.launch(headless=True, proxy=proxy_settings)
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()
        page.goto(INVENTORY_URL, timeout=90000)
        html = page.content()
        browser.close()

        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select(".vehicle-card")

        if not cards:
            print("⚠️ No vehicle cards found. Dumping HTML for debug.")
            print(html[:1500])
            return []

        for card in cards:
            v = extract_vehicle_data(card)
            if v:
                all_vehicles.append(v)
    print(f"→ Total vehicles found: {len(all_vehicles)}")
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
