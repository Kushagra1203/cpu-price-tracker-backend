"""
export_website_json.py — export MySQL data to the frontend repo's JSON files.

Produces:
  data/processors.json     current snapshot (same schema as processors_standardized.json)
  data/price-history.json  {"cpus": [{slug, name, history: [{date, vendor, price}]}]}

Usage:
  .venv/bin/python export_website_json.py [frontend_repo_path]
  (default: ~/dev/CPU-Price-Tracker)
"""
import json
import os
import re
import sys
from datetime import date

BASE = os.path.dirname(os.path.abspath(__file__))

SAMPLE_STEP = 2  # keep every Nth day of history to bound JSON size


def slugify_frontend(s):
    """MUST match frontend: standard_name.toLowerCase().replace(/\\s+/g, '-')"""
    return s.lower().replace(" ", "-")


def main():
    from dotenv import load_dotenv
    import mysql.connector

    load_dotenv(os.path.join(BASE, ".env"))
    conn = mysql.connector.connect(
        host=os.getenv("DB_HOST"), port=int(os.getenv("DB_PORT", 3306)),
        user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"), ssl_ca=os.getenv("DB_SSL_CA"),
    )
    cur = conn.cursor(dictionary=True)

    # ---- processors.json (current snapshot + specs) ----
    cur.execute("""
        SELECT name, link, price, vendor, brand, generation, series,
               cores, threads, base_clock_ghz, tdp_watt
        FROM cpu_prices
        WHERE price IS NOT NULL AND price > 0""")
    processors = []
    for r in cur.fetchall():
        processors.append({
            "name": r["name"],
            "link": r["link"],
            "price": r["price"],
            "vendor": r["vendor"],
            "standard_name": r["name"],
            "brand": r["brand"] or "Others",
            "generation": r["generation"] or "Others",
            "series": r["series"] or "Others",
            "cores": r["cores"],
            "threads": r["threads"],
            "base_clock_ghz": r["base_clock_ghz"],
            "tdp_watt": r["tdp_watt"],
        })

    # ---- price-history.json ----
    cur.execute("""
        SELECT name, vendor, price, snapshot_date
        FROM price_history
        WHERE price IS NOT NULL AND price > 0
        ORDER BY name, vendor, snapshot_date""")
    by_cpu = {}
    for r in cur.fetchall():
        by_cpu.setdefault(r["name"], []).append(
            (r["snapshot_date"].isoformat(), r["vendor"], r["price"]))

    cpus = []
    for name, entries in sorted(by_cpu.items()):
        # downsample: keep every Nth day per (cpu, vendor) + always the last day
        by_vendor = {}
        for d, v, p in entries:
            by_vendor.setdefault(v, []).append((d, p))
        history = []
        for v, pts in sorted(by_vendor.items()):
            pts.sort()
            for i, (d, p) in enumerate(pts):
                if i % SAMPLE_STEP == 0 or i == len(pts) - 1:
                    history.append({"date": d, "vendor": v, "price": p})
        history.sort(key=lambda x: x["date"])
        cpus.append({"slug": slugify_frontend(name), "name": name, "history": history})

    cur.close()
    conn.close()

    target = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/dev/CPU-Price-Tracker")
    data_dir = os.path.join(target, "data")
    os.makedirs(data_dir, exist_ok=True)

    p1 = os.path.join(data_dir, "processors.json")
    p2 = os.path.join(data_dir, "price-history.json")
    with open(p1, "w", encoding="utf-8") as f:
        json.dump(processors, f, indent=1)
    with open(p2, "w", encoding="utf-8") as f:
        json.dump({"cpus": cpus}, f, indent=1)

    print(f"processors.json: {len(processors)} listings -> {p1} ({os.path.getsize(p1)//1024} KB)")
    print(f"price-history.json: {len(cpus)} CPUs -> {p2} ({os.path.getsize(p2)//1024} KB)")


if __name__ == "__main__":
    main()
