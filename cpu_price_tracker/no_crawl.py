import os
import json
import mysql.connector
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# MySQL connection details from .env
DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
DB_SSL_CA = os.getenv("DB_SSL_CA")

# Path to your already processed JSON
JSON_FILE = "/Users/kushagrasrivastava/Developer/Cpu Price Tracker/cpu_price_tracker/cpu_price_tracker/data/processors_standardized.json"

# Connect to MySQL
conn = mysql.connector.connect(
    host=DB_HOST,
    port=DB_PORT,
    user=DB_USER,
    password=DB_PASS,
    database=DB_NAME,
    ssl_ca=DB_SSL_CA
)
curr = conn.cursor()

# Create table if it doesn't exist
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
with open(JSON_FILE, "r", encoding="utf-8") as f:
    standardized_data = json.load(f)

# Insert into DB
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
