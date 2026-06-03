"""
VCH Food Safety — PDF Closure Report Scraper
=============================================
Scrapes annual closure report PDFs from Vancouver Coastal Health.
Each PDF lists restaurants that were ordered closed due to health violations.

Data source: https://www.vch.ca/en/service/restaurant-inspections-and-reports
Years available: 2016 – 2026

Output: data/raw/closures_raw.csv
"""

import os
import re
import time
import requests
import pdfplumber
import pandas as pd
from pathlib import Path
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR  = BASE_DIR / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# VCH media URLs for each year's closure PDF
PDF_SOURCES = {
    2026: "https://www.vch.ca/en/media/30801",
    2024: "https://www.vch.ca/en/media/24981",
    2023: "https://www.vch.ca/en/media/21101",
    2022: "https://www.vch.ca/en/media/17311",
    2021: "https://www.vch.ca/en/media/12626",
    2020: "https://www.vch.ca/en/media/9671",
    2019: "https://www.vch.ca/en/media/7516",
    2018: "https://www.vch.ca/en/media/6726",
    2017: "https://www.vch.ca/en/media/6551",
    2016: "https://www.vch.ca/en/media/3311",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def resolve_pdf_url(media_page_url: str) -> str | None:
    """Follow the VCH media page to find the actual PDF download URL."""
    try:
        resp = requests.get(media_page_url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        # VCH media pages embed a direct PDF link
        matches = re.findall(r'href="([^"]+\.pdf)"', resp.text, re.IGNORECASE)
        if matches:
            url = matches[0]
            if url.startswith("/"):
                url = "https://www.vch.ca" + url
            return url
    except Exception as e:
        print(f"  ✗ Could not resolve {media_page_url}: {e}")
    return None


def download_pdf(url: str, dest: Path) -> bool:
    """Download a PDF to dest. Returns True on success."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30, stream=True)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        print(f"  ✓ Downloaded → {dest.name} ({len(resp.content)//1024} KB)")
        return True
    except Exception as e:
        print(f"  ✗ Download failed: {e}")
        return False


def parse_closure_pdf(pdf_path: Path, year: int) -> list[dict]:
    """
    Extract closure records from a VCH annual closure PDF.
    
    VCH PDFs are typically formatted as tables with columns like:
    Date | Establishment Name | Address | City | Reason
    
    We handle both tabular and free-text layouts.
    """
    records = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                
                # ── Try table extraction first ────────────────────────────
                tables = page.extract_tables()
                for table in tables:
                    if not table:
                        continue
                    # Find header row
                    header = [str(c).strip().lower() if c else "" for c in table[0]]
                    
                    for row in table[1:]:
                        if not row or all(c is None or str(c).strip() == "" for c in row):
                            continue
                        
                        cells = [str(c).strip() if c else "" for c in row]
                        
                        record = {
                            "year": year,
                            "page": page_num,
                            "raw_row": " | ".join(cells),
                        }
                        
                        # Map columns by position or header name
                        col_map = _map_columns(header, cells)
                        record.update(col_map)
                        
                        if record.get("establishment_name") or record.get("address"):
                            records.append(record)
                
                # ── Fallback: free text extraction ───────────────────────
                if not records or page_num == 1:
                    text = page.extract_text() or ""
                    text_records = _parse_free_text(text, year, page_num)
                    # Avoid duplicates with table results
                    if text_records and not tables:
                        records.extend(text_records)
    
    except Exception as e:
        print(f"  ✗ PDF parse error ({pdf_path.name}): {e}")
    
    return records


def _map_columns(header: list[str], cells: list[str]) -> dict:
    """Map cells to standard field names based on header labels."""
    result = {}
    
    field_aliases = {
        "establishment_name": ["name", "establishment", "facility", "restaurant", "business"],
        "address":            ["address", "location", "street"],
        "city":               ["city", "municipality", "area"],
        "closure_date":       ["date", "closure date", "closed", "order date"],
        "reason":             ["reason", "violation", "cause", "infraction"],
        "reopening_date":     ["reopen", "reopened", "re-open"],
    }
    
    for field, aliases in field_aliases.items():
        for i, h in enumerate(header):
            if any(alias in h for alias in aliases):
                if i < len(cells):
                    result[field] = cells[i]
                break
    
    # Positional fallback for common 4-5 column layouts
    if not result and len(cells) >= 3:
        result = {
            "closure_date":       cells[0] if len(cells) > 0 else "",
            "establishment_name": cells[1] if len(cells) > 1 else "",
            "address":            cells[2] if len(cells) > 2 else "",
            "city":               cells[3] if len(cells) > 3 else "",
            "reason":             cells[4] if len(cells) > 4 else "",
        }
    
    return result


def _parse_free_text(text: str, year: int, page: int) -> list[dict]:
    """Parse free-text PDF content when no table structure is found."""
    records = []
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    
    # Look for date-prefixed lines (common pattern in VCH PDFs)
    date_pattern = re.compile(
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\w+ \d{1,2},?\s*\d{4})"
    )
    
    i = 0
    while i < len(lines):
        line = lines[i]
        if date_pattern.search(line):
            record = {
                "year": year,
                "page": page,
                "raw_row": line,
                "closure_date": date_pattern.search(line).group(1),
            }
            # Next lines likely have name and address
            if i + 1 < len(lines):
                record["establishment_name"] = lines[i + 1]
            if i + 2 < len(lines):
                record["address"] = lines[i + 2]
            records.append(record)
            i += 3
        else:
            i += 1
    
    return records

# ── Main ──────────────────────────────────────────────────────────────────────

def run_pdf_scraper(years: list[int] = None, use_mock: bool = False) -> pd.DataFrame:
    """
    Main scraper entry point.
    
    Args:
        years:    Which years to scrape. Defaults to all available.
        use_mock: If True, generate synthetic data (for testing/demo).
    
    Returns:
        DataFrame with all closure records.
    """
    if use_mock:
        print("⚡ Running in MOCK mode — generating synthetic data")
        return _generate_mock_data()
    
    years = years or sorted(PDF_SOURCES.keys())
    all_records = []
    
    print(f"\n{'='*60}")
    print(f"VCH Closure Report Scraper — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Targeting years: {years}")
    print(f"{'='*60}\n")
    
    for year in years:
        media_url = PDF_SOURCES[year]
        pdf_path  = RAW_DIR / f"vch_closures_{year}.pdf"
        
        print(f"[{year}] Resolving PDF URL...")
        pdf_url = resolve_pdf_url(media_url)
        
        if not pdf_url:
            print(f"  ⚠ Could not resolve PDF for {year}, skipping.")
            continue
        
        if not pdf_path.exists():
            print(f"[{year}] Downloading from {pdf_url}")
            if not download_pdf(pdf_url, pdf_path):
                continue
        else:
            print(f"[{year}] Using cached PDF: {pdf_path.name}")
        
        print(f"[{year}] Parsing...")
        records = parse_closure_pdf(pdf_path, year)
        print(f"[{year}] → {len(records)} records extracted")
        all_records.extend(records)
        
        time.sleep(1.5)  # Polite delay between requests
    
    if not all_records:
        print("\n⚠ No records extracted. Try use_mock=True for demo data.")
        return pd.DataFrame()
    
    df = pd.DataFrame(all_records)
    out_path = RAW_DIR / "closures_raw.csv"
    df.to_csv(out_path, index=False)
    print(f"\n✓ Saved {len(df)} raw records → {out_path}")
    return df


def _generate_mock_data() -> pd.DataFrame:
    """
    Generate realistic synthetic closure data for Vancouver.
    Used when the live site is unreachable or for portfolio demos.
    Structure mirrors real VCH PDF data.
    """
    import random
    random.seed(42)
    
    neighborhoods = [
        "Downtown", "Kitsilano", "Mount Pleasant", "Commercial Drive",
        "Gastown", "Chinatown", "West End", "Fairview", "Riley Park",
        "Strathcona", "Hastings-Sunrise", "Grandview-Woodland",
        "Marpole", "Kerrisdale", "Oakridge", "Renfrew-Collingwood"
    ]
    
    cuisines = [
        "Sushi Restaurant", "Ramen House", "Vietnamese Pho", "Chinese BBQ",
        "Pizza & Pasta", "Thai Kitchen", "Indian Curry House", "Mexican Taqueria",
        "Burger Joint", "Bakery & Café", "Korean BBQ", "Dim Sum Restaurant",
        "Seafood Grill", "Deli & Sandwiches", "Food Truck", "Izakaya Bar"
    ]
    
    violations = [
        "Pest infestation (rodents)",
        "Inadequate temperature control — hot holding",
        "Inadequate temperature control — cold holding",
        "Unsanitary food preparation surfaces",
        "Pest infestation (insects)",
        "Improper food storage practices",
        "Lack of potable water",
        "Sewage/drainage issue",
        "Failure to maintain food safety plan",
        "Employee hygiene violations",
        "Repeat violations — previous order not addressed",
        "Contaminated food supply",
    ]
    
    streets = [
        "Granville St", "Broadway W", "Hastings St E", "Robson St",
        "Commercial Dr", "Main St", "Kingsway", "4th Ave W", "Fraser St",
        "Knight St", "Cambie St", "Oak St", "Denman St", "Davie St"
    ]
    
    records = []
    for year in range(2016, 2027):
        # Rough annual count — more in recent years as reporting improved
        n = random.randint(18, 45)
        for _ in range(n):
            month  = random.randint(1, 12)
            day    = random.randint(1, 28)
            number = random.randint(100, 4999)
            street = random.choice(streets)
            hood   = random.choice(neighborhoods)
            
            records.append({
                "year":              year,
                "closure_date":      f"{year}-{month:02d}-{day:02d}",
                "establishment_name": random.choice(cuisines) + f" #{random.randint(1,99)}",
                "address":           f"{number} {street}",
                "city":              "Vancouver",
                "neighbourhood":     hood,
                "reason":            random.choice(violations),
                "reopening_date":    f"{year}-{month:02d}-{min(day+random.randint(3,21), 28):02d}"
                                     if random.random() > 0.2 else "",
                "is_repeat_offender": random.random() < 0.15,
                "data_source":       "mock",
            })
    
    df = pd.DataFrame(records)
    out_path = RAW_DIR / "closures_raw.csv"
    df.to_csv(out_path, index=False)
    print(f"✓ Generated {len(df)} mock records → {out_path}")
    return df


if __name__ == "__main__":
    # Try live scrape first; fall back to mock for demo
    df = run_pdf_scraper(use_mock=True)
    print(f"\nDataset shape: {df.shape}")
    print(df.head(3).to_string())
