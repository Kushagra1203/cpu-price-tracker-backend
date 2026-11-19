"""Computech Store -- a plain HTML scrape, 20 products per request.

The storefront is a custom Tailwind/htmx app, not WooCommerce (every
/wp-json/ route answers 404), so there is no API to read. The grid arrives
server-rendered inside #product-grid-container and "load more" is an htmx
request for ?page=N&sort=name_asc.

Pagination stops on repeated product links rather than on a short page. That
detail matters: asking for a page past the end does not return an empty grid,
it returns the last page again -- ?page=7 and ?page=20 both answer with the
same single product that ?page=6 holds. A "stop when fewer than 20 cards"
rule would therefore never fire when the catalogue size is an exact multiple
of 20, and would spin until the page cap. Counting links already seen stops
the walk on the first page that adds nothing.
"""

import re

import scrapy

from cpu_price_tracker.items import CpuPriceTrackerItem

BASE_URL = "https://computechstore.in/product-category/processor/"

PAGE_SIZE = 20

# A sanity cap, not an expected size: the catalogue is 101 products (6 pages).
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

        yielded = 0
        no_price = 0
        no_badge = 0

        for card in cards:
            name = card.css("h3::text").get()
            href = card.css("a[href^='/product/']::attr(href)").get()
            if not name or not href:
                continue

            link = response.urljoin(href)
            if link in self.seen_links:
                # Page past the end: the site re-serves its last page.
                continue
            self.seen_links.add(link)

            price_text = card.css("div.items-baseline span::text").get()
            price = None
            if price_text:
                digits = re.sub(r"[^\d]", "", price_text)
                if digits:
                    price = int(digits)

            if price is None:
                # Out of stock usually means the price element is replaced by
                # a "notify me" block, so there is nothing to track.
                no_price += 1
                continue

            if "In Stock" not in card.get():
                # A price without an in-stock badge. The store shows no
                # "Out of Stock" badge at all, so these are ambiguous rather
                # than definitely unavailable -- and they still quote a price,
                # which is what this project records. Counted, not silently kept.
                no_badge += 1

            item = CpuPriceTrackerItem()
            item["name"] = name.strip()
            item["link"] = link
            item["price"] = price
            item["vendor"] = "Computech Store"

            yielded += 1
            yield item

        self.logger.info(
            "Computech page %d: %d cards, %d new items (collected %d; "
            "%d without a price, %d without an in-stock badge)",
            page,
            len(cards),
            yielded,
            len(self.seen_links),
            no_price,
            no_badge,
        )

        if yielded == 0:
            self.logger.info("Computech: page %d added nothing new, stopping", page)
            return

        if page < MAX_PAGES:
            yield self.page_request(page + 1)
