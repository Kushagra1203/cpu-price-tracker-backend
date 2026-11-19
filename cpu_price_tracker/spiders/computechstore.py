"""Computech Store -- a plain HTML scrape, 20 products per request.

Custom Tailwind/htmx storefront, no WooCommerce API (every /wp-json/ route is
404). Pagination stops on repeated links because a page past the end re-serves
the last page instead of returning an empty grid.
"""

import re

import scrapy

from cpu_price_tracker.items import CpuPriceTrackerItem

BASE_URL = "https://computechstore.in/product-category/processor/"
MAX_PAGES = 10


class ComputechstoreSpider(scrapy.Spider):
    name = "computechstore"
    allowed_domains = ["computechstore.in"]

    custom_settings = {
        "DOWNLOAD_DELAY": 2,
        "USER_AGENT": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.seen_links = set()

    def start_requests(self):
        yield self.page_request(1)

    def page_request(self, page):
        url = BASE_URL if page == 1 else f"{BASE_URL}?page={page}&sort=name_asc"
        return scrapy.Request(url, callback=self.parse, cb_kwargs={"page": page})

    def parse(self, response, page):
        cards = response.css("#product-grid-container > div.group")
        if not cards:
            self.logger.info("Computech: no products on page %d, stopping", page)
            return

        new_links = 0
        for card in cards:
            name = card.css("h3::text").get()
            href = card.css("a[href^='/product/']::attr(href)").get()
            if not name or not href:
                continue

            link = response.urljoin(href)
            if link in self.seen_links:
                continue
            self.seen_links.add(link)
            new_links += 1

            price_text = card.css("div.items-baseline span::text").get()
            digits = re.sub(r"[^\d]", "", price_text) if price_text else ""
            if not digits:
                # No price element: the store swaps it for a "notify me" block
                # on out-of-stock products.
                continue

            item = CpuPriceTrackerItem()
            item["name"] = name.strip()
            item["link"] = link
            item["price"] = int(digits)
            item["vendor"] = "Computech Store"
            yield item

        self.logger.info(
            "Computech page %d: %d cards, %d new items", page, len(cards), new_links
        )

        if new_links == 0 or page >= MAX_PAGES:
            return
        yield self.page_request(page + 1)
