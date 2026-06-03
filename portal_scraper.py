"""
VCH Food Safety — Inspection Portal Scraper
============================================
Scrapes the live VCH inspection portal for detailed per-establishment
inspection records, violations, and scores.

Portal: https://inspections.vch.ca/#/9b234c07-fdcb-4d9f-a1d6-d5a0d6a77cd8/disclosure

The portal is a React SPA backed by a REST API. This scraper
hits the underlying API endpoints directly.

Output: data/raw/inspections_raw.csv
"""

import time
import json
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR  = BASE_DIR / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

# VCH portal API base — discovered by inspecting network traffic
VCH_API_BASE = "https://inspections.vch.ca/api"
PORTAL_ID    = "9b234c07-fdcb-4d9f-a1d6-d5a0d6a77cd8"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/json",
    "Referer":         "https://inspections.vch.ca/",
    "Origin":          "https://inspections.vch.ca",
}

NEIGHBOURHOODS = [
    "Downtown", "Kitsilano", "Mount Pleasant", "Commercial Drive",
    "Gastown", "Chinatown", "West End", "Fairview", "Riley Park",
    "Strathcona", "Hastings-Sunrise", "Grandview-Woodland",
    "Marpole", "Kerrisdale", "Oakridge", "Renfrew-Collingwood",
    "Dunbar", "Point Grey", "Shaughnessy", "South Cambie",
]


def fetch_establishments(session: requests.Session, page: int = 0, size: int = 100) -> dict:
    """Query the VCH API for a page of food establishments."""
    url = f"{VCH_API_BASE}/disclosure/{PORTAL_ID}/search"
    params = {
        "pageNumber": page,
        "pageSize":   size,
        "type":       "Food Premises",
    }
    try:
        resp = session.get(url, params=params, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  ✗ API error (page {page}): {e}")
        return {}


def fetch_establishment_detail(session: requests.Session, establishment_id: str) -> dict:
    """Fetch detailed inspection history for one establishment."""
    url = f"{VCH_API_BASE}/disclosure/{PORTAL_ID}/establishment/{establishment_id}"
    try:
        resp = session.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  ✗ Detail fetch error ({establishment_id}): {e}")
        return {}


def scrape_portal(max_pages: int = 10, use_mock: bool = True) -> pd.DataFrame:
    """
    Main portal scraper.
    
    Args:
        max_pages: How many API pages to scrape (100 records/page).
        use_mock:  Generate synthetic data if True.
    
    Returns:
        DataFrame with inspection records.
    """
    if use_mock:
        print("⚡ Running portal scraper in MOCK mode")
        return _generate_mock_inspections()
    
    session = requests.Session()
    all_records = []
    
    print(f"\n{'='*60}")
    print(f"VCH Portal Scraper — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")
    
    for page in range(max_pages):
        print(f"Fetching establishments page {page + 1}/{max_pages}...")
        data = fetch_establishments(session, page=page)
        
        if not data or "items" not in data:
            print(f"  No more data at page {page}. Stopping.")
            break
        
        items = data["items"]
        if not items:
            break
        
        print(f"  → {len(items)} establishments on this page")
        
        for item in items:
            est_id   = item.get("id", "")
            est_name = item.get("name", "")
            address  = item.get("address", "")
            city     = item.get("city", "")
            
            # Fetch detail for each establishment
            detail = fetch_establishment_detail(session, est_id)
            inspections = detail.get("inspections", [])
            
            for insp in inspections:
                record = {
                    "establishment_id":   est_id,
                    "establishment_name": est_name,
                    "address":            address,
                    "city":               city,
                    "inspection_date":    insp.get("date", ""),
                    "inspection_type":    insp.get("type", ""),
                    "result":             insp.get("result", ""),
                    "violation_count":    len(insp.get("violations", [])),
                    "violations":         "; ".join(
                        v.get("description", "") for v in insp.get("violations", [])
                    ),
                }
                all_records.append(record)
            
            time.sleep(0.3)  # Polite delay
        
        time.sleep(1.0)
    
    if not all_records:
        print("⚠ No live data retrieved. Falling back to mock.")
        return _generate_mock_inspections()
    
    df = pd.DataFrame(all_records)
    out_path = RAW_DIR / "inspections_raw.csv"
    df.to_csv(out_path, index=False)
    print(f"\n✓ Saved {len(df)} inspection records → {out_path}")
    return df


def _generate_mock_inspections() -> pd.DataFrame:
    """
    Realistic synthetic inspection data mirroring the VCH portal schema.
    ~5,000 records across 800 establishments, 2019–2026.
    """
    import random
    random.seed(99)
    
    violation_types = [
        "Temperature control — hot holding below 60°C",
        "Temperature control — cold holding above 4°C",
        "Pest evidence — rodent droppings observed",
        "Pest evidence — insect activity",
        "Food contact surfaces not sanitized",
        "Employee handwashing facilities inadequate",
        "Food stored on floor",
        "Raw meat stored above ready-to-eat foods",
        "No food safety plan on premises",
        "Thawing procedures not followed",
        "Date labelling missing on stored foods",
        "Cleaning schedule not maintained",
        "Equipment in disrepair",
        "Inadequate ventilation",
    ]
    
    establishment_types = [
        "Restaurant", "Food Truck", "Café", "Bakery",
        "Catering", "Grocery/Deli", "Food Market Stall",
    ]
    
    inspection_types = ["Routine", "Follow-up", "Complaint-driven"]
    results         = ["Passed", "Passed with Violations", "Failed", "Closed"]
    result_weights  = [0.55, 0.28, 0.12, 0.05]
    
    streets = [
        "Granville St", "Broadway W", "Hastings St E", "Robson St",
        "Commercial Dr", "Main St", "Kingsway", "4th Ave W",
        "Fraser St", "Knight St", "Cambie St", "Denman St",
    ]
    
    # Create establishments
    establishments = []
    for i in range(800):
        hood = random.choice(NEIGHBOURHOODS)
        establishments.append({
            "id":   f"EST{i:04d}",
            "name": f"{random.choice(establishment_types)} {i+1:03d}",
            "address": f"{random.randint(100,4999)} {random.choice(streets)}",
            "neighbourhood": hood,
            "type": random.choice(establishment_types),
        })
    
    records = []
    for est in establishments:
        # Each establishment gets 2–8 inspections over the years
        n_inspections = random.randint(2, 8)
        for _ in range(n_inspections):
            year   = random.randint(2019, 2026)
            month  = random.randint(1, 12)
            day    = random.randint(1, 28)
            result = random.choices(results, weights=result_weights)[0]
            
            # Violation count depends on result
            if result == "Passed":
                n_viol = 0
            elif result == "Passed with Violations":
                n_viol = random.randint(1, 3)
            elif result == "Failed":
                n_viol = random.randint(3, 7)
            else:  # Closed
                n_viol = random.randint(5, 10)
            
            violations = random.sample(violation_types, min(n_viol, len(violation_types)))
            
            records.append({
                "establishment_id":   est["id"],
                "establishment_name": est["name"],
                "address":            est["address"],
                "neighbourhood":      est["neighbourhood"],
                "establishment_type": est["type"],
                "inspection_date":    f"{year}-{month:02d}-{day:02d}",
                "inspection_year":    year,
                "inspection_month":   month,
                "inspection_type":    random.choice(inspection_types),
                "result":             result,
                "violation_count":    n_viol,
                "violations":         " | ".join(violations),
                "data_source":        "mock",
            })
    
    df = pd.DataFrame(records)
    out_path = RAW_DIR / "inspections_raw.csv"
    df.to_csv(out_path, index=False)
    print(f"✓ Generated {len(df)} mock inspection records → {out_path}")
    return df


if __name__ == "__main__":
    df = scrape_portal(use_mock=True)
    print(f"\nShape: {df.shape}")
    print(df["result"].value_counts())
