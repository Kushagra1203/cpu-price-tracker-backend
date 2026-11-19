"""PC Studio, read from its WooCommerce Store API instead of its HTML.

The HTML category page is behind Cloudflare's bot management, which answers the
GitHub runner with HTTP 403 in under a second -- before any document exists, so
Playwright cannot get around it. The storefront is WooCommerce, and WooCommerce
publishes a separate public route:

    /wp-json/wc/store/v1/products?category=113&per_page=100

which returns the same catalogue as JSON, with name, permalink, prices and
is_in_stock. Category 113 is the "Processor" term (confirmed via
/wp-json/wc/store/v1/products/categories?slug=processor, which reports
count: 67).

Verified from a working network: 67 products, all in stock, all with prices.
One request returns the whole catalogue, so there is no pagination to follow.
"""

import json

import scrapy

from cpu_price_tracker.items import CpuPriceTrackerItem

STORE_API = (
    "https://www.pcstudio.in/wp-json/wc/store/v1/products"
    "?category=113&per_page=100"
)


class PcstudioSpider(scrapy.Spider):
    name = "pcstudio"
    allowed_domains = ["www.pcstudio.in"]

    custom_settings = {
        "DOWNLOAD_DELAY": 3,
        "CLOSESPIDER_PAGECOUNT": 5,
        "USER_AGENT": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
    }

    def start_requests(self):
        yield scrapy.Request(
            STORE_API,
            callback=self.parse,
            headers={"Accept": "application/json"},
        )

    def parse(self, response):
        try:
            products = json.loads(response.text)
        except ValueError:
            # A Cloudflare challenge page is HTML, so this is where an IP-level
            # block surfaces now. Say so plainly instead of raising.
            self.logger.error(
                "PC Studio: expected JSON, got HTTP %s (%d bytes): %r",
                response.status,
                len(response.body),
                response.text[:160],
            )
            return

        if not isinstance(products, list):
            self.logger.error(
                "PC Studio: unexpected payload type %s", type(products).__name__
            )
            return

        in_stock = 0
        yielded = 0

        for product in products:
            if not product.get("is_in_stock"):
                continue
            in_stock += 1

            name = (product.get("name") or "").strip()
            link = product.get("permalink")
            if not name or not link:
                continue

            # prices.price is an integer string in the store's smallest unit,
            # and currency_minor_unit says how many decimal places that is.
            # This store reports 0, so "36380" is already ₹36,380.
            price = None
            prices = product.get("prices") or {}
            raw = prices.get("price")
            if raw not in (None, ""):
                try:
                    minor_unit = int(prices.get("currency_minor_unit", 2))
                    price = int(round(int(raw) / (10 ** minor_unit)))
                except (TypeError, ValueError):
                    price = None

            item = CpuPriceTrackerItem()
            item["name"] = name
            item["link"] = link
            item["price"] = price
            item["vendor"] = "PC Studio"

            yielded += 1
            yield item

        self.logger.info(
            "PC Studio: %d products in the API, %d in stock, %d yielded",
            len(products),
            in_stock,
            yielded,
        )
