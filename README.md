# CPU Price Tracker — Backend

This repository contains the backend for the CPU Price Tracker service. It is responsible for collecting CPU pricing data from multiple Indian retailers, normalizing and persisting historical price snapshots, and exposing a web API for the frontend and other consumers.

This README documents the project's purpose, architecture, features, project structure, configuration examples, and operational notes.

## Live frontend
- The frontend for this service is available at: https://v0-cpu-price-tracker.vercel.app/

## High-level overview
- Scrapers: A set of modular scraper modules (or Scrapy spiders) fetch product listings and current prices from supported retailers.
- Normalization: Raw scraped data is mapped to canonical product identifiers and a consistent schema to make cross-store comparisons meaningful.
- Persistence: Time-stamped price snapshots are stored in a database to enable historical queries and trend analysis.
- API: A web API (e.g., FastAPI) serves current prices, historical series, and aggregated statistics to the frontend.
- Orchestration: A single master script coordinates scraping, normalization, and persistence. Running `master_script.py` performs an end-to-end run.

## Features
- Multi-store scraping and consolidation
- Robust normalization to map retailer names/SKUs to canonical product entries
- Time-series storage of price snapshots for historical analysis
- REST API endpoints for current prices, history, and aggregates
- Extensible scraper interface to add new retailers with minimal changes
- Operational considerations: rate limiting, retries, monitoring, alerting

## Project structure (typical)

````
.
├─ cpu_price_tracker/            # Python package (app & scrapers)
│  ├─ spiders/                   # Scraper modules or Scrapy spiders
│  ├─ normalization/             # Name matching, canonicalization logic
│  ├─ db/                        # Database models and persistence code
│  ├─ api/                       # FastAPI app, routes, serializers
│  ├─ workers/                   # Background tasks, schedulers, Celery configs (optional)
│  └─ master_script.py           # Orchestration entrypoint
├─ scripts/                      # Helper scripts (migrations, exports, diagnostics)
├─ tests/                        # Unit and integration tests
├─ requirements.txt or pyproject.toml
└─ README.md
````

Note: Actual layout may vary; adapt paths above to the repository's existing layout.

## Example configuration (environment variables)

The project typically uses environment variables to configure DB connections, API secrets, and scraping options. Example `.env` values:

```
DB_HOST=127.0.0.1
DB_PORT=5432
DB_USER=cpu_user
DB_PASSWORD=supersecret
DB_NAME=cpu_price_tracker
API_HOST=0.0.0.0
API_PORT=8000
SCRAPE_TIMEOUT=30
```

## Example database schema (minimal)

This is a simple example—your project may use a different schema or ORM migrations.

````sql
-- canonical products
CREATE TABLE products (
  id BIGSERIAL PRIMARY KEY,
  canonical_name TEXT NOT NULL,
  manufacturer TEXT,
  model TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- price snapshots
CREATE TABLE price_snapshots (
  id BIGSERIAL PRIMARY KEY,
  product_id BIGINT REFERENCES products(id) ON DELETE CASCADE,
  store TEXT NOT NULL,
  store_sku TEXT,
  url TEXT,
  currency TEXT DEFAULT 'INR',
  price NUMERIC(12,2) NOT NULL,
  scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
````

## How to run (overview)

- The repository's `master_script.py` orchestrates scraping, normalization, and database upserts. To perform an end-to-end run, execute:

  python3 master_script.py

- The web API (if present) is typically exposed by a framework like FastAPI and run with Uvicorn or similar. The frontend consumes this API to display listings and charts.

## Scheduler / background jobs
- If the project uses a scheduler (CRON, APScheduler) or worker system (Celery, RQ), ensure scheduler workers are started in the deployment environment to keep data fresh.
- The master orchestration script may also be run periodically via a system scheduler or CI cron job.

## Testing
- Unit tests for scrapers, normalization logic, and DB operations should live in `tests/` and be runnable with `pytest`.
- Integration tests can validate end-to-end scraping and DB writes (use fixtures or a test DB).

## Observability & operations
- Monitor scraper success/failure and set up alerting for persistent failures.
- Track database growth and retention policies for historical snapshots.
- Implement rate-limiting and respectful crawling (respect robots.txt and polite request rates).

## Contributing
- Follow the repository's code style and add tests for new scrapers and normalization rules.
- When adding a new scraper: implement a fetch -> extract -> normalize -> persist flow and include tests and documentation.

## Links & contact
- Frontend (live): https://v0-cpu-price-tracker.vercel.app/
- Frontend repo: https://github.com/Kushagra1203/CPU-Price-Tracker
- Issues & support: open issues in this repository for backend-specific problems.

---

This README focuses on documenting the backend's responsibilities, structure, and operational guidance. If you want, I can also:
- Add concrete example code snippets for scrapers or DB interactions.
- Create a PR instead of committing directly.
