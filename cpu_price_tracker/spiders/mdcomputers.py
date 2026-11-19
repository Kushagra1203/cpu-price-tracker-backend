"""MDComputers -- 62 processors across 4 pages of 20.

The listing prints its own size ("Showing 1 to 20 of 62 (4 Pages)"), so the
spider knows the target before it starts and says how close it got.

Fetched through Playwright. A plain HTTP request works from a residential
connection but the 2026-11-19 run got HTTP 403 on page 1 from the GitHub
runner, while the same URL answered 200 from home with both a Chrome and a
Firefox user agent. A UA string cannot fix that: the runner's IP carries a
worse reputation and Scrapy's TLS fingerprint is not a browser's. A real
Chromium presents both, which is how Elitehubs and Vishal already survive
Cloudflare from the same runner.

The grid is server-rendered, so the wait has nothing to do with JavaScript
rendering -- it is there so the capture happens after Cloudflare has either
served the page or refused it, instead of scraping a challenge body.
"""

import scrapy
from scrapy_playwright.page import PageMethod

from cpu_price_tracker.items import CpuPriceTrackerItem
from cpu_price_tracker.listing import parse_showing_total

PAGE_URL = "https://mdcomputers.in/catalog/processor?page={page}"

MAX_PAGES = 20


class mdcomputerSpider(scrapy.Spider):
    name = "mdcomputers"
    allowed_domains = ["mdcomputers.in"]

    custom_settings = {
        "DOWNLOAD_DELAY": 2,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.expected_total = None
        self.total_pages = None
        self.collected = 0

    def start_requests(self):
        yield self.page_request(1)

    def page_request(self, page):
        return scrapy.Request(
            PAGE_URL.format(page=page),
            callback=self.parse,
            cb_kwargs={"page": page},
            meta={
                "playwright": True,
                "playwright_page_methods": [
                    PageMethod("wait_for_selector", "div.product-wrapper", timeout=20000)
                ],
            },
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
            yield self.page_request(page + 1)
