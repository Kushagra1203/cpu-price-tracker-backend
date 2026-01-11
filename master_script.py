import os
import subprocess
import json
import mysql.connector
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Base directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = BASE_DIR
DATA_DIR = os.path.join(PROJECT_ROOT, "cpu_price_tracker", "data")
NORMALIZER = os.path.join(PROJECT_ROOT, "cpu_price_tracker", "normalize_cpu_names.py")
STANDARDIZED_JSON = os.path.join(DATA_DIR, "processors_standardized.json")

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
    ("sclgaming", "processors_scl.json"),
    ("shwetacomputers", "processors_shweta.json"),
    ("vedantcomputers", "processors_vedant.json"),
    ("vishalperipherals", "processors_vishal.json"),
    ("ezpzsolutions", "processors_ezpz.json"),
]

for spider, json_file in spider_to_json:
    output_path = os.path.join(DATA_DIR, json_file)
    print(f"Running spider {spider} --> output: {output_path}")
    subprocess.run(
        ["scrapy", "crawl", spider, "-O", output_path],
        check=True,
        cwd=PROJECT_ROOT,
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
print(f"Merged raw data saved to {raw_json_path}")

# Step 3: Normalize CPU names
print("Running CPU name normalization...")
subprocess.run(
    ["python3", NORMALIZER],
    check=True,
    cwd=PROJECT_ROOT,
)
print("Normalization completed!")

# Step 4: Insert into MySQL (Aiven)
print("Inserting standardized data into MySQL...")
conn = mysql.connector.connect(
    host=DB_HOST,
    port=DB_PORT,
    user=DB_USER,
    password=DB_PASS,
    database=DB_NAME,
    ssl_ca=DB_SSL_CA
)
curr = conn.cursor()

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

# Load standardized JSON
with open(STANDARDIZED_JSON, "r", encoding="utf-8") as f:
    standardized_data = json.load(f)

for item in standardized_data:
    price = item.get("price")

    # Skip if price is missing or 0
    if price is None or str(price).strip() == "" or int(price) == 0:
        continue

    try:
        curr.execute("""
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
        """, (
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
    except mysql.connector.Error as err:
        print(f"Error inserting {item.get('link')}: {err}")
        conn.rollback()

conn.commit()
curr.close()
conn.close()
print("Data inserted successfully into MySQL!")
