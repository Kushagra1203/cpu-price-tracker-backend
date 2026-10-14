"""
generate_synthetic.py — Phase B2: fit synthetic per-vendor price history to
real market anchors scraped from a public tracker (see pcpt_reference_scraper.py).

Method (documented for README):
  - For CPUs with reference anchors (118): per-vendor synthetic series =
    anchor_market_median(day) x per-listing offset, where the offset scales the
    market path to pass through the listing's REAL current price at the join
    date. The pre-anchor window (back to ~6 months) is extended backwards with
    generation-aware drift. No invented sale dips inside the anchored window
    (real dips are already in the anchor data).
  - For CPUs without anchors (~55): series generated backwards from the real
    current price with generation-aware drift, stickiness, and sale-event dips.
  - All rows: is_synthetic=1, inserted with INSERT IGNORE so REAL snapshots
    (any date) always win.

Input:  /tmp/opencode/pcpt/reference_prices.json + latest processors_standardized.json
Output: rows inserted into price_history (MySQL, Aiven)
"""
import csv
import json
import os
import random
import statistics
from datetime import date, datetime, timedelta

BASE = "/home/kushagra/dev/cpu_price_tracker"
DATA_DIR = f"{BASE}/cpu_price_tracker/data"
REF = "/tmp/opencode/pcpt/reference_prices.json"
CPU_CSV = f"{DATA_DIR}/cpu_data.csv"

SEED = 42
rng = random.Random(SEED)

WINDOW_START = date(2026, 4, 5)      # ~6 months back
WINDOW_END_EXCL = date.today()       # synthetic fills up to yesterday; today = real run
ANCHOR_START = date(2026, 7, 17)     # first day of reference data

# Sale windows used ONLY where we have no real market signal
# (pre-anchor backfill + no-anchor CPUs)
SALE_WINDOWS = [
    (date(2026, 7, 13), date(2026, 7, 16)),   # Prime Day-ish
    (date(2026, 9, 28), date(2026, 10, 8)),   # festive (BBD/GIF)
]

GEN_DRIFT = {  # daily fractional drift going BACKWARD, by generation number
    "amd": {9: 0.0006, 8: 0.0010, 7: 0.0013, 6: 0.0016, 5: 0.0019, 4: 0.0022, 3: 0.0025, 2: 0.0028, 1: 0.0030},
    "intel": {14: 0.0008, 13: 0.0011, 12: 0.0014, 11: 0.0017, 10: 0.0020, 9: 0.0023, 8: 0.0026, 7: 0.0029},
}


def gen_drift(generation, name):
    n = (name or "").lower()
    if "x3d" in n:
        return 0.0004  # halo chips hold value
    g = (generation or "").lower()
    for brand, table in GEN_DRIFT.items():
        if brand in g:
            if "ultra" in g:
                return table[14]
            m = None
            for k in table:
                if f"{k}" in g and ("gen" in g or "generation" in g):
                    m = k if m is None else max(m, k)
            if m:
                return table.get(m, 0.0015)
    return 0.0016  # Others / unknown


def in_sale(d):
    return any(a <= d <= b for a, b in SALE_WINDOWS)


def round_price(p):
    step = 10 if p < 10000 else (50 if p < 30000 else 100)
    return max(step, int(round(p / step) * step))


def parse_ref_date(s):
    return datetime.strptime(s, "%d-%m-%Y").date()


# ------------------------------------------------------------------ inputs
def load_reference():
    raw = json.load(open(REF))
    out = {}
    for cpu, days in raw.items():
        out[cpu] = [(parse_ref_date(d), v["median"]) for d, v in days.items()]
        out[cpu].sort()
    return out


def load_listings():
    """[(standard_name, vendor, link, real_price, generation)] with valid price."""
    items = json.load(open(f"{DATA_DIR}/processors_standardized.json"))
    out = []
    for it in items:
        p = it.get("price")
        if p in (None, 0, ""):
            continue
        out.append({
            "name": it.get("standard_name"),
            "vendor": it.get("vendor"),
            "link": it.get("link"),
            "price": int(p),
            "gen": it.get("generation"),
        })
    return out


def anchor_at(series, d, max_back=5):
    """nearest anchor value at or before date d (within max_back days)."""
    best = None
    for ad, val in series:
        if ad <= d:
            best = (ad, val)
        if ad > d:
            break
    if best and (d - best[0]).days <= max_back:
        return best[1]
    return None


# ------------------------------------------------------------ series builders
def anchored_series(listing, ref, join_date):
    """Market path scaled to pass through the listing's real price at join_date."""
    a_join = anchor_at(ref, join_date) or (ref[-1][1] if ref[-1][0] <= join_date else ref[0][1])
    offset = listing["price"] / a_join
    offset = min(1.25, max(0.80, offset))
    vendor_eps = 1 + rng.uniform(-0.006, 0.006)  # per-listing persistent wiggle
    offset *= vendor_eps

    prices = {}
    d = WINDOW_START
    while d < WINDOW_END_EXCL:
        a = anchor_at(ref, d)
        if a is not None:
            prices[d] = a * offset
        d += timedelta(days=1)

    # pre-anchor extension: walk backward from earliest anchored price
    first_d = min(prices) if prices else ANCHOR_START
    base = prices.get(first_d, listing["price"])
    drift = gen_drift(listing["gen"], listing["name"])
    price = base
    d = first_d - timedelta(days=1)
    while d >= WINDOW_START:
        if d in prices:
            price = prices[d]
        else:
            if rng.random() < 0.10:
                price *= 1 + drift + rng.gauss(0, 0.002)
            else:
                price *= 1 + drift * 0.25
            if in_sale(d) and rng.random() < 0.5:
                price *= 1.04  # sale had ENDED going forward -> older price higher
            price = min(price, listing["price"] * 1.40)
            prices[d] = price
        d -= timedelta(days=1)
    return prices


def drift_series(listing):
    """Full-window backward walk from the listing's real current price."""
    drift = gen_drift(listing["gen"], listing["name"])
    p0 = listing["price"]
    sale_drop = rng.uniform(0.04, 0.09)
    is_sale_item = rng.random() < 0.65

    prices = {}
    price = float(p0)
    d = WINDOW_END_EXCL - timedelta(days=1)
    while d >= WINDOW_START:
        if in_sale(d) and is_sale_item:
            if rng.random() < 0.06:
                price *= 1 + rng.gauss(0, 0.003)
        elif rng.random() < 0.12:
            price *= 1 + drift + rng.gauss(0, 0.003)
        else:
            price *= 1 + drift * 0.25
        price = min(max(price, p0 * 0.85), p0 * 1.40)
        prices[d] = price
        d -= timedelta(days=1)
    # re-apply sale dip forward so dips actually appear in-window
    for a, b in SALE_WINDOWS:
        depth = sale_drop
        for dd in range((b - a).days + 1):
            day = a + timedelta(days=dd)
            if day in prices and is_sale_item:
                recover = dd / max(1, (b - a).days)
                prices[day] = prices[day] * (1 - depth * (1 - recover))
    return prices


# ------------------------------------------------------------------ main
def main():
    ref = load_reference()
    listings = load_listings()
    print(f"reference CPUs: {len(ref)} | listings: {len(listings)}")

    rows = []
    for i, li in enumerate(listings):
        series = None
        if li["name"] in ref:
            series = anchored_series(li, ref[li["name"]], join_date=date.today())
        else:
            series = drift_series(li)
        for d, p in series.items():
            rows.append((li["name"], li["vendor"], li["link"],
                         round_price(p), d.isoformat(), 1))
        if (i + 1) % 100 == 0:
            print(f"  {i + 1}/{len(listings)} listings processed")

    print(f"synthetic rows: {len(rows)}")

    # ---- insert ----
    from dotenv import load_dotenv
    import mysql.connector
    load_dotenv(f"{BASE}/.env")
    conn = mysql.connector.connect(
        host=os.getenv("DB_HOST"), port=int(os.getenv("DB_PORT", 3306)),
        user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"), ssl_ca=os.getenv("DB_SSL_CA"),
    )
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255), vendor VARCHAR(255), link VARCHAR(500),
            price INT, snapshot_date DATE NOT NULL,
            is_synthetic TINYINT(1) NOT NULL DEFAULT 0,
            UNIQUE KEY uniq_vendor_link_date (vendor, link, snapshot_date)
        )""")
    conn.commit()

    sql = """INSERT IGNORE INTO price_history
             (name, vendor, link, price, snapshot_date, is_synthetic)
             VALUES (%s, %s, %s, %s, %s, %s)"""
    inserted = 0
    for i in range(0, len(rows), 5000):
        chunk = rows[i:i + 5000]
        cur.executemany(sql, chunk)
        conn.commit()
        inserted += cur.rowcount
        print(f"  chunk {i // 5000 + 1}: attempted {len(chunk)}, inserted {cur.rowcount}")

    cur.execute("SELECT COUNT(*), SUM(is_synthetic) FROM price_history")
    total, syn = cur.fetchone()
    print(f"price_history now: {total} rows ({syn} synthetic)")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
