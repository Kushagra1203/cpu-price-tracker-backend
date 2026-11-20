# CPU Price Tracker — Backend

A daily ETL pipeline that tracks desktop CPU prices across **10 Indian PC-hardware
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
   mdcomputers     theitdepot      elitehubs       shweta          computech
   vedant          ezpz            vishal*         sclgaming*      pcstudio
        └───────────────┴───────────────┴───────┬───────┴──────────────┘
                                                ▼
                                    merge + dedup by (link)
                                                ▼
                        normalize_cpu_names.py — match raw listings
                        against cpu_data.csv specs dictionary (98% match)
                                                ▼
                 ┌──────────────────────────────┴─────────────────────────┐
                 ▼                                                        ▼
        cpu_prices (current snapshot,                            price_history (append-only,
        upserted daily, read by website)                         one row per listing per day,
                                                                 is_synthetic flag)
```

`*` = JavaScript-rendered sites handled with `scrapy-playwright` (Vishal's grid
is painted client-side; SCL's listing is too, and its source IP is blocked, so
neither spider can run on a hosted runner).

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
than random fake data, 4 months of history (17 Jul → today, the anchor window) **fitted to observed market
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
  cpu_data.csv               curated specs dictionary (184 CPUs: cores, threads, TDP…)
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

| Vendor | Site's own count | runner (Windows pool) | local (home IP) | Spider |
|---|---|---|---|---|
| MDComputers | 63 — `Showing 1 to 20 of 63 (4 Pages)` | 63 ✅ | 63 ✅ | plain HTML, banner drives pagination |
| The IT Depot | 53 — `Showing 1 to 12 of 53 (5 Pages)` | 53 ✅ | 53 ✅ | plain HTML, banner stop, 3 s delay |
| Vedant Computers | 41 — `Showing 1 to 41 of 41 (1 Pages)` | 41 ✅ | 41 ✅ | one request, `limit=100` |
| Ezpz Solutions | 43 | 43 ✅ | 43 ✅ | plain HTML, next-page link |
| Elitehubs | 50 in stock | 50 ✅ | 50 ✅ | storefront search API, self-reported total |
| Vishal Peripherals | 46 — `46 of 141 products` | 42 ✅ | 42 ✅ | Shopify search, availability filter |
| Shweta Computers | n/a — set has no total | 73 ✅ | 81 ✅ | Shopify `products.json` |
| Computech Store | 101 — 6 pages of 20 | 101 ✅ | 101 ✅ | plain HTML, stops on repeated links |
| SCL Gaming | 70 in stock, all priced, of 213 | 0 ❌ edge-blocked | 70 ✅ | local nightly feeds it |
| PC Studio | 67 — Store API `count: 67` | 0 ❌ edge-blocked | 67 ✅ | Store API JSON, local nightly feeds it |

Every row the runner cannot reach is filled by a second nightly run on the
home network: the GitHub job (21:00 IST, Windows pool) produces 8 of the 10
vendors, and a local cron (21:30 IST) runs the same pipeline from a
residential IP, where all 10 answer. The two runs merge harmlessly:
`price_history` is `INSERT IGNORE` per (vendor, link, date) and `cpu_prices`
upserts, so whichever run reaches a vendor first wins and the other fills
only the gaps.

Each spider now logs `collected N of M`, so a short run names its own deficit
in the log instead of leaving the total row count to be trusted.

### Why each vendor is short, and what changed

**MDComputers — the spider was never broken; a rewrite was.** The honest
record, from the database: 33 consecutive days of 61–66 rows, including 62
items scraped *by the GitHub runner* at 14:02 on 2026-11-19 — six hours
before the first failure ever logged for this vendor. The failures started
with the first run of a rewritten spider that claimed Chrome in its user
agent while sending Scrapy's own TLS fingerprint, which is exactly the
mismatch Cloudflare flags. The rewrite also read the *rendered* DOM, where
the page's JavaScript leaves stale tiles behind: a page that says 20 products
rendered 23, with one CPU duplicated and another missing entirely. Reading
the server's HTML is what makes the per-page count come out exactly right.

Both changes were reverted. The spider is back to the original 42-line
plain-HTML version, and the runner run of 2026-11-19 22:26 UTC produced 63 of
63 through it. The wrong theory — "the runner's IP is blocked" — cost two
days here, and it is kept in this section on purpose: the next plausible
story about a vendor failing deserves the same check against history first.

**The IT Depot — 0 rows, then 53.** Not a parser problem: the five listing
pages are ~1 MB of HTML each and the spider fetched them back to back with no
delay, which tripped the site's LiteSpeed rate limiter (`response_status_count
/429: 4`). The same five pages returned 200 from an ordinary connection minutes
later. It now runs at one request every 3s with AutoThrottle and stops at the
page count the banner states, instead of guessing from an empty response.

**Elitehubs — the grid was never the data source.** The collection page is
painted by a client-side filter app, and a headless browser only materialises
21–26 of the 50 in-stock processors the site's own filter advertises, at every
`usf_take` from 28 to 100 — so no amount of pointing at divs could close the
gap. The page fills its grid from a hosted search API, and that API answers
the same question in one request with a `total` field: 50 products, each with
price and stock on hand. The spider reads the API and checks its own rows
against the site's number (`captured N of the site's 50`); first run was 50
of 50, and every price the old tile spider ever produced matches the API's
value, so it is the same catalogue read whole instead of read as far as the
page painted it.

**Vishal Peripherals — 10 of 46, now 42.** The spider was reading
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
`/wp-json/wc/store/v1/products/categories?slug=processor` (`count: 67`).

The 2026-11-19 run answered that: the JSON route is blocked too, with the same
immediate 403 (`GET /wp-json/wc/store/v1/products?category=113&per_page=100 →
403`). So this is not a Cloudflare HTML challenge that a browser could solve —
it is the IP, on every route. The 2026-11-19/20 experiments extended that:
the Windows runner pool is refused identically, so neither hosted IP range
serves this site. The same spider returns all 67 rows from a home connection,
and the local nightly run (21:30 IST) is what puts them in the database.

**Computech Store — new, 101 products.** A custom Tailwind/htmx storefront, not
WooCommerce (every `/wp-json/` route is 404), so it is scraped from the grid at
20 per page. Pagination stops on a page that adds no new product links: asking
for a page past the end re-serves the last page instead of returning nothing,
so a "stop when the page looks short" rule would loop forever whenever the
catalogue size is an exact multiple of 20.

**SCL Gaming — 70 in stock of 213.** Availability is not visible on the
listing: an out-of-stock card shows the same photo and often the same price as
a buyable one, and the theme never renders the words "Out of stock" — not on
the listing, and not on the product page either. Of the 213 processors, 119 are
out of stock but still priced, 24 are out of stock with an empty `<p class="price">`
and no add-to-cart button, and 70 are in stock and priced. The Ryzen 5 5600X is
listed at ₹12,250 while being unbuyable, so price cannot stand in for stock.

WooCommerce does put the state in each card's class attribute
(`instock` / `outofstock`), and that matched the product page for every card
checked. The spider keeps only `instock` cards and then requires a price, so an
unpriced card cannot become a row even if its class were wrong. Without the
stock filter it would have stored 119 unbuyable prices, mostly older
generations the store leaves buried rather than delisting.

The 15:46 run moved it onto Playwright and it still returned 403 — in 0.2 s,
with `cf.errors.css` and `cf-no-screenshot-error.png` in the response. The
2026-11-19/20 experiments closed the remaining routes: the Windows runner
pool is refused identically, and the WooCommerce Store API — which answers
200 from a residential connection with the same 213 products, prices, and
stock flags — is 403 from both pools too. The block covers every route from
both hosted IP ranges, so no runner change reaches this vendor; the local
nightly run (21:30 IST) puts its 70 rows in the database from the home IP.

**Shweta Computers — re-added, via Shopify JSON.** The old spider pinned
`filter.v.price.lte=69699` into its URL, so every processor above ₹69,699 was
invisible to it, and it guessed between five card selectors. It now reads
`/collections/processor/products.json`, which returns title, handle, and
variants with price and an `available` flag — no theme selectors at all. The
site rate-limits hard (`429`, body `local_rate_limited`), so whether the runner
gets through is only knowable from a run; the spider logs the status and
payload head instead of raising.

The 429 is a per-IP budget on Shopify's side, and GitHub runners share egress
IPs with thousands of other jobs, so whether a run draws one with budget left
is a lottery. Measured on 2026-11-19/20: the same hour produced 429 seven
times on the Ubuntu pool and 200-first-try with 81 rows on the Windows pool —
twice. The nightly job therefore runs on the Windows pool
(`.github/workflows/daily-scrape.yml`), where the budget has been clean on
every draw so far; the local nightly run covers any night the pool is spent.

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

### Why Elitehubs stopped being a 429 problem

Until 2026-11-19 the spider read the collection page's rendered grid, and the
storefront's Cloudflare answered some IPs with 429 (`local_rate_limited`) —
the GitHub runner collected 26 rows while a home connection collected 0 on
the same day. Reading the storefront's search API on a different host
(`svc-3-usf.hotyon.com`) removed that exposure entirely: the API has never
rate-limited either pool, and it is where the page's own data comes from.

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
  eight vendors the runner can actually reach. SCL Gaming and PC Studio are
  excluded because both hosted IP pools are proven refused on every route
  (Store API included), so keeping them expected would fail the job every
  night for a cause no code change can fix, which is how a useful alert turns
  into wallpaper. Their rows come from the local nightly run, which runs the
  same check over all ten vendors. Their runner logs still print a
  `0 items` line, so they are named, not hidden.

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
