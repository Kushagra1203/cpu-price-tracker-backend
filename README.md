# CPU Price Tracker — Backend

A daily ETL pipeline that tracks desktop CPU prices across **7 Indian PC-hardware
retailers**, normalizes product names against a curated specs dictionary, and stores
both the **current snapshot** and an **append-only price history** in a cloud MySQL
database.

Live frontend (auto-refreshed from this pipeline's data):
[v0-cpu-price-tracker.vercel.app](https://cpu-price-tracker.vercel.app/)

> **Why this exists:** no Indian website tracks CPU prices across multiple retailers
> over time with per-spec filtering. This project is that tracker, built from scratch —
> scraping, cleaning, modeling, storage, and scheduling.

---

## Architecture

```
                ┌──────────────────────────────────────────────────────┐
                │              master_script.py  (daily)               │
                └──────────────────────────────────────────────────────┘
                                        │
        ┌───────────────┬───────────────┼───────────────┬──────────────┐
        ▼               ▼               ▼               ▼              ▼
   Scrapy spiders  Scrapy spiders  Scrapy spiders  Scrapy spiders  Scrapy spiders
   elitehubs*      theitdepot      mdcomputers     pcstudio        vedant, vishal*,
   (Playwright)    (http)          (http)          (Playwright)    ezpz (http)
        └───────────────┴───────────────┴───────┬───────┴──────────────┘
                                                ▼
                                    merge + dedup by (link)
                                                ▼
                        normalize_cpu_names.py — match raw listings
                        against cpu_data.csv specs dictionary (~99% match)
                                                ▼
                 ┌──────────────────────────────┴─────────────────────────┐
                 ▼                                                        ▼
        cpu_prices (current snapshot,                            price_history (append-only,
        upserted daily, read by website)                         one row per listing per day,
                                                                 is_synthetic flag)
```

`*` = JavaScript-rendered sites handled with `scrapy-playwright`.

## The data model (and why)

**`cpu_prices`** — one row per (vendor, product link). Upserted on every run, so it
always holds the latest observed price. The website reads this.

**`price_history`** — append-only **daily snapshot fact table**: one row per
(vendor, link, snapshot_date), unique-keyed so re-runs are idempotent
(`INSERT IGNORE`), with an `is_synthetic` flag.

> **Design note — daily snapshots vs. start/end intervals (SCD Type 2):**
> Interval-based rows (`start_date`/`end_date`) would store unchanged prices more
> compactly, but daily snapshots won here because (1) the pipeline stays purely
> append-only — no update path, idempotent re-runs; (2) missed scrape days remain
> honest gaps instead of silently extending an interval; (3) "price unchanged for
> N days" is itself signal (price stickiness, listing still alive); (4) trend
> queries map directly to analytics without date-spine joins; (5) at ~65K rows/6
> months, storage is negligible. A gaps-and-islands view can derive intervals from
> snapshots anytime if ever needed.

## Backfilled history (synthetic, clearly flagged)

Real history only exists since Oct 2026, so the charts needed a backfill. Rather
than random fake data, 3 months of history (the anchor window) **fitted to observed market
anchors**:

1. `backfill/pcpt_reference_scraper.py` scraped 90-day price-trend charts of a
   public Indian price tracker (headful browser only to clear a Cloudflare
   challenge once, then fully headless `curl_cffi` at ~1 req/s) — anchor series
   for **118 of 173** dictionary CPUs (`backfill/anchors/reference_prices.json`).
   CPUs the tracker doesn't cover fall back to MSRP + generation-aware drift.
2. `backfill/generate_synthetic.py` scales each anchor path per-listing so it
   passes through the listing's **real current price** at the join date (no seam
   between synthetic and real), rounds to realistic ₹ endings, and flags every
   row `is_synthetic = 1`.
3. **Purge plan:** once ~3 months of real daily data accumulate, one query
   (`DELETE FROM price_history WHERE is_synthetic = 1`) removes the synthetic
   layer and the charts stay continuous.

## Repo layout

```
master_script.py             daily orchestrator: spiders → merge → normalize → MySQL
backfill/                    one-time history backfill (scripts + anchor data)
cpu_price_tracker/
  spiders/                   9 Scrapy spiders (7 active vendors)
  normalize_cpu_names.py     raw name cleaning + specs-dictionary matching
  cpu_data.csv               curated specs dictionary (185 CPUs: cores, threads, TDP…)
  settings.py                Scrapy config (Playwright handlers, delays, UA)
certs/ca.pem                 Aiven MySQL CA certificate (gitignored)
```

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium

# .env (not committed)
DB_HOST=... DB_PORT=... DB_USER=... DB_PASSWORD=... DB_NAME=...
DB_SSL_CA=certs/ca.pem

.venv/bin/python master_script.py
```

## Current status

| Vendor | State |
|---|---|
| MDComputers, PC Studio, Elitehubs, The IT Depot, Ezpz, Vedant | ✅ daily |
| Vishal Peripherals | ⚠️ intermittent (aggressive rate limiting; Playwright-based) |
| SCL Gaming | 🚧 paused — product grid only renders per-product pages |
| Shweta Computers | ❌ removed — prices pulled from site ("call for price") |

## Roadmap

- [x] Append-only price history + daily snapshots
- [x] History backfill fitted to market anchors
- [x] Scheduled runs (GitHub Actions, daily 9pm IST)
- [ ] Analytics layer (SQL + pandas) and dashboards (Streamlit, Tableau Public)
- [ ] sclgaming spider rebuild
