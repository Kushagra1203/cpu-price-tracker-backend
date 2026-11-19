"""SCL Gaming -- 213 processors over 11 pages of 20, of which 70 are in stock.

Availability is invisible on the listing. An out-of-stock card looks exactly
like a purchasable one: same photo, same price, no badge. The Ryzen 5 5600X,
for instance, shows "Rs 12,250" on the grid and "Out of stock" only after you
open it. So price is not a proxy for availability.

The listing does carry the state, in each card's class attribute. WooCommerce's
wc_product_class adds ``instock`` or ``outofstock`` to every loop item, and
that is the same field the product page renders. Verified card-class against
product-page for the Ryzen 5 5600X, the Ryzen 5 5600T, and both Threadripper
9975WX SKUs (box vs tray, which correctly disagree with each other).

Keeping only ``instock`` cards is what makes this vendor usable. Without it,
the spider would record prices for 143 products nobody can buy.

Pagination stops when a page adds no new product links. /page/12/ returns HTTP
200 with zero products and still advertises pages 11 and 12, so "stop when the
grid is empty" is not enough on its own.

Each product appears twice in the markup (a slide plus a grid cell), so links
are deduplicated before they are counted or yielded.
"""

import re

import scrapy
from scrapy_playwright.page import PageMethod

from cpu_price_tracker.browser import wait_for_selector_or_none
from cpu_price_tracker.items import CpuPriceTrackerItem

PAGE_URL = "https://sclgaming.in/product-category/processor/page/{page}/"

# 11 real pages today; the cap only exists so a broken pagination rule cannot
# loop forever.
MAX_PAGES = 25


class SclgamingSpider(scrapy.Spider):
    name = "sclgaming"
    allowed_domains = ["sclgaming.in"]

    custom_settings = {
        "DOWNLOAD_DELAY": 3,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "ROBOTSTXT_OBEY": False,
        "USER_AGENT": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.seen_links = set()
        self.collected = 0

    def start_requests(self):
        yield self.page_request(1)

    def page_request(self, page):
        # Playwright for the same reason as MDComputers: plain HTTP gets 200
        # from a residential connection but the 2026-11-19 runner run was
        # answered 403 on page 1, and a user-agent string does not change an
        # IP reputation or Scrapy's TLS fingerprint.
        return scrapy.Request(
            PAGE_URL.format(page=page),
            callback=self.parse,
            cb_kwargs={"page": page},
            meta={
                "playwright": True,
                "playwright_page_methods": [
                    # Must not raise: a Cloudflare 403 body has no product
                    # cards, and raising here throws the response away, so
                    # the log says "20 second timeout" and the status that
                    # explains the refusal is lost.
                    PageMethod(wait_for_selector_or_none, "div.e-loop-item", 15000)
                ],
            },
        )

    def parse(self, response, page):
        if response.status != 200:
            self.logger.warning(
                "SCL Gaming page %d: HTTP %d from %s",
                page,
                response.status,
                response.url,
            )
            return

        cards = response.css("div.e-loop-item.product_cat-processor")
        if not cards:
            self.logger.info("SCL Gaming: no cards on page %d, stopping", page)
            return

        new_links = 0
        in_stock = 0
        no_price = 0

        for card in cards:
            classes = card.attrib.get("class", "")
            if "outofstock" in classes or "instock" not in classes:
                continue
            in_stock += 1

            title = card.css("h3.elementor-heading-title a")
            if not title:
                continue
            name = " ".join((title[0].xpath("string(.)").get() or "").split())
            link = title[0].attrib.get("href")
            if not name or not link:
                continue
            if link in self.seen_links:
                continue
            self.seen_links.add(link)
            new_links += 1

            price_block = card.css("p.price ins bdi") or card.css("p.price bdi")
            price = None
            if price_block:
                raw = price_block[0].xpath("string(.)").get() or ""
                digits = re.sub(r"[^\d]", "", raw)
                if digits:
                    price = int(digits)

            if price is None:
                no_price += 1
                continue

            item = CpuPriceTrackerItem()
            item["name"] = name
            item["link"] = link
            item["price"] = price
            item["vendor"] = "SCL Gaming"

            self.collected += 1
            yield item

        self.logger.info(
            "SCL Gaming page %d: %d cards, %d in stock, %d new items "
            "(collected %d; %d in-stock cards had no price)",
            page,
            len(cards),
            in_stock,
            new_links,
            self.collected,
            no_price,
        )

        if new_links == 0:
            self.logger.info("SCL Gaming: page %d added nothing new, stopping", page)
            return

        if page < MAX_PAGES:
            yield self.page_request(page + 1)
