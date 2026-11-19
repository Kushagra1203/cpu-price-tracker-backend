import re

import scrapy
from scrapy_playwright.page import PageMethod

from cpu_price_tracker.items import CpuPriceTrackerItem

# Shopify's search app filters availability server-side, so every tile on the
# page is in stock. The collection URL the spider used before
# (/collections/processors?page=N) shows 20 tiles of which half are out of
# stock and exposes no working next-page link, so the spider stopped after one
# page and reported 10 products for a catalogue of 46.
SEARCH_URL = (
    "https://vishalperipherals.com/a/search/processors"
    "?filter_availability%5Bin_stock%5D=true"
)

MAX_PAGES = 10


class VishalperipheralsSpider(scrapy.Spider):
    name = "vishalperipherals"
    allowed_domains = ["vishalperipherals.com"]

    custom_settings = {
        "DOWNLOAD_DELAY": 5,
        "USER_AGENT": "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
        "RETRY_HTTP_CODES": [429, 500, 502, 503, 504, 522, 524, 408],
        "RETRY_TIMES": 8,
        "CLOSESPIDER_PAGECOUNT": 50,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The same product can appear twice in the grid (desktop/mobile markup),
        # and the pagination stop condition counts distinct products.
        self.seen_links = set()
        self.expected_total = None
        self.collected = 0

    def start_requests(self):
        yield self.page_request(1)

    def page_request(self, page):
        url = SEARCH_URL if page == 1 else f"{SEARCH_URL}&page={page}"
        return scrapy.Request(
            url,
            callback=self.parse,
            cb_kwargs={"page": page},
            meta={
                "playwright": True,
                "playwright_page_methods": [
                    PageMethod("wait_for_selector", "div.product-collection")
                ],
            },
        )

    def parse(self, response, page):
        products = response.css("div.product-collection")
        if not products:
            self.logger.info("Vishal: no products on page %d, stopping", page)
            return

        # The listing states its own size: "46 of 141 products". That is the
        # only way to tell a complete scrape from a truncated one.
        match = re.search(r"(\d+)\s+of\s+(\d+)\s+products", response.text)
        if match:
            self.expected_total = int(match.group(1))

        yielded = 0
        for product in products:
            if not product.css("div.product-collection__availability p.in_stock"):
                continue

            name = product.css("div.product-collection__title a::text").get()
            relative_link = product.css(
                "div.product-collection__title a::attr(href)"
            ).get()
            if not name or not relative_link:
                continue

            name = name.strip()
            link = response.urljoin(relative_link)
            if link in self.seen_links:
                continue
            self.seen_links.add(link)

            price_text = product.css("div.frm-price-color span.current::text").get()
            price = None
            if price_text:
                digits = re.sub(r"[^\d]", "", price_text)
                if digits:
                    price = int(digits)

            item = CpuPriceTrackerItem()
            item["name"] = name
            item["link"] = link
            item["price"] = price
            item["vendor"] = "Vishal Peripherals"

            yielded += 1
            self.collected += 1
            yield item

        expected = f" of {self.expected_total}" if self.expected_total else ""
        self.logger.info(
            "Vishal page %d: %d tiles, %d new items (collected %d%s)",
            page,
            len(products),
            yielded,
            self.collected,
            expected,
        )

        if self.expected_total and self.collected >= self.expected_total:
            return
        if page < MAX_PAGES:
            yield self.page_request(page + 1)
