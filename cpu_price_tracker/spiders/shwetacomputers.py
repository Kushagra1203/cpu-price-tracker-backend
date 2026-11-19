"""Shweta Computers -- read from Shopify's collection JSON, not the theme.

The storefront is Shopify (its listing URLs carry Shopify's own filter
parameters, ``filter.v.availability`` / ``filter.v.price.gte``), so the
collection is also published as JSON:

    /collections/processor/products.json?limit=250&page=N

Each product there carries a title, a handle, and variants with a price and an
``available`` flag. That flag is the same stock field the product page renders,
so nothing depends on the availability query parameter -- which products.json
ignores anyway.

This replaces two failures in the previous spider:

* it guessed between five different card selectors, which is how a theme change
  silently produces zero rows;
* it pinned ``filter.v.price.lte=69699`` into its URL. That is Rs 69,699, so
  every processor above that price was invisible to it -- which is most of the
  high-end catalogue.

The site rate-limits aggressively (HTTP 429, body ``local_rate_limited``,
``retry-after: 60``), on the JSON route as well as the HTML. That is a per-IP
block, so whether it applies to the GitHub runner is only knowable from a run;
this spider logs the status and payload head instead of raising, so the answer
shows up in the log rather than as a crash.
"""

import json

import scrapy

from cpu_price_tracker.items import CpuPriceTrackerItem

API_URL = (
    "https://shwetacomputers.com/collections/processor/products.json"
    "?limit=250&page={page}"
)

MAX_PAGES = 5


class ShwetacomputersSpider(scrapy.Spider):
    name = "shwetacomputers"
    allowed_domains = ["shwetacomputers.com"]

    custom_settings = {
        "DOWNLOAD_DELAY": 3,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "USER_AGENT": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.collected = 0

    def start_requests(self):
        yield self.page_request(1)

    def page_request(self, page):
        return scrapy.Request(
            API_URL.format(page=page),
            callback=self.parse,
            cb_kwargs={"page": page},
            headers={"Accept": "application/json"},
        )

    def parse(self, response, page):
        try:
            payload = json.loads(response.text)
        except ValueError:
            self.logger.error(
                "Shweta: expected JSON, got HTTP %s (%d bytes): %r",
                response.status,
                len(response.body),
                response.text[:160],
            )
            return

        products = payload.get("products") if isinstance(payload, dict) else None
        if not isinstance(products, list):
            self.logger.error("Shweta: unexpected payload shape: %r", str(payload)[:160])
            return

        if not products:
            self.logger.info("Shweta: page %d is empty, stopping", page)
            return

        available = 0
        yielded = 0

        for product in products:
            name = (product.get("title") or "").strip()
            handle = product.get("handle")
            if not name or not handle:
                continue

            # A CPU normally has one variant, but compare only the buyable ones
            # so a sold-out variant can never contribute a price.
            prices = []
            for variant in product.get("variants") or []:
                if not variant.get("available"):
                    continue
                raw = variant.get("price")
                try:
                    prices.append(int(round(float(raw))))
                except (TypeError, ValueError):
                    continue
            if not prices:
                continue
            available += 1

            item = CpuPriceTrackerItem()
            item["name"] = name
            item["link"] = f"https://shwetacomputers.com/products/{handle}"
            item["price"] = min(prices)
            item["vendor"] = "Shweta Computers"

            yielded += 1
            self.collected += 1
            yield item

        self.logger.info(
            "Shweta page %d: %d products, %d available, %d items (collected %d)",
            page,
            len(products),
            available,
            yielded,
            self.collected,
        )

        if len(products) >= 250 and page < MAX_PAGES:
            yield self.page_request(page + 1)
