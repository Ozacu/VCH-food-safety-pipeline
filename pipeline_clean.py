"""
VCH Food Safety — Cleaning & Transformation Pipeline
=====================================================
Cleans raw scraped data, normalises fields, engineers features,
and produces the analysis-ready dataset.

Input:  data/raw/inspections_raw.csv
        data/raw/closures_raw.csv
Output: data/processed/inspections_clean.csv
        data/processed/closures_clean.csv
        data/processed/combined.csv
"""

import pandas as pd
import numpy as np
from pathlib import Path

BASE_DIR  = Path(__file__).resolve().parent.parent
RAW_DIR   = BASE_DIR / "data" / "raw"
PROC_DIR  = BASE_DIR / "data" / "processed"
PROC_DIR.mkdir(parents=True, exist_ok=True)


# ── Cleaning helpers ──────────────────────────────────────────────────────────

def clean_inspections(df: pd.DataFrame) -> pd.DataFrame:
    """Clean and enrich inspection records."""
    print("Cleaning inspection data...")
    
    df = df.copy()
    
    # ── Dates ────────────────────────────────────────────────────────────────
    df["inspection_date"] = pd.to_datetime(df["inspection_date"], errors="coerce")
    df = df.dropna(subset=["inspection_date"])
    df["inspection_year"]    = df["inspection_date"].dt.year
    df["inspection_month"]   = df["inspection_date"].dt.month
    df["inspection_quarter"] = df["inspection_date"].dt.quarter
    df["inspection_dow"]     = df["inspection_date"].dt.day_name()
    
    # ── Text normalisation ────────────────────────────────────────────────────
    for col in ["establishment_name", "address", "neighbourhood", "establishment_type"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.title()
    
    df["result"] = df["result"].astype(str).str.strip()
    
    # ── Derived fields ────────────────────────────────────────────────────────
    df["result_severity"] = df["result"].map({
        "Passed":                 0,
        "Passed With Violations": 1,
        "Passed with Violations": 1,
        "Failed":                 2,
        "Closed":                 3,
    }).fillna(0).astype(int)
    
    df["had_violations"] = (df["violation_count"] > 0).astype(int)
    
    df["is_critical_result"] = df["result_severity"].isin([2, 3]).astype(int)
    
    # ── Violation category buckets ────────────────────────────────────────────
    def categorise_violations(viol_text: str) -> str:
        viol_text = str(viol_text).lower()
        if "pest" in viol_text or "rodent" in viol_text or "insect" in viol_text:
            return "Pest Infestation"
        if "temperature" in viol_text or "cold holding" in viol_text or "hot holding" in viol_text:
            return "Temperature Control"
        if "sanitiz" in viol_text or "clean" in viol_text or "surface" in viol_text:
            return "Sanitation"
        if "handwash" in viol_text or "hygiene" in viol_text or "employee" in viol_text:
            return "Employee Hygiene"
        if "storage" in viol_text or "stored" in viol_text:
            return "Food Storage"
        if "plan" in viol_text or "label" in viol_text or "record" in viol_text:
            return "Documentation"
        if viol_text.strip() in ("", "nan"):
            return "None"
        return "Other"
    
    df["primary_violation_category"] = df["violations"].apply(categorise_violations)
    
    # ── Repeat offender flag ──────────────────────────────────────────────────
    fail_counts = (
        df[df["result_severity"] >= 2]
        .groupby("establishment_id")
        .size()
        .rename("fail_count")
    )
    df = df.merge(fail_counts, on="establishment_id", how="left")
    df["fail_count"]      = df["fail_count"].fillna(0).astype(int)
    df["is_repeat_offender"] = (df["fail_count"] >= 2).astype(int)
    
    print(f"  → {len(df):,} clean inspection records")
    return df


def clean_closures(df: pd.DataFrame) -> pd.DataFrame:
    """Clean closure report records."""
    print("Cleaning closure data...")
    
    df = df.copy()
    
    df["closure_date"]   = pd.to_datetime(df.get("closure_date", ""), errors="coerce")
    df["reopening_date"] = pd.to_datetime(df.get("reopening_date", ""), errors="coerce")
    
    df["closure_year"]  = df["closure_date"].dt.year.fillna(df.get("year", 0))
    df["closure_month"] = df["closure_date"].dt.month
    
    # Days closed
    df["days_closed"] = (
        (df["reopening_date"] - df["closure_date"])
        .dt.days
        .clip(lower=0)
    )
    
    for col in ["establishment_name", "address", "city"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.title()
    
    print(f"  → {len(df):,} clean closure records")
    return df


def build_neighbourhood_summary(df_insp: pd.DataFrame) -> pd.DataFrame:
    """Aggregate inspection metrics by neighbourhood."""
    grp = df_insp.groupby("neighbourhood").agg(
        total_inspections   = ("establishment_id", "count"),
        unique_establishments = ("establishment_id", "nunique"),
        avg_violations      = ("violation_count", "mean"),
        pct_failed          = ("is_critical_result", "mean"),
        total_closures      = ("result_severity", lambda x: (x == 3).sum()),
    ).reset_index()
    
    grp["avg_violations"] = grp["avg_violations"].round(2)
    grp["pct_failed"]     = (grp["pct_failed"] * 100).round(1)
    grp["risk_score"]     = (
        grp["avg_violations"] * 0.4 +
        grp["pct_failed"]     * 0.4 +
        grp["total_closures"] * 0.2
    ).round(2)
    
    grp = grp.sort_values("risk_score", ascending=False)
    return grp


def build_violation_trend(df_insp: pd.DataFrame) -> pd.DataFrame:
    """Year-over-year violation trend."""
    trend = df_insp.groupby("inspection_year").agg(
        total_inspections = ("establishment_id", "count"),
        avg_violations    = ("violation_count", "mean"),
        pct_failed        = ("is_critical_result", "mean"),
        total_closures    = ("result_severity", lambda x: (x == 3).sum()),
    ).reset_index()
    trend["avg_violations"] = trend["avg_violations"].round(2)
    trend["pct_failed"]     = (trend["pct_failed"] * 100).round(1)
    return trend


# ── Main ──────────────────────────────────────────────────────────────────────

def run_pipeline() -> dict[str, pd.DataFrame]:
    """Run the full cleaning pipeline. Returns dict of DataFrames."""
    
    results = {}
    
    # Load raw data
    insp_raw_path = RAW_DIR / "inspections_raw.csv"
    clos_raw_path = RAW_DIR / "closures_raw.csv"
    
    if insp_raw_path.exists():
        df_insp_raw = pd.read_csv(insp_raw_path)
        df_insp     = clean_inspections(df_insp_raw)
        df_insp.to_csv(PROC_DIR / "inspections_clean.csv", index=False)
        results["inspections"] = df_insp
        
        # Aggregates
        hood_summary = build_neighbourhood_summary(df_insp)
        hood_summary.to_csv(PROC_DIR / "neighbourhood_summary.csv", index=False)
        results["neighbourhood_summary"] = hood_summary
        
        trend = build_violation_trend(df_insp)
        trend.to_csv(PROC_DIR / "violation_trend.csv", index=False)
        results["trend"] = trend
        
        print(f"\n── Neighbourhood Risk Ranking (top 5) ──")
        print(hood_summary.head().to_string(index=False))
    
    if clos_raw_path.exists():
        df_clos_raw = pd.read_csv(clos_raw_path)
        df_clos     = clean_closures(df_clos_raw)
        df_clos.to_csv(PROC_DIR / "closures_clean.csv", index=False)
        results["closures"] = df_clos
    
    print(f"\n✓ Pipeline complete. Files saved to {PROC_DIR}")
    return results


if __name__ == "__main__":
    results = run_pipeline()
    for name, df in results.items():
        print(f"\n[{name}] shape: {df.shape}")
