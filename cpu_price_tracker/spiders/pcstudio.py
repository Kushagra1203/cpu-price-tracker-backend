import json

import scrapy

from cpu_price_tracker.items import CpuPriceTrackerItem

STORE_API = "https://www.pcstudio.in/wp-json/wc/store/v1/products?category=113&per_page=100"


class PcstudioSpider(scrapy.Spider):
    name = "pcstudio"
    allowed_domains = ["www.pcstudio.in"]

    custom_settings = {
        "DOWNLOAD_DELAY": 3,
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
            self.logger.error(
                "PC Studio: expected JSON, got HTTP %s: %r", response.status, response.text[:160]
            )
            return

        if not isinstance(products, list):
            self.logger.error("PC Studio: unexpected payload type %s", type(products).__name__)
            return

        yielded = 0
        for product in products:
            if not product.get("is_in_stock"):
                continue

            name = (product.get("name") or "").strip()
            link = product.get("permalink")
            if not name or not link:
                continue

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
            "PC Studio: %d products, %d in stock, %d yielded", len(products),
            sum(1 for p in products if p.get("is_in_stock")), yielded,
        )
