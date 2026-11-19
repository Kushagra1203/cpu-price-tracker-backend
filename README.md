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

| Vendor | Site's own count | 2026-11-19 15:25 | 2026-11-19 15:46 | Spider |
|---|---|---|---|---|
| MDComputers | 62 — `Showing 1 to 20 of 62 (4 Pages)` | 0 ⚠️ 403 | 0 ⚠️ our bug, fixed | page walk, stops at the stated page count |
| The IT Depot | 53 — `Showing 1 to 12 of 53 (5 Pages)` | 53 ✅ | 53 ✅ | page walk, throttled |
| Vedant Computers | 41 — `Showing 1 to 41 of 41 (1 Pages)` | 41 ✅ | 41 ✅ | one request, `limit=100` |
| Ezpz Solutions | 43 | 43 ✅ | 43 ✅ | page walk |
| Elitehubs | 50 in stock | 24 ⚠️ | 22 ⚠️ | one request, `usf_take=56` |
| Vishal Peripherals | 46 — `46 of 141 products` | 46 ✅ | 46 ✅ | filtered search URL, 3 pages |
| PC Studio | 67 — Store API `count: 67` | 0 ❌ 403 on `/wp-json/` too | 0 ❌ same | Store API JSON |
| Computech Store | 101 — 6 pages of 20 | 101 ✅ | 101 ✅ | page walk, stops on repeated links |
| SCL Gaming | 70 in stock, all priced, of 213 | 0 ⚠️ 403 | 0 ❌ 403 through Chromium too | keeps `instock` cards only |
| Shweta Computers | n/a — set has no total | 81 ✅ | 0 ⚠️ 429, backoff too short | Shopify `products.json` |

The 15:25 run merged 389 raw rows and inserted 378: the other 11 were names the
normalizer could not match against `cpu_data.csv` (`Matched 378, Unmatched 11`),
not crawler losses. It is also why vendor totals can differ slightly from the
per-spider counts — Computech scraped 101 and contributed 99, Shweta 81 → 73.

The 15:46 run was the re-run that tested the fixes above. It merged 306 raw
rows, of which 303 matched a CPU in `cpu_data.csv` (`Matched 303,
Unmatched 3`). Three of its four problems are diagnosed below; the fourth is
that two runs twenty minutes apart is enough to burn the runner's shared IP
budget on Shopify, which is a real constraint rather than a code fault.

Each spider now logs `collected N of M`, so a short run names its own deficit
in the log instead of leaving the total row count to be trusted.

### Why each vendor is short, and what changed

**MDComputers — 403 from the runner, then 0 rows from a bad wait.** From a
residential connection the listing answers 200; from the runner it answered 403
on page 1 with a Chrome *and* a Firefox user agent, while the `Scrapy/2.13.3`
agent is refused from every IP. That rules out the selectors and rules out a
user-agent fix, so the spider now renders through Playwright, which is how
Elitehubs and Vishal already get through Cloudflare from the same runner.

The first Playwright run then produced 0 rows for a second, self-inflicted
reason. `wait_for_selector` defaults to `state="visible"`, the page contained
23 `div.product-wrapper` elements, and the first of them is hidden — so the
wait timed out after 20 s and scrapy-playwright discarded a page that had
loaded perfectly:

```
locator resolved to 23 elements. Proceeding with the first one:
  <div class="product-wrapper">…</div>
Page.wait_for_selector: Timeout 20000ms exceeded.
```

It now waits for `state="attached"`. The lesson is in the log line: a selector
that *resolves* and a selector that *passes* are different questions.

**MDComputers — 23 of 62, and the honest history of "63".** The 16:12 run got
past the wait and pulled 23 rows, which is *fewer* than the 63 the
2026-11-18 run produced — and the run before that, in this repo, got 0. The
spider code was identical for the 63 → 0 transition, so what moved was the
site: MD's Cloudflare started refusing plain Scrapy from the runner's IP
sometime between 18 and 19 November, while still answering 200 from a
residential connection. The old 63 was never a target either — the site's own
banner says **62**, and 63 means one extra row slipped in. Chasing the
previous run's number would have meant chasing the wrong one.

The 16:12 log says where the missing 39 went:

```
16:13:16  Response: <200 https://mdcomputers.in/catalog/processor?page=1>
16:13:21  Response: <403 https://mdcomputers.in/catalog/processor?page=2>
```

Page 1 passed, page 2 was refused, from the same browser, in the same session.
Two plausible causes, both now addressed:

- **The browser was impersonating something it is not.** scrapy-playwright
  copies Scrapy's headers onto the navigation request, so a Chromium 139 was
  announcing itself as Firefox 128 with Scrapy's narrow `Accept-Encoding`.
  `PLAYWRIGHT_PROCESS_REQUEST_HEADERS = None` lets the browser send its own.
- **One listing page cost 90 requests** to the same host: 30 scripts, 20
  stylesheets, 40 images, 5 fonts. The grid is server-rendered — fetched
  without a browser at all, the page carries 20 product titles and the
  banner — so `PLAYWRIGHT_ABORT_REQUEST` now drops every request that is not
  the document on that host, and images and fonts everywhere else (Elitehubs
  made 290 requests in one run and Vishal 808).

`wait_for_selector` no longer raises, so a refusal is now logged as
`HTTP 403` instead of masquerading as a 20-second timeout, and the page is
asked again through a slow download slot rather than ending the crawl. The
selector is also scoped to the listing grid, because the page carries a 21st
`product-wrapper` outside it (a hidden template) and its JavaScript injects
two more — that is how 23 tiles came off a page that says 20. Each page is
now checked against the banner's own range (`Showing 21 to 40 of 62`), so a
short page is named in the log rather than only noticed in the total.

**The IT Depot — 0 rows, then 53.** Not a parser problem: the five listing
pages are ~1 MB of HTML each and the spider fetched them back to back with no
delay, which tripped the site's LiteSpeed rate limiter (`response_status_count
/429: 4`). The same five pages returned 200 from an ordinary connection minutes
later. It now runs at one request every 3s with AutoThrottle and stops at the
page count the banner states, instead of guessing from an empty response.

**Elitehubs — 24 of 50.** `usf_take` is how many tiles the collection renders
in one response. At 28 the spider saw 21-26 of the 50 in-stock processors, and
asking for a second page earned a 307 followed by four 429s
(`response_status_count/429: 4`).

Raising it to 100 did not help: that appears to exceed the filter app's maximum
and it falls back to its own default page of 24. Worse, the app rewrites the
address bar with `history.replaceState` after load and drops `usf_take`, so the
spider's own `response.url` no longer contained the value it had asked for and
the crawl stopped after one page with `Could not parse usf_take ... Stopping`.
It now carries the value through `cb_kwargs` instead of reading it back out of
a URL the page mutates.

**The `usf_take` theory turned out to be wrong.** Asking for 56 produced 22
tiles, and 28 produced 21-26 and 100 produced 24: the number barely moves, so
the parameter is not sizing the response at all. The likely mechanism is
client-side: this is a filter app that paginates in the browser, and only the
tiles in view are rendered, so a headless 1280x720 Chromium materialises about
two dozen cards and stops. That matters because the hardcoded log line "the
in-stock collection holds 50" came from a manual browser check, and the run
cannot currently see the difference between "the store has 22" and "the page
only painted 22". This one is open, and it needs a measurement rather than
another guess.

**Vishal Peripherals — 10 of 46.** The spider was reading

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
`/wp-json/wc/store/v1/products/categories?slug=processor` (`count: 67`).

The 2026-11-19 run answered that: the JSON route is blocked too, with the same
immediate 403 (`GET /wp-json/wc/store/v1/products?category=113&per_page=100 →
403`). So this is not a Cloudflare HTML challenge that a browser could solve —
it is the IP, on every route. The same spider returns all 67 rows from a home
connection. It stays in the repo and keeps logging its 403 every run, but it is
out of `EXPECTED_VENDORS` until it can be given a proxy, which is the only thing
that changes this.

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
with `cf.errors.css` and `cf-no-screenshot-error.png` in the response. That is
Cloudflare refusing the runner's IP before any document exists, the same block
as PC Studio, and no browser can solve it. The spider stays as it is so that a
proxy is the only thing needed to bring the vendor back.

**Shweta Computers — re-added, via Shopify JSON.** The old spider pinned
`filter.v.price.lte=69699` into its URL, so every processor above ₹69,699 was
invisible to it, and it guessed between five card selectors. It now reads
`/collections/processor/products.json`, which returns title, handle, and
variants with price and an `available` flag — no theme selectors at all. The
site rate-limits hard (`429`, body `local_rate_limited`), so whether the runner
gets through is only knowable from a run; the spider logs the status and
payload head instead of raising.

It got through at 15:25 (81 rows) and was refused at 15:46: four attempts, six
seconds apart, then `Gave up retrying`. The window in that header is
`Retry-After: 60`, so all four attempts fell inside one window. Scrapy's retry
is not `Retry-After` aware and AutoThrottle paces by latency rather than by
status, so the retry count was never the problem — the spacing was. It now
runs with AutoThrottle off, a fixed 20 s delay and six attempts, which spans
about two minutes and outlasts the window.

That the two runs were twenty minutes apart matters, but only secondarily: one
request per run is nowhere near a per-IP budget, so the trigger is that GitHub
runners share egress IPs. It is the one vendor whose reliability we do not
control.

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
  nine vendors the runner must always produce. PC Studio is excluded while its
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
