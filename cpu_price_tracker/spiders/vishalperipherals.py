import re

import scrapy
from scrapy_playwright.page import PageMethod

from cpu_price_tracker.items import CpuPriceTrackerItem

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
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.seen_links = set()
        self.expected_total = None

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

        match = re.search(r"(\d+)\s+of\s+(\d+)\s+products", response.text)
        if match:
            self.expected_total = int(match.group(1))

        new_links = 0
        for product in products:
            if not product.css("div.product-collection__availability p.in_stock"):
                continue

            name = product.css("div.product-collection__title a::text").get()
            relative = product.css("div.product-collection__title a::attr(href)").get()
            if not name or not relative:
                continue

            link = response.urljoin(relative)
            if link in self.seen_links:
                continue
            self.seen_links.add(link)
            new_links += 1

            price_text = product.css("div.frm-price-color span.current::text").get()
            digits = re.sub(r"[^\d]", "", price_text) if price_text else ""
            if not digits:
                continue

            item = CpuPriceTrackerItem()
            item["name"] = name.strip()
            item["link"] = link
            item["price"] = int(digits)
            item["vendor"] = "Vishal Peripherals"
            yield item

        expected = f" of {self.expected_total}" if self.expected_total else ""
        self.logger.info(
            "Vishal page %d: %d tiles, %d new items%s", page, len(products), new_links, expected
        )

        if (self.expected_total and new_links == 0) or page >= MAX_PAGES:
            return
        yield self.page_request(page + 1)
