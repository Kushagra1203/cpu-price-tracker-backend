"""Vedant Computers -- 41 processors, all on one page.

?limit=100 makes OpenCart render the whole catalogue in a single response, so
there is no pagination and no need for a browser: the product grid and the
"Showing 1 to 41 of 41 (1 Pages)" banner are both in the server HTML. Dropping
Playwright here removes a browser launch from every run.
"""

import scrapy

from cpu_price_tracker.items import CpuPriceTrackerItem
from cpu_price_tracker.listing import parse_showing_total

LISTING_URL = "https://www.vedantcomputers.com/pc-components/processor?limit=100"


class VedantcomputersSpider(scrapy.Spider):
    name = "vedantcomputers"
    allowed_domains = ["vedantcomputers.com"]

    custom_settings = {
        "DOWNLOAD_DELAY": 3,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "USER_AGENT": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
    }

    def start_requests(self):
        yield scrapy.Request(LISTING_URL, callback=self.parse)

    def parse(self, response):
        products = response.css("div.product-thumb")

        if not products:
            self.logger.info("Vedant Computers: no products found, stopping")
            return

        expected_total, total_pages = parse_showing_total(response.text)

        yielded = 0
        for product in products:
            name = product.css("div.name a::text").get()
            link = product.css("div.name a::attr(href)").get()
            if not name or not link:
                continue

            price_text = product.css("span.price-new::text").get()
            price = None
            if price_text:
                cleaned = (
                    price_text.strip()
                    .replace(",", "")
                    .replace("₹", "")
                    .replace(".00", "")
                )
                try:
                    price = int(cleaned)
                except ValueError:
                    price = None

            item = CpuPriceTrackerItem()
            item["name"] = name.strip()
            item["link"] = response.urljoin(link)
            item["price"] = price
            item["vendor"] = "Vedant Computers"

            yielded += 1
            yield item

        expected = f" of {expected_total}" if expected_total else ""
        pages = f", {total_pages} page(s)" if total_pages else ""
        self.logger.info(
            "Vedant Computers: %d tiles, %d items%s%s",
            len(products),
            yielded,
            expected,
            pages,
        )
