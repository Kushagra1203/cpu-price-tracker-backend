import json
import urllib.parse

import scrapy

from cpu_price_tracker.items import CpuPriceTrackerItem

SEARCH_API = "https://svc-3-usf.hotyon.com/search"
COLLECTION = "278532915293"
TAKE = 100


class ElitehubsSpider(scrapy.Spider):
    name = "elitehubs"
    allowed_domains = ["elitehubs.com", "svc-3-usf.hotyon.com"]

    def start_requests(self):
        params = {
            "q": "",
            "apiKey": "74aa3569-3ebf-4ffc-8bc3-37c9b11941b9",
            "country": "IN",
            "locale": "en",
            "getProductDescription": "0",
            "collection": COLLECTION,
            "facetFilters": json.dumps({"1566433867": ["stockStatus", ["1"]]}),
            "skip": "0",
            "take": str(TAKE),
        }
        yield scrapy.Request(
            SEARCH_API + "?" + urllib.parse.urlencode(params),
            callback=self.parse,
            headers={"Accept": "application/json"},
        )

    def parse(self, response):
        if response.status != 200:
            self.logger.error("Elitehubs: the search API answered HTTP %d", response.status)
            return

        data = json.loads(response.text)["data"]
        items = data["items"]

        yielded = 0
        for entry in items:
            in_stock = [v for v in entry["variants"] if v.get("available")]
            if not in_stock:
                continue

            item = CpuPriceTrackerItem()
            item["name"] = entry["title"].strip()
            item["link"] = "https://elitehubs.com/products/" + entry["urlName"]
            item["price"] = min(v["price"] for v in in_stock)
            item["vendor"] = "Elitehubs"
            yielded += 1
            yield item

        self.logger.info(
            "Elitehubs: %d items, the site says it has %d in stock", yielded, data["total"]
        )
        if yielded != data["total"]:
            self.logger.error(
                "Elitehubs: captured %d of the %d the site advertises", yielded, data["total"]
            )
