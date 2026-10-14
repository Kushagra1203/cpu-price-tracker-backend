"""
pcpt_reference_scraper.py — ONE-TIME reference scraper for pcpricetracker.in

Flow:
  1. (If no valid session) headful browser for a few seconds -> cf_clearance cookie
  2. Headless curl_cffi (chrome TLS impersonation):
     a. scrape /processor listing -> {hash: name}
     b. fuzzy-match our cpu_data.csv dictionary -> per-CPU product hashes
     c. GET /api/chart/{hash} for each match (1 rps politeness, disk-cached)
  3. Output: /tmp/opencode/pcpt/reference_prices.json  (aggregate per-day anchor series)

Everything is cached; re-running skips already-fetched items.
"""
import json
import os
import re
import sys
import time

from curl_cffi import requests as cffi_requests
from rapidfuzz import fuzz

OUT = "/tmp/opencode/pcpt"
REF_DIR = f"{OUT}/reference"
os.makedirs(REF_DIR, exist_ok=True)

PROJECT = "/home/kushagra/dev/cpu_price_tracker"
CPU_CSV = f"{PROJECT}/cpu_price_tracker/data/cpu_data.csv"

BASE = "https://pcpricetracker.in"
HASH_RE = re.compile(r"/products/([0-9a-f]{32})")
DATE_RE = re.compile(r"^\d{2}-\d{2}-\d{4}$")


# ---------------------------------------------------------------- session
def get_session(force=False):
    """Return (ua, cf_clearance); refresh via headful browser if needed."""
    sf = f"{OUT}/session.json"
    if not force and os.path.exists(sf):
        s = json.load(open(sf))
        return s["ua"], s["cf_clearance"]

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False,
                                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        page = ctx.new_page()
        page.goto(f"{BASE}/processor", timeout=90000, wait_until="domcontentloaded")
        for _ in range(60):
            try:
                if "just a moment" not in page.title().lower():
                    break
            except Exception:
                pass
            time.sleep(1)
        ua = page.evaluate("navigator.userAgent")
        cookies = ctx.cookies(BASE)
        browser.close()
    clearance = next((c["value"] for c in cookies if c["name"] == "cf_clearance"), None)
    if not clearance:
        sys.exit("Could not obtain cf_clearance")
    json.dump({"ua": ua, "cf_clearance": clearance}, open(sf, "w"), indent=2)
    return ua, clearance


class Client:
    def __init__(self):
        self.ua, self.clear = get_session()
        self.headers = {"User-Agent": self.ua, "Cookie": f"cf_clearance={self.clear}",
                        "Accept": "text/html,application/json,*/*",
                        "Referer": f"{BASE}/processor"}

    def get(self, url, as_json=False):
        for attempt in (1, 2):
            r = cffi_requests.get(url, impersonate="chrome", headers=self.headers, timeout=30)
            time.sleep(1.0)  # politeness: ~1 rps, one-time job
            if r.status_code == 200:
                return r.json() if as_json else r.text
            if r.status_code == 403:  # clearance expired -> refresh once
                self.ua, self.clear = get_session(force=True)
                self.headers["User-Agent"] = self.ua
                self.headers["Cookie"] = f"cf_clearance={self.clear}"
                continue
            print(f"  ! {r.status_code} on {url}")
            return None
        return None


# ---------------------------------------------------------------- catalog
def scrape_catalog(client):
    cat_file = f"{OUT}/catalog.json"
    if os.path.exists(cat_file):
        return json.load(open(cat_file))
    html = client.get(f"{BASE}/processor")
    # product links with their anchor text (name lives in the <a> content)
    pairs = re.findall(
        r'<a[^>]+href="/products/([0-9a-f]{32})"[^>]*>(.*?)</a>', html, re.S)
    catalog = {}
    for h, raw in pairs:
        name = re.sub(r"<[^>]+>", " ", raw)
        name = re.sub(r"\s+", " ", name).strip()
        name = name.replace("Â®", "®").replace("Â", "")  # fix mojibake
        if h not in catalog or len(name) > len(catalog[h]):
            catalog[h] = name
    json.dump(catalog, open(cat_file, "w"), indent=2)
    return catalog


# ---------------------------------------------------------------- matching
def our_cpus():
    import csv
    cpus = []
    with open(CPU_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cpus.append(row["name"].strip())
    return cpus


def model_token(name):
    """'AMD Ryzen 5 7500F' -> '7500F'; 'Intel Core i5 12400F' -> '12400F';
    'Intel Core Ultra 5 250K Plus' -> '250K Plus'"""
    n = name.lower()
    m = re.search(r"(?:ultra\s+)?([3579])\s+(\d{4,5}\s?(?:x3d2?|kf?|x3d)?(?:\s+plus)?)", n)
    if m:
        return f"{m.group(1)} {m.group(2)}".replace("  ", " ") if "ultra" in n else m.group(2)
    m = re.search(r"(i[3579])[-\s]?(\d{4,5}\s?(?:kf|f|k|t)?)", n)
    if m:
        return f"{m.group(2)}"
    m = re.search(r"(\d{4}g3?|(\d{4}x3d?)|(\d{4}f))", n)
    return m.group(1) if m else None


SUFFIX_RE = re.compile(r"(x3d2|x3d|xt|ks|kf|plus|pro|[a-z])", re.I)


def sku_key(name):
    """-> (model_digits, suffix_set) e.g. 'Ryzen 7 5800X' -> ('5800', {'x'}),
    'i5-12400F' -> ('12400', {'f'}), '7800X3D' -> ('7800', {'x3d'}).
    The FIRST 3-5 digit run is the model number in these product names."""
    n = name.lower().replace("Â®", "®")
    m = re.search(r"(?<!\d)(\d{3,5})((?:[a-z0-9]{1,4})?)", n)
    if not m:
        return None
    digits = m.group(1)
    tail = (m.group(2) or "").lower()
    suffixes = set(SUFFIX_RE.findall(tail)) - {"plus", "pro"}  # handled as words
    if re.search(rf"{digits}\s*[a-z0-9]*\s+plus\b", n):
        suffixes.add("plus")
    return digits, frozenset(suffixes)


def sig_tokens(name):
    n = name.lower()
    return {t for t in ("x3d2", "x3d", "plus", "pro", "xt") if t in n}


def match_catalog(cpus, catalog):
    """Return {our_name: [hashes]}.
    Tier 1: SKU-key equality (digits + suffix set + 'pro' word agreement).
    Tier 2: fuzzy one-to-one fallback."""
    entries = []
    for h, n in catalog.items():
        nl = n.lower()
        entries.append((h, n, nl, sku_key(n)))

    matches = {}
    used = set()
    unmatched = []

    for cpu in cpus:
        our_key = sku_key(cpu)
        our_pro = " pro " in f" {cpu.lower()} "
        cands = []
        if our_key:
            d, sufs = our_key
            for h, n, nl, key in entries:
                if key and key[0] == d and key[1] == sufs:
                    if our_pro != (" pro " in f" {nl} "):
                        continue
                    cands.append(h)
        if cands:
            matches[cpu] = cands[:3]
            continue

        # fuzzy fallback (one-to-one)
        best, best_score = None, 0
        for h, n, nl, key in entries:
            if h in used:
                continue
            s = fuzz.token_set_ratio(cpu.lower(), nl)
            if s > best_score:
                best, best_score = h, s
        if best and best_score >= 85:
            matches[cpu] = [best]
            used.add(best)
        else:
            unmatched.append(cpu)

    return matches, unmatched


# ---------------------------------------------------------------- charts
def fetch_charts(client, matches):
    out = {}
    hashes = sorted({h for hs in matches.values() for h in hs})
    for i, h in enumerate(hashes):
        cache = f"{REF_DIR}/{h}.json"
        if os.path.exists(cache):
            out[h] = json.load(open(cache))
            continue
        data = client.get(f"{BASE}/api/chart/{h}", as_json=True)
        if data and isinstance(data, list) and len(data) >= 2:
            json.dump(data, open(cache, "w"))
            out[h] = data
            print(f"  chart {i + 1}/{len(hashes)} {h}: {len(data[0])} days")
        else:
            print(f"  chart {i + 1}/{len(hashes)} {h}: FAILED/EMPTY")
    return out


def build_anchor_series(matches, charts):
    """{cpu: {date: median_price_across_their_vendors}} with min/max."""
    import statistics
    result = {}
    for cpu, hs in matches.items():
        by_date = {}
        for h in hs:
            data = charts.get(h)
            if not data:
                continue
            dates, *series = data
            for di, d in enumerate(dates):
                vals = [s[di] for s in series if di < len(s) and isinstance(s[di], (int, float)) and s[di] > 0]
                if vals:
                    by_date.setdefault(d, []).extend(vals)
        if not by_date:
            continue
        anchor = {}
        for d, vals in by_date.items():
            anchor[d] = {"median": round(statistics.median(vals)),
                         "min": min(vals), "max": max(vals), "n": len(vals)}
        result[cpu] = dict(sorted(anchor.items(), key=lambda kv: __import__("datetime").datetime.strptime(kv[0], "%d-%m-%Y")))
    return result


def main():
    client = Client()
    catalog = scrape_catalog(client)
    print(f"catalog: {len(catalog)} processor products")

    cpus = our_cpus()
    print(f"our dictionary: {len(cpus)} CPUs")

    matches, unmatched = match_catalog(cpus, catalog)
    print(f"matched: {len(matches)} | unmatched: {len(unmatched)}")
    for u in unmatched:
        print("   unmatched:", u)
    json.dump({"matches": matches, "unmatched": unmatched},
              open(f"{OUT}/match_report.json", "w"), indent=2)

    charts = fetch_charts(client, matches)
    anchors = build_anchor_series(matches, charts)
    json.dump(anchors, open(f"{OUT}/reference_prices.json", "w"), indent=2)
    print(f"\nanchor series for {len(anchors)} CPUs -> {OUT}/reference_prices.json")
    for cpu, a in list(anchors.items())[:3]:
        first = next(iter(a.items()))
        last = list(a.items())[-1]
        print(f"  {cpu[:40]:40} {first[0]}: {first[1]['median']}  ->  {last[0]}: {last[1]['median']}")


if __name__ == "__main__":
    main()
