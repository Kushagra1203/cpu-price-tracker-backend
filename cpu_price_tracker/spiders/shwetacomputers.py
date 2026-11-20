import json

import scrapy

from cpu_price_tracker.items import CpuPriceTrackerItem

API_URL = "https://shwetacomputers.com/collections/processor/products.json?limit=250&page={page}"
MAX_PAGES = 5


class ShwetacomputersSpider(scrapy.Spider):
    name = "shwetacomputers"
    allowed_domains = ["shwetacomputers.com"]

    custom_settings = {
        "AUTOTHROTTLE_ENABLED": False,
        "DOWNLOAD_DELAY": 20,
        "RETRY_TIMES": 6,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "USER_AGENT": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
    }

    def start_requests(self):
        yield scrapy.Request(
            API_URL.format(page=1),
            callback=self.parse,
            cb_kwargs={"page": 1},
            headers={"Accept": "application/json"},
        )

    def parse(self, response, page):
        try:
            payload = json.loads(response.text)
        except ValueError:
            self.logger.error(
                "Shweta: expected JSON, got HTTP %s: %r", response.status, response.text[:160]
            )
            return

        products = payload.get("products") or []
        if not products:
            self.logger.info("Shweta: page %d is empty, stopping", page)
            return

        yielded = 0
        for product in products:
            name = (product.get("title") or "").strip()
            handle = product.get("handle")
            if not name or not handle:
                continue

            prices = []
            for variant in product.get("variants") or []:
                if not variant.get("available"):
                    continue
                try:
                    prices.append(int(round(float(variant.get("price")))))
                except (TypeError, ValueError):
                    continue
            if not prices:
                continue

            item = CpuPriceTrackerItem()
            item["name"] = name
            item["link"] = f"https://shwetacomputers.com/products/{handle}"
            item["price"] = min(prices)
            item["vendor"] = "Shweta Computers"
            yielded += 1
            yield item

        self.logger.info(
            "Shweta page %d: %d products, %d in stock", page, len(products), yielded
        )

        if len(products) >= 250 and page < MAX_PAGES:
            yield scrapy.Request(
                API_URL.format(page=page + 1),
                callback=self.parse,
                cb_kwargs={"page": page + 1},
                headers={"Accept": "application/json"},
            )
