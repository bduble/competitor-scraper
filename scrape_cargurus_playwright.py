import os
from datetime import datetime
from bs4 import BeautifulSoup
from supabase import create_client, Client
from playwright.sync_api import sync_playwright

# Supabase config
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Proxy (Bright Data) config
BRIGHTDATA_PROXY = os.getenv("BRIGHTDATA_PROXY")
BRIGHTDATA_USER = os.getenv("BRIGHTDATA_USER")
BRIGHTDATA_PASS = os.getenv("BRIGHTDATA_PASS")
USE_PROXY = bool(BRIGHTDATA_PROXY and BRIGHTDATA_USER and BRIGHTDATA_PASS)

def get_context(playwright):
    if USE_PROXY:
        return playwright.chromium.launch(
            headless=True,
            proxy={
                "server": f"http://{BRIGHTDATA_PROXY}",
                "username": BRIGHTDATA_USER,
                "password": BRIGHTDATA_PASS
            }
        ).new_context(
            ignore_https_errors=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 900},
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Upgrade-Insecure-Requests": "1",
                "DNT": "1",
            }
        )
    else:
        return playwright.chromium.launch(headless=True).new_context(
            ignore_https_errors=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 900},
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Upgrade-Insecure-Requests": "1",
                "DNT": "1",
            }
        )

def parse_vehicle(card):
    try:
        title_elem = card.select_one(".listing-title")
        title = title_elem.get_text(strip=True) if title_elem else ""
        url_elem = card.select_one("a.listing-title")
        url = "https://www.cargurus.com" + url_elem['href'] if url_elem else None

        price_elem = card.select_one(".cg-dealFinder-priceAndMoPayment .price")
        price = int(price_elem.get_text(strip=True).replace("$","").replace(",","")) if price_elem else None

        year = make = model = trim = ""
        parts = title.split(" ")
        if len(parts) >= 3:
            year = int(parts[0])
            make = parts[1]
            model = parts[2]
            trim = " ".join(parts[3:]) if len(parts) > 3 else ""

        mileage_elem = card.select_one(".listing-mileage")
        mileage = int(mileage_elem.get_text(strip=True).replace("miles", "").replace(",", "")) if mileage_elem else None

        return {
            "source": "cargurus.com",
            "year": year,
            "make": make,
            "model": model,
            "trim": trim,
            "mileage": mileage,
            "price": price,
            "url": url,
            "created_at": datetime.utcnow().isoformat()
        }
    except Exception as e:
        print(f"[!] Parse fail: {e}")
        return None

def scrape_inventory():
    BASE_URL = "https://www.cargurus.com/Cars/inventorylisting/viewDetailsFilterViewInventoryListing.action"
    params = "?zip=76504&distance=100&sortDir=ASC&sourceContext=carGurusHomePageModel&startYear=1981&maxPrice=1000000&showNegotiable=true&sortType=DEAL_SCORE&page=1"
    all_vehicles = []

    with sync_playwright() as p:
        context = get_context(p)
        page = context.new_page()
        url = BASE_URL + params
        print(f"🔍 Visiting {url}")
        page.goto(url, timeout=90000, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)  # Wait for JS & cars to load

        html = page.content()
        context.close()

        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select(".cg-listingRow") or soup.select(".card-listing")  # adapt as needed

        print(f"→ Found {len(cards)} vehicle cards")
        for card in cards:
            v = parse_vehicle(card)
            if v:
                all_vehicles.append(v)
    return all_vehicles

def sync_to_supabase(vehicles):
    print(f"🚚 Syncing {len(vehicles)} vehicles to Supabase...")
    for v in vehicles:
        print(f"Pushing {v['year']} {v['make']} {v['model']} @ ${v['price']}")
        supabase.table("market_comps").upsert(v, on_conflict="url").execute()

def main():
    vehicles = scrape_inventory()
    if not vehicles:
        print("⚠️ No vehicles found.")
        return
    sync_to_supabase(vehicles)
    print("✅ Done.")

if __name__ == "__main__":
    main()
