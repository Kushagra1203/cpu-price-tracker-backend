"""The IT Depot -- 53 processors across 5 pages of 12.

The banner ("Showing 1 to 12 of 53 (5 Pages)") states the catalogue size, so it
drives the stop condition. Pages are ~1 MB of HTML, so this runs at one request
every 3 s -- back-to-back fetching earned a 429 from the rate limiter.
"""

import scrapy

from cpu_price_tracker.items import CpuPriceTrackerItem
from cpu_price_tracker.listing import parse_showing_total

PAGE_URL = "https://www.theitdepot.com/Processor?page={page}&fq=1"
MAX_PAGES = 20


class TheitdepotSpider(scrapy.Spider):
    name = "theitdepot"
    allowed_domains = ["www.theitdepot.com"]

    custom_settings = {
        "DOWNLOAD_DELAY": 3,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.total_pages = None

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
            _, self.total_pages = parse_showing_total(response.text)

        for product in products:
            name = product.css("div.name a::text").get()
            link = product.css("div.name a::attr(href)").get()
            if not name or not link:
                continue

            price_text = product.css("div.price span.price-new::text").get()
            price = None
            if price_text:
                cleaned = price_text.replace("₹", "").replace(".00", "").replace(",", "").strip()
                try:
                    price = int(cleaned)
                except ValueError:
                    price = None

            item = CpuPriceTrackerItem()
            item["name"] = name.strip()
            item["link"] = response.urljoin(link)
            item["price"] = price
            item["vendor"] = "The IT Depot"
            yield item

        self.logger.info(
            "The IT Depot page %d: %d items", page, len(products)
        )

        if (self.total_pages and page >= self.total_pages) or page >= MAX_PAGES:
            return
        yield self.page_request(page + 1)
