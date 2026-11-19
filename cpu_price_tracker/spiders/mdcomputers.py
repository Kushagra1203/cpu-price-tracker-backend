"""MDComputers -- 62 processors across 4 pages of 20.

The listing prints its own size ("Showing 1 to 20 of 62 (4 Pages)"), so the
spider knows the target before it starts and can say how close it got -- per
page, not just in total, because the banner also states the range each page
covers ("Showing 21 to 40 of 62" on page 2).

Fetched through Playwright. A plain HTTP request works from a residential
connection but the 2026-11-19 run got HTTP 403 on page 1 from the GitHub
runner, while the same URL answered 200 from home with both a Chrome and a
Firefox user agent. A UA string cannot fix that: the runner's IP carries a
worse reputation and Scrapy's TLS fingerprint is not a browser's. A real
Chromium presents both, which is how Elitehubs and Vishal already survive
Cloudflare from the same runner.

Three things this spider learned the hard way, all of them from the
2026-11-19 runner log:

* The grid is server-rendered. Fetched without a browser at all, the page
  carries 20 product titles, 20 "product-wrapper" blocks inside the listing
  grid and the banner. The browser only has to fetch the document.
* There is a 21st "product-wrapper" outside the grid -- a hidden template --
  plus two more that the page's own JavaScript injects. Selecting
  "div.product-wrapper" therefore picked up 23 tiles on a page that says 20.
  The selector is scoped to the grid, which is what makes the per-page count
  come out exactly right.
* Cloudflare answered page 2 with 403 in 0.2 s, from the same browser, in the
  same session as the 200 on page 1. That used to be invisible: the wait for
  a product tile timed out, and scrapy-playwright threw the response away,
  so the log said "20 second timeout" and the status was lost. The wait is
  now tolerant, the status is logged, and a refused page is asked again a
  slot-delay later instead of ending the crawl.
"""

import scrapy
from scrapy_playwright.page import PageMethod

from cpu_price_tracker.browser import wait_for_selector_or_none
from cpu_price_tracker.items import CpuPriceTrackerItem
from cpu_price_tracker.listing import parse_showing_range

PAGE_URL = "https://mdcomputers.in/catalog/processor?page={page}"

MAX_PAGES = 20

# The listing grid. One product-wrapper lives outside it as a hidden
# template, and the page's JavaScript injects two more.
GRID = "div.product-products-holder div.product-wrapper"

# How many times one page may be re-asked after a refusal. The spacing comes
# from the "md-slow" download slot, set in settings.py.
MAX_ATTEMPTS = 3


class mdcomputerSpider(scrapy.Spider):
    name = "mdcomputers"
    allowed_domains = ["mdcomputers.in"]

    custom_settings = {
        # Only used if a request carries no download_slot; every request this
        # spider makes pins itself to "md-slow", whose delay is the real one.
        "DOWNLOAD_DELAY": 30,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.expected_total = None
        self.total_pages = None
        self.collected = 0

    def start_requests(self):
        yield self.page_request(1)

    def page_request(self, page, attempt=1):
        return scrapy.Request(
            PAGE_URL.format(page=page),
            callback=self.parse,
            cb_kwargs={"page": page, "attempt": attempt},
            meta={
                "playwright": True,
                # Every MD request goes through one download slot with a 30 s
                # gap, so a page that is refused is simply asked again after
                # the same gap as a page that was not. Scrapy has no
                # per-request delay -- request.meta["download_delay"] is not
                # read by the downloader at all -- but it does have per-slot
                # settings, and a request picks its slot by this key.
                "download_slot": "md-slow",
                "playwright_page_methods": [
                    # Must not raise: a 403 page has no product tiles, and
                    # raising here throws the response -- and the status that
                    # explains the refusal -- away.
                    PageMethod(wait_for_selector_or_none, GRID, 15000)
                ],
            },
        )

    def parse(self, response, page, attempt):
        if response.status != 200:
            self.logger.warning(
                "MDComputers page %d: HTTP %d (attempt %d of %d)",
                page,
                response.status,
                attempt,
                MAX_ATTEMPTS,
            )
            if attempt < MAX_ATTEMPTS:
                yield self.page_request(page, attempt + 1)
            return

        products = response.css(GRID)

        first, last, total, pages = parse_showing_range(response.text)
        if page == 1:
            self.expected_total = total
            self.total_pages = pages

        if not products:
            self.logger.warning(
                "MDComputers page %d: no products on the page, stopping", page
            )
            return

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

        # The banner says how many products this page holds, so the page can
        # be checked against the site's own number rather than against a
        # hard-coded one that would rot the moment a vendor adds a CPU.
        expected = f" of {last}" if last else ""
        self.logger.info(
            "MDComputers page %d: %d tiles, %d items (collected %d%s)",
            page,
            len(products),
            yielded,
            self.collected,
            expected,
        )
        if last and yielded != last:
            self.logger.error(
                "MDComputers page %d: the site says this page shows %d products "
                "but only %d were captured",
                page,
                last,
                yielded,
            )

        if self.total_pages and page >= self.total_pages:
            return

        if page < MAX_PAGES:
            yield self.page_request(page + 1)
