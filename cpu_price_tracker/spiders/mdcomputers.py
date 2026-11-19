"""MDComputers -- 62 processors across 4 pages of 20.

The listing prints its own size ("Showing 1 to 20 of 62 (4 Pages)"), so the
spider knows the target before it starts and says how close it got. Previously
the only signal was the total row count, which cannot distinguish "sold out
today" from "the pagination silently stopped".
"""

import scrapy

from cpu_price_tracker.items import CpuPriceTrackerItem
from cpu_price_tracker.listing import parse_showing_total

PAGE_URL = "https://mdcomputers.in/catalog/processor?page={page}"

MAX_PAGES = 20


class mdcomputerSpider(scrapy.Spider):
    name = "mdcomputers"
    allowed_domains = ["mdcomputers.in"]

    custom_settings = {
        "DOWNLOAD_DELAY": 2,
        "USER_AGENT": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.expected_total = None
        self.total_pages = None
        self.collected = 0

    def start_requests(self):
        yield scrapy.Request(
            PAGE_URL.format(page=1),
            callback=self.parse,
            cb_kwargs={"page": 1},
        )

    def parse(self, response, page):
        products = response.css("div.product-wrapper")

        if not products:
            self.logger.info("MDComputers: no products on page %d, stopping", page)
            return

        if page == 1:
            self.expected_total, self.total_pages = parse_showing_total(response.text)

        yielded = 0
        for product in products:
            name = product.css("h3.product-entities-title a::text").get()
            link = product.css("h3.product-entities-title a::attr(href)").get()
            if not name or not link:
                continue

            price_text = product.css("span.ins span.amount::text").get()
            if not price_text:
                price_text = product.css("span.price span.amount::text").get()

            price = None
            if price_text:
                cleaned = price_text.strip().replace(",", "").replace("₹", "")
                try:
                    price = int(cleaned)
                except ValueError:
                    price = None

            item = CpuPriceTrackerItem()
            item["name"] = name.strip()
            item["link"] = link
            item["price"] = price
            item["vendor"] = "MDComputers"

            yielded += 1
            self.collected += 1
            yield item

        expected = f" of {self.expected_total}" if self.expected_total else ""
        self.logger.info(
            "MDComputers page %d: %d tiles, %d items (collected %d%s)",
            page,
            len(products),
            yielded,
            self.collected,
            expected,
        )

        if self.total_pages and page >= self.total_pages:
            return

        if page < MAX_PAGES:
            yield scrapy.Request(
                PAGE_URL.format(page=page + 1),
                callback=self.parse,
                cb_kwargs={"page": page + 1},
            )
