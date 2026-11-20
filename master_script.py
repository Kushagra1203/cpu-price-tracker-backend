import concurrent.futures
import json
import logging
import os
import subprocess
import sys

# mysql-connector-python 9.4 references ssl.PROTOCOL_TLSv1 at import time.
# Python 3.15 removed those constants, which would kill this script on any
# machine running it -- the local nightly run does, the pinned runner (3.12)
# does not. The constants only matter for long-dead TLS versions, so aliasing
# them to the modern default is safe, and this is a no-op on the runner.
import ssl as _ssl

for _name in ("PROTOCOL_TLSv1", "PROTOCOL_TLSv1_1", "PROTOCOL_TLSv1_2"):
    if not hasattr(_ssl, _name):
        setattr(_ssl, _name, _ssl.PROTOCOL_TLS_CLIENT)

import mysql.connector
from dotenv import load_dotenv

from cpu_price_tracker.validation import (
    EXPECTED_VENDORS,
    check_vendor_counts,
    vendor_counts,
)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables from .env
load_dotenv()

# Base directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = BASE_DIR
DATA_DIR = os.path.join(PROJECT_ROOT, "cpu_price_tracker", "data")
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
NORMALIZER = os.path.join(PROJECT_ROOT, "cpu_price_tracker", "normalize_cpu_names.py")
STANDARDIZED_JSON = os.path.join(DATA_DIR, "processors_standardized.json")

# How many spiders may run at once.
#
# Each spider is already its own `scrapy crawl` subprocess, so the GIL is not
# involved -- the old loop was serial because of a 30-45 s sleep between
# spiders, not because of Python. Measured on the 2026-11-19 run: the ten
# spiders spent 92 s actually crawling inside a 433 s wall clock, so 341 s
# (79%) was that sleep.
#
# Three, not ten: the runner has 2 vCPU / 7 GB and up to three of these launch
# a Chromium, so three browsers is the practical ceiling before Playwright
# starts timing out under CPU starvation. It also keeps the three Shopify
# shops (Elitehubs, Vishal, Shweta) from all firing at once.
MAX_PARALLEL_SPIDERS = 3

# How much of a failed spider's own log to echo into the run log. Only the
# interesting lines are picked, because DEBUG lines are most of a Scrapy log
# and never contain the reason.
LOG_TAIL_LINES = 40

# MySQL connection details from environment variables
DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
DB_SSL_CA = os.getenv("DB_SSL_CA")

# Step 1: Run spiders
spider_to_json = [
    ("elitehubs", "processors_elite.json"),
    ("theitdepot", "processors_itdepot.json"),
    ("mdcomputers", "processors_md.json"),
    ("pcstudio", "processors_pc.json"),
    ("vedantcomputers", "processors_vedant.json"),
    ("vishalperipherals", "processors_vishal.json"),
    ("ezpzsolutions", "processors_ezpz.json"),
    ("computechstore", "processors_computech.json"),
    ("sclgaming", "processors_scl.json"),
    ("shwetacomputers", "processors_shweta.json"),
]


def log_tail(log_path, limit=LOG_TAIL_LINES):
    """The last few informative lines of one spider's log file."""
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return []

    interesting = [line.rstrip("\n") for line in lines if " DEBUG: " not in line]
    return interesting[-limit:]


def run_spider(spider, json_file):
    """Run one spider in its own subprocess and report what it produced.

    Each spider writes its own log so that three interleaved crawls stay
    readable; on failure the interesting tail is echoed into the run log.
    """
    output_path = os.path.join(DATA_DIR, json_file)
    log_path = os.path.join(LOG_DIR, f"{spider}.log")

    # -O truncates the feed, but only once Scrapy starts. If the process dies
    # before that (bad spider name, import error) a stale file from an earlier
    # run would otherwise be silently merged as if it were today's data.
    if os.path.exists(output_path):
        os.remove(output_path)

    command = [
        sys.executable,
        "-m",
        "scrapy",
        "crawl",
        spider,
        "-O",
        output_path,
    ]

    try:
        with open(log_path, "w", encoding="utf-8") as log_file:
            returncode = subprocess.run(
                command,
                cwd=PROJECT_ROOT,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                check=False,
            ).returncode
    except OSError as err:
        returncode = -1
        with open(log_path, "a", encoding="utf-8") as log_file:
            log_file.write(f"Could not start Scrapy: {err}\n")

    # Report how many items the spider actually produced. A spider that exits
    # cleanly with an empty file is the failure mode the vendor check exists
    # for; naming the count here points straight at the spider log.
    items = 0
    if os.path.exists(output_path):
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                scraped = json.load(f)
            if isinstance(scraped, list):
                items = len(scraped)
        except (json.JSONDecodeError, OSError) as err:
            logger.error("Could not read %s: %s", json_file, err)

    return {
        "spider": spider,
        "items": items,
        "returncode": returncode,
        "log_path": log_path,
    }


def report(result):
    """Print one finished spider, with its log tail if it produced nothing."""
    spider = result["spider"]

    if result["returncode"] != 0:
        logger.warning(
            "%s: exited %s after %d items",
            spider,
            result["returncode"],
            result["items"],
        )

    if result["items"]:
        logger.info("%s: %d items", spider, result["items"])
        return

    logger.warning("%s: 0 items - see %s", spider, result["log_path"])
    for line in log_tail(result["log_path"]):
        logger.warning("  | %s", line)


os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

logger.info(
    "Running %d spiders, %d at a time",
    len(spider_to_json),
    MAX_PARALLEL_SPIDERS,
)

results = {}
with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_PARALLEL_SPIDERS) as pool:
    futures = {
        pool.submit(run_spider, spider, json_file): spider
        for spider, json_file in spider_to_json
    }
    for future in concurrent.futures.as_completed(futures):
        # A spider failing to run is data, not an exception: the vendor check
        # below is what turns it into a red run.
        result = future.result()
        results[result["spider"]] = result
        report(result)

for spider, _ in spider_to_json:
    if spider not in results:
        logger.error("%s: never ran", spider)

logger.info(
    "Spider totals (raw items): "
    + ", ".join(
        f"{spider}={results[spider]['items']}" if spider in results else f"{spider}=?"
        for spider, _ in sorted(spider_to_json)
    )
)

# Step 2: Merge JSONs and remove duplicates by link
merged = []
seen_links = set()
for _, json_file in spider_to_json:
    in_path = os.path.join(DATA_DIR, json_file)
    if os.path.exists(in_path):
        with open(in_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    link = item.get("link")
                    if link and link not in seen_links:
                        seen_links.add(link)
                        merged.append(item)
raw_json_path = os.path.join(DATA_DIR, "processors.json")
with open(raw_json_path, "w", encoding="utf-8") as f:
    json.dump(merged, f, indent=2)
logger.info(f"Merged raw data saved to {raw_json_path}")

# Step 3: Normalize CPU names
logger.info("Running CPU name normalization...")
subprocess.run(
    [sys.executable, NORMALIZER],
    check=True,
    cwd=PROJECT_ROOT,
)
logger.info("Normalization completed!")

# Step 4: Insert into MySQL (Aiven)
logger.info("Inserting standardized data into MySQL...")
current_counts = {}
previous_counts = {}
try:
    with mysql.connector.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME,
        ssl_ca=DB_SSL_CA
    ) as conn:
        with conn.cursor() as curr:
            # Ensure table exists with extended columns
            curr.execute("""
            CREATE TABLE IF NOT EXISTS cpu_prices (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255),
                link VARCHAR(500),
                price INT,
                vendor VARCHAR(255),
                brand VARCHAR(50),
                generation VARCHAR(50),
                series VARCHAR(50),
                cores INT,
                threads INT,
                base_clock_ghz FLOAT,
                tdp_watt INT,
                UNIQUE KEY unique_vendor_link (vendor, link)
            )
            """)
            conn.commit()

            # Append-only history table for price trends (real + synthetic rows)
            curr.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255),
                vendor VARCHAR(255),
                link VARCHAR(500),
                price INT,
                snapshot_date DATE NOT NULL,
                is_synthetic TINYINT(1) NOT NULL DEFAULT 0,
                UNIQUE KEY uniq_vendor_link_date (vendor, link, snapshot_date)
            )
            """)
            conn.commit()

            # Load standardized JSON
            with open(STANDARDIZED_JSON, "r", encoding="utf-8") as f:
                standardized_data = json.load(f)

            # Row counts for this run, checked against the last run below.
            current_counts = vendor_counts(standardized_data)

            # How many rows each vendor produced on the previous real snapshot.
            # A vendor that used to return 60 rows and now returns 0 is broken,
            # not resting.
            previous_counts = {}
            try:
                curr.execute("""
                    SELECT vendor, COUNT(*) FROM price_history
                    WHERE is_synthetic = 0 AND snapshot_date = (
                        SELECT MAX(snapshot_date) FROM price_history
                        WHERE is_synthetic = 0 AND snapshot_date < CURDATE()
                    )
                    GROUP BY vendor
                """)
                previous_counts = dict(curr.fetchall())
            except mysql.connector.Error as err:
                logger.warning(f"Could not read previous run counts: {err}")

            # Prepare data for batch insert
            insert_data = []
            history_data = []
            for item in standardized_data:
                price = item.get("price")

                # Skip if price is missing or 0
                if price is None or str(price).strip() == "" or int(price) == 0:
                    continue

                insert_data.append((
                    item.get("standard_name"),
                    item.get("link"),
                    int(price),
                    item.get("vendor"),
                    item.get("brand"),
                    item.get("generation"),
                    item.get("series"),
                    int(item.get("cores")) if item.get("cores") else None,
                    int(item.get("threads")) if item.get("threads") else None,
                    float(item.get("base_clock_ghz")) if item.get("base_clock_ghz") else None,
                    int(item.get("tdp_watt")) if item.get("tdp_watt") else None
                ))
                # (name, vendor, link, price) -> appended to price_history every run
                history_data.append((
                    item.get("standard_name"),
                    item.get("vendor"),
                    item.get("link"),
                    int(price),
                ))

            if insert_data:
                try:
                    curr.executemany("""
                        INSERT INTO cpu_prices
                        (name, link, price, vendor, brand, generation, series, cores, threads, base_clock_ghz, tdp_watt)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            name = VALUES(name),
                            price = VALUES(price),
                            brand = VALUES(brand),
                            generation = VALUES(generation),
                            series = VALUES(series),
                            cores = VALUES(cores),
                            threads = VALUES(threads),
                            base_clock_ghz = VALUES(base_clock_ghz),
                            tdp_watt = VALUES(tdp_watt)
                    """, insert_data)
                except mysql.connector.Error as err:
                    logger.error(f"Error during batch insert: {err}")
                    conn.rollback()

            # Record today's snapshot in history (idempotent per day via unique key)
            if history_data:
                try:
                    curr.executemany("""
                        INSERT IGNORE INTO price_history
                        (name, vendor, link, price, snapshot_date, is_synthetic)
                        VALUES (%s, %s, %s, %s, CURDATE(), 0)
                    """, history_data)
                    logger.info(f"Price history snapshot recorded ({len(history_data)} rows).")
                except mysql.connector.Error as err:
                    logger.error(f"Error during price_history insert: {err}")
                    conn.rollback()

            conn.commit()
    logger.info("Data inserted successfully into MySQL!")
except mysql.connector.Error as err:
    logger.error(f"Database connection error: {err}")


# Step 5: verify every vendor actually produced data
# A 200 OK with zero products is the failure mode this exists for.
if current_counts:
    logger.info(
        "Vendor rows: "
        + ", ".join(f"{v}={n}" for v, n in sorted(current_counts.items()))
    )
else:
    logger.warning("No rows were collected from any vendor.")

problems = check_vendor_counts(current_counts, previous_counts, EXPECTED_VENDORS)
for problem in problems:
    logger.error("VENDOR CHECK FAILED: %s", problem)

if problems:
    # Exit non-zero so the GitHub Actions run goes red and emails, rather than
    # completing "successfully" with a vendor silently missing.
    logger.error("%d vendor check(s) failed; today's snapshot is incomplete.", len(problems))
    sys.exit(1)

logger.info("All vendor checks passed.")
