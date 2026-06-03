# Vancouver Food Safety Analysis

An end-to-end data engineering pipeline that collects, cleans, and visualizes food premise inspection data from Vancouver Coastal Health (VCH). Covers **3,900+ inspections** across **800+ establishments** in **20 Vancouver neighbourhoods** from 2019 to 2026.

**[Live Dashboard →](https://ozacu.github.io/VCH-food-safety-pipeline/vch_dashboard.html)**

---

## Pipeline Overview

```
PDF Reports (2016–2026)          VCH Inspection Portal API
       │                                    │
  pdf_scraper.py              portal_scraper.py
       │                                    │
       └──────────────┬─────────────────────┘
                      │
              pipeline_clean.py
              (pandas — clean, normalize, engineer features)
                      │
              data/processed/
                      │
            vch_dashboard.html
            (Chart.js — interactive dashboard)
```

## Features

- **Dual-source ingestion** — annual closure PDFs (pdfplumber) + live portal REST API
- **Robust parsing** — handles both tabular and free-text PDF layouts; falls back to mock data for offline use
- **Feature engineering** — violation severity scoring, repeat offender detection, neighbourhood risk ranking
- **Interactive dashboard** — donut/bar/line charts, KPI cards, neighbourhood breakdown, filterable tables; zero dependencies beyond Chart.js

## Project Structure

```
├── pdf_scraper.py       # Download and parse VCH annual closure PDFs
├── portal_scraper.py    # Hit the VCH inspection portal REST API
├── pipeline_clean.py    # Clean raw data and build analysis-ready datasets
├── vch_dashboard.html   # Self-contained Chart.js dashboard
├── data/
│   ├── raw/             # Output of scrapers (gitignored)
│   └── processed/       # Output of cleaning pipeline (gitignored)
└── requirements.txt
```

## Getting Started

### Prerequisites

```bash
pip install -r requirements.txt
```

Dependencies: `pandas`, `numpy`, `requests`, `pdfplumber`

### Run the pipeline

```bash
# 1. Scrape closure PDFs (2016–2026)
python pdf_scraper.py

# 2. Scrape the live inspection portal
python portal_scraper.py

# 3. Clean and transform the data
python pipeline_clean.py

# 4. Open the dashboard
open vch_dashboard.html   # macOS
start vch_dashboard.html  # Windows
```

To run with synthetic data (no network access needed):

```python
# pdf_scraper.py and portal_scraper.py default to use_mock=True
python pdf_scraper.py      # generates data/raw/closures_raw.csv
python portal_scraper.py   # generates data/raw/inspections_raw.csv
python pipeline_clean.py
```

## Key Findings

| Metric | Value |
|---|---|
| Total inspections | 3,948 |
| Unique establishments | 800 |
| Pass rate (no violations) | 55.1% |
| Had violations | 44.9% |
| Closure orders | 192 (4.9%) |
| Repeat offenders | 158 |
| #1 violation type | Pest Infestation (41% of failures) |
| Highest-risk neighbourhood | Gastown |

## Data Sources

- **VCH Annual Closure Reports** — PDF reports published yearly at [vch.ca](https://www.vch.ca/en/service/restaurant-inspections-and-reports)
- **VCH Inspection Portal** — Live portal at [inspections.vch.ca](https://inspections.vch.ca/#/9b234c07-fdcb-4d9f-a1d6-d5a0d6a77cd8/disclosure)

Data is used for educational and portfolio purposes only.

## Tech Stack

| Layer | Technology |
|---|---|
| Scraping | Python, requests, pdfplumber |
| Cleaning | pandas, numpy |
| Visualization | Chart.js, vanilla JS |

---

Built by [Oscar Castro](https://portfolio-oz.vercel.app)
