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
  spiders/                   10 Scrapy spiders, one per vendor
  validation.py              post-run vendor health check (see below)
  listing.py                 parses a vendor's own "Showing X of N" total
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

Every count below is the vendor's own, read off the page or the API — not a
number typed in by hand. That distinction is the point: a hard-coded expected
count rots the moment a vendor adds a CPU, while the site's banner cannot.

| Vendor | Site's own count | Last run | Spider |
|---|---|---|---|
| MDComputers | 62 — `Showing 1 to 20 of 62 (4 Pages)` | 62 ✅ | page walk, stops at the stated page count |
| The IT Depot | 53 — `Showing 1 to 12 of 53 (5 Pages)` | 0 ⚠️ | page walk, throttled |
| Vedant Computers | 41 — `Showing 1 to 41 of 41 (1 Pages)` | 41 ✅ | one request, `limit=100` |
| Ezpz Solutions | 43 | 43 ✅ | page walk |
| Elitehubs | 50 in stock | 21 ⚠️ | one request, `usf_take=100` |
| Vishal Peripherals | 46 — `46 of 141 products` | 10 ⚠️ | filtered search URL, 3 pages |
| PC Studio | 67 — Store API `count: 67` | 0 ❌ | Store API JSON |
| Computech Store | 101 — 6 pages of 20 | — | page walk, stops on repeated links |
| SCL Gaming | 70 in stock of 213 | — | page walk, keeps `instock` cards only |
| Shweta Computers | n/a — set has no total | — | Shopify `products.json`, available variants only |

Each spider now logs `collected N of M`, so a short run names its own deficit
in the log instead of leaving the total row count to be trusted.

### Why each vendor is short, and what changed

**The IT Depot — 0 rows, then 53.** Not a parser problem: the five listing
pages are ~1 MB of HTML each and the spider fetched them back to back with no
delay, which tripped the site's LiteSpeed rate limiter (`response_status_count
/429: 4`). The same five pages returned 200 from an ordinary connection minutes
later. It now runs at one request every 3s with AutoThrottle and stops at the
page count the banner states, instead of guessing from an empty response.

**Elitehubs — 21 of 50.** `usf_take` is how many tiles the collection renders
in one response. It was 28, so the spider saw 21-26 of the 50 in-stock
processors; asking for a second page earned a 307 followed by four 429s
(`response_status_count/429: 4`). It now asks for 100 in the single request the
site will serve, and only paginates if that page comes back full.

**Vishal Peripherals — 10 of 46.** The spider was reading
`/collections/processors?page=N`, which shows 20 tiles of which half are out of
stock and exposes no working next-page link, so it stopped after one page. The
spider now uses the store search with the availability filter applied
server-side (`/a/search/processors?filter_availability[in_stock]=true`), walks
its three pages, and reads the page's own `46 of 141 products` line as the
target.

**PC Studio — 0 rows, 403 on every attempt.** Cloudflare refuses the runner's
IP before any document is served:

```
<GET https://www.pcstudio.in/product-category/processor/>
Response: <403
... cf.errors.css, cf-no-screenshot-error.png, challenge-platform/.../jsd/main.js
```

Playwright cannot help: the rejection arrives in under a second, ahead of the
document. The storefront is WooCommerce, though, and WooCommerce publishes a
public Store API — `/wp-json/wc/store/v1/products?category=113&per_page=100`
returns the same catalogue as JSON (name, permalink, price, `is_in_stock`).
Category 113 is the Processor term, confirmed via
`/wp-json/wc/store/v1/products/categories?slug=processor` (`count: 67`). The
spider now reads that route: one request, 67 rows, no browser. Whether the
runner's IP is challenged on `/wp-json/` too is the open question — the spider
logs the status and payload head rather than crashing, so the answer arrives in
the next run log.

**Computech Store — new, 101 products.** A custom Tailwind/htmx storefront, not
WooCommerce (every `/wp-json/` route is 404), so it is scraped from the grid at
20 per page. Pagination stops on a page that adds no new product links: asking
for a page past the end re-serves the last page instead of returning nothing,
so a "stop when the page looks short" rule would loop forever whenever the
catalogue size is an exact multiple of 20.

**SCL Gaming — 70 in stock of 213.** Availability is not visible on the
listing: an out-of-stock card shows the same photo and the same price as a
buyable one, and only the product page says "Out of stock". The Ryzen 5 5600X
is listed at ₹12,250 while being unbuyable, so price cannot stand in for stock.
WooCommerce does put the state in each card's class attribute
(`instock` / `outofstock`), and that matches the product page for every card
checked. The spider keeps only `instock` cards — without that it would have
recorded prices for 143 products nobody can buy, mostly older generations the
store leaves buried rather than delisting.

**Shweta Computers — re-added, via Shopify JSON.** The old spider pinned
`filter.v.price.lte=69699` into its URL, so every processor above ₹69,699 was
invisible to it, and it guessed between five card selectors. It now reads
`/collections/processor/products.json`, which returns title, handle, and
variants with price and an `available` flag — no theme selectors at all. The
site rate-limits hard (`429`, body `local_rate_limited`), so whether the runner
gets through is only knowable from a run; the spider logs the status and
payload head instead of raising.

### What the 2026-11-18 log showed

Per-spider totals from that run's `Stored json feed` lines:

```
elitehubs        26      theitdepot   53      mdcomputers  63
pcstudio          0      vedant       41      vishal       10
ezpzsolutions    43
```

Two bugs that run exposed, both now fixed:

**Every `wait_for_selector` in the project had never run.** They were passed as
plain tuples, and scrapy-playwright silently discards those —

```
WARNING: Ignoring ('wait_for_selector', 'div.product-collection'):
         expected PageMethod, got <class 'tuple'>
```

So whether a JavaScript-rendered grid existed at capture time came down to
luck, which is why Vishal yielded 10 one night and 0 the next with no error
either time.

**One Elitehubs tile had no title.**

```
{'link': 'https://elitehubs.com/collections/processor?...usf_take=28',
 'name': None, 'price': None, 'vendor': 'Elitehubs'}
```

`Response.urljoin(None)` returns the base URL, so that tile became a row with no
name and the collection page as its link. It then killed the normalizer and with
it the whole night's insert. Both ends are guarded now: the spider skips
untitled tiles, and the normalizer drops nameless rows instead of dying.

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
  eight vendors the runner must always produce. PC Studio is excluded while its
  new Store API route is unproven from the runner: if the block extends to
  `/wp-json/`, keeping it expected would fail the job every night for a cause no
  code change can fix, which is how a useful alert turns into wallpaper. It is
  added back the moment a run reports its 67 rows. Its per-spider
  `pcstudio: 0 items` line still names it every night, so nothing is hidden.

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
