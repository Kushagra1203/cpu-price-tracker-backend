"""The IT Depot -- 53 processors across 5 pages of 12.

The site states its own catalogue size in the listing banner:

    Showing 1 to 12 of 53 (5 Pages)

That number drives both the stop condition and the completeness check, so the
spider knows when it is done instead of requesting a sixth page and inferring
from an empty response.

It also runs slowly on purpose. Each listing page is ~1 MB of HTML and the
previous configuration fetched five of them back to back with no delay, which
earned an HTTP 429 from the site's LiteSpeed rate limiter on 2026-11-19 and
cost the whole vendor for that night. The vendor itself was fine: the same
five pages returned 200 from an ordinary connection minutes later.
"""

import scrapy

from cpu_price_tracker.items import CpuPriceTrackerItem
from cpu_price_tracker.listing import parse_showing_total

PAGE_URL = "https://www.theitdepot.com/Processor?page={page}&fq=1"

# Five pages today; leave room for a growing catalogue without letting a broken
# pagination rule loop forever.
MAX_PAGES = 20


class TheitdepotSpider(scrapy.Spider):
    name = "theitdepot"
    allowed_domains = ["www.theitdepot.com"]

    custom_settings = {
        "DOWNLOAD_DELAY": 3,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 2,
        "AUTOTHROTTLE_MAX_DELAY": 30,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 1.0,
        "RETRY_TIMES": 5,
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
        yield self.page_request(1)

    def page_request(self, page):
        return scrapy.Request(
            PAGE_URL.format(page=page),
            callback=self.parse,
            cb_kwargs={"page": page},
        )

    def parse(self, response, page):
        products = response.css("div.product-thumb")

        if not products:
            self.logger.info("The IT Depot: no products on page %d, stopping", page)
            return

        if page == 1:
            self.expected_total, self.total_pages = parse_showing_total(response.text)

        yielded = 0
        for product in products:
            name = product.css("div.name a::text").get()
            link = product.css("div.name a::attr(href)").get()
            if not name or not link:
                continue

            price_text = product.css("div.price span.price-new::text").get()
            price = None
            if price_text:
                cleaned = (
                    price_text.replace("₹", "").replace(".00", "").replace(",", "").strip()
                )
                try:
                    price = int(cleaned)
                except ValueError:
                    price = None

            item = CpuPriceTrackerItem()
            item["name"] = name.strip()
            item["link"] = response.urljoin(link)
            item["price"] = price
            item["vendor"] = "The IT Depot"

            yielded += 1
            self.collected += 1
            yield item

        expected = f" of {self.expected_total}" if self.expected_total else ""
        self.logger.info(
            "The IT Depot page %d: %d tiles, %d items (collected %d%s)",
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
