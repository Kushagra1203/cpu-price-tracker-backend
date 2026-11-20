"""SCL Gaming -- the in-stock processors from an 11-page WooCommerce listing.

An out-of-stock card looks identical to a buyable one (same photo, same price,
no badge); the only signal is each card's "instock"/"outofstock" class.
"""

import re

import scrapy
from playwright.async_api import TimeoutError as PlaywrightTimeout
from scrapy_playwright.page import PageMethod

from cpu_price_tracker.items import CpuPriceTrackerItem

PAGE_URL = "https://sclgaming.in/product-category/processor/page/{page}/"
MAX_PAGES = 25


async def _wait_for_grid(page):
    """Wait for the product grid, but never raise.

    The plain ``PageMethod("wait_for_selector", ...)`` raises on timeout, and
    scrapy-playwright then throws the whole response away -- taking the HTTP
    status with it, which is the only thing that explains a block.
    """
    try:
        await page.wait_for_selector("div.e-loop-item", state="attached", timeout=15000)
    except PlaywrightTimeout:
        pass


class SclgamingSpider(scrapy.Spider):
    name = "sclgaming"
    allowed_domains = ["sclgaming.in"]

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
        # Each product appears twice in the markup (slide + grid cell).
        self.seen_links = set()

    def start_requests(self):
        yield self.page_request(1)

    def page_request(self, page):
        return scrapy.Request(
            PAGE_URL.format(page=page),
            callback=self.parse,
            cb_kwargs={"page": page},
            meta={
                "playwright": True,
                "playwright_page_methods": [PageMethod(_wait_for_grid)],
            },
        )

    def parse(self, response, page):
        if response.status != 200:
            self.logger.warning("SCL Gaming page %d: HTTP %d", page, response.status)
            return

        cards = response.css("div.e-loop-item.product_cat-processor")
        if not cards:
            self.logger.info("SCL Gaming: no cards on page %d, stopping", page)
            return

        new_links = 0
        for card in cards:
            classes = card.attrib.get("class", "")
            if "outofstock" in classes or "instock" not in classes:
                continue

            title = card.css("h3.elementor-heading-title a")
            if not title:
                continue
            name = " ".join((title[0].xpath("string(.)").get() or "").split())
            link = title[0].attrib.get("href")
            if not name or not link or link in self.seen_links:
                continue
            self.seen_links.add(link)
            new_links += 1

            price_block = card.css("p.price ins bdi") or card.css("p.price bdi")
            digits = re.sub(r"[^\d]", "", (price_block[0].xpath("string(.)").get() or "")) if price_block else ""
            if not digits:
                continue

            item = CpuPriceTrackerItem()
            item["name"] = name
            item["link"] = link
            item["price"] = int(digits)
            item["vendor"] = "SCL Gaming"
            yield item

        self.logger.info(
            "SCL Gaming page %d: %d cards, %d new items", page, len(cards), new_links
        )

        # A page past the end still returns 200 with the last page's links,
        # so "no new links" is the stop condition, not an empty grid.
        if new_links == 0 or page >= MAX_PAGES:
            return
        yield self.page_request(page + 1)
