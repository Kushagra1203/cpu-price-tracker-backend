# CPU Price Tracker — Backend

A daily ETL pipeline that tracks desktop CPU prices across **7 Indian PC-hardware
retailers**, normalizes product names against a curated specs dictionary, and stores
both the **current snapshot** and an **append-only price history** in a cloud MySQL
database.

Live frontend (auto-refreshed from this pipeline's data):
[cpu-price-tracker.vercel.app](https://cpu-price-tracker.vercel.app/)

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
  spiders/                   7 Scrapy spiders, one per vendor
  validation.py              post-run vendor health check (see below)
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

# tests (no database, no network)
python -m unittest discover -s tests -t .
```

## Current status

| Vendor | GitHub runner | Detail |
|---|---|---|
| MDComputers, The IT Depot, Ezpz, Vedant | ✅ | 63 / 53 / 43 / 41 items |
| Elitehubs | ⚠️ 26 items | first page only; every pagination request answers 429 |
| Vishal Peripherals | ⚠️ intermittent | 10 items when the grid renders before the response is captured |
| PC Studio | ❌ 403 | Cloudflare refuses the runner's IP before any HTML is served |

### What the 2026-11-18 log actually showed

Per-spider totals from that run's `Stored json feed` lines:

```
elitehubs        26      theitdepot   53      mdcomputers  63
pcstudio          0      vedant       41      vishal       10
ezpzsolutions    43
```

Six of seven vendors produced data. Only one is genuinely blocked, and the
individual causes are different:

**PC Studio — blocked (not fixable in code).** One request, one response:

```
<GET https://www.pcstudio.in/product-category/processor/>
Response: <403
... cf.errors.css, cf-no-screenshot-error.png, challenge-platform/.../jsd/main.js
```

That is Cloudflare's error page, arriving in 0.6s. Playwright cannot help: the
rejection happens before the document exists. Same spider from a home
connection returns 67 items. A proxy would fix it; nothing in the parser will.

**Elitehubs — first page only.** The first request (`usf_take=28`) returns 200
and 26 items. The pagination request (`usf_take=56`) answers 307 → 429, then
fails all three retries: `response_status_count/429: 4`. The ceiling is one page
per run.

**Vishal — a race, now fixed.** It yielded 10 items in this run and 0 the run
before, with no error either time. Cause: `playwright_page_methods` was passed
as *tuples*, and scrapy-playwright ignores tuples outright —

```
WARNING: Ignoring ('wait_for_selector', 'div.product-collection'):
         expected PageMethod, got <class 'tuple'>
```

So every `wait_for_selector` in the project had always been skipped, and whether
a vendor's JS-rendered grid existed at capture time came down to luck. The same
latent race explains the 26/53/63 counts being stable while Vishal's and PC
Studio's were not.

**The crash.** Elitehubs also yielded a non-product tile:

```
{'link': 'https://elitehubs.com/collections/processor?...usf_take=28',
 'name': None, 'price': None, 'vendor': 'Elitehubs'}
```

`Response.urljoin(None)` returns the base URL, so that tile became a row with no
name and the collection page as its link. It then killed the normalizer and with
it the whole night's insert. Both ends are now guarded: the spider skips tiles
without a title, and the normalizer drops nameless rows instead of dying.

### Why a local run sees no Elitehubs

The 429 is per-IP, not global. Same code, same day: the GitHub Actions runner
collected 26 Elitehubs rows, a home connection collected 0 —

```
HTTP/2 429   retry-after: 60   server: cloudflare   x-dc: gcp-asia-southeast1
body: local_rate_limited
```

It survives a real browser (Playwright) and a plain JSON endpoint
(`/collections/processor/products.json` returns the same 18 bytes), so it cannot
be JavaScript rendering or a selector problem. Nothing in the code fixes a
blocked IP, and nothing needs fixing while the scheduled runner keeps working.

A local run will therefore fail the vendor check on Elitehubs. That is the
correct outcome: a local snapshot really is incomplete.

## Failure detection

An empty spider result is indistinguishable from a successful one at the process
level, so `master_script.py` checks every vendor's row count after the insert:

* **Absolute floor** (`MIN_ROWS_PER_VENDOR = 3`) — a vendor returning nothing is
  always wrong.
* **Drop vs. last run** (`MIN_FRACTION_OF_PREVIOUS = 0.6`) — a vendor that keeps
  its catalogue but loses most of it is also wrong. This is the case a floor
  alone misses.
* **Disappearance** (`EXPECTED_VENDORS`) — a spider that vanishes entirely is
  reported by name rather than as a silently shorter total. The list holds the
  six vendors the runner can actually reach; PC Studio is deliberately excluded
  because it is blocked there permanently (see *Current status*). It still gets
  its own `pcstudio: 0 items` warning from the per-spider log line, so nothing
  is hidden — only the build is not held hostage by a known, unfixable block.

Failures exit non-zero, so the GitHub Actions run goes red and emails, instead of
completing green with a vendor missing. The check runs *after* the commit, so the
day's partial data is still stored — a red run never loses data, it only demands
attention. The workflow marks the pipeline step `continue-on-error` so the frontend
JSON refresh still runs, then fails the job explicitly afterwards: a partial
snapshot is still worth publishing, but it should still be visible as a failure.

Vendor counts from the last real snapshot are read from `price_history` and
compared against today's, which means the check needs no extra state file.
Each spider also logs its own item count the moment it finishes
(`pcstudio: 0 items - see the spider log above`), so a red build points at the
empty crawler instead of only at the summary.

## Roadmap

- [x] Append-only price history + daily snapshots
- [x] History backfill fitted to market anchors
- [x] Scheduled runs (GitHub Actions, daily 9pm IST)
- [ ] Analytics layer (SQL + pandas) and dashboards (Streamlit, Tableau Public)
