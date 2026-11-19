import scrapy
from scrapy_playwright.page import PageMethod

from cpu_price_tracker.items import CpuPriceTrackerItem


class ElitehubsSpider(scrapy.Spider):
    name = "elitehubs"
    allowed_domains = ["elitehubs.com"]
    start_urls = [
        # usf_take is how many tiles the collection renders in one response.
        # 28 gave 21-26 in-stock processors while the collection holds 50, and
        # every request after the first is answered 429, so the only way to get
        # a complete snapshot is to ask for everything in the first request.
        # 100 covers the whole in-stock collection with room to spare; if the
        # filter app caps the value below the catalogue size the full-page test
        # in parse() still triggers pagination.
        "https://elitehubs.com/collections/processor?uff_pwm43v_stockStatus=1&usf_take=100"
    ]

    def start_requests(self):
        url = self.start_urls[0]
        yield scrapy.Request(
            url,
            meta={
                "playwright": True,
                # Must be a PageMethod, not a tuple. scrapy-playwright silently
                # ignores tuples ("expected PageMethod, got <class 'tuple'>"),
                # so this wait had never actually run.
                "playwright_page_methods": [
                    PageMethod("wait_for_selector", "div.product-collection")
                ],
            },
        )

    def parse(self, response):
        products=response.css("div.usf-results div.grid__item")
        
        if not products:
            self.logger.info("No more products. Stopping.")
            return

        for product in products:
            name = product.css("div.product-collection__title a::text").get()
            if not name:
                # A grid tile that is not a product (promo banner, spacer).
                # It used to be yielded with name=None and link=<collection url>,
                # which later crashed the normalizer and poisoned the table.
                continue
            link = response.urljoin(product.css("div.product-collection__title a::attr(href)").get())
            price_text = product.css("span.current::text").get()
            price = None
            if price_text:
                try:
                    price = int(price_text.replace("Rs.", "").replace(",", "").strip())
                except ValueError:
                    price = None

            item = CpuPriceTrackerItem()
            item["name"] = name
            item["link"] = link
            item["price"] = price
            item["vendor"] = "Elitehubs"
            yield item

        # figure out the current &usf_take value
        try:
            current_take = int(response.url.split("usf_take=")[-1])
        except (ValueError, IndexError):
            self.logger.info(f"Could not parse usf_take from {response.url}. Stopping.")
            return

        self.logger.info(
            "Elitehubs: %d tiles on the page (usf_take=%d, collection holds 50 in stock)",
            len(products),
            current_take,
        )

        # Only ask for another page if this one was full. Every request after the
        # first is answered with a Cloudflare 429, so asking when there is
        # nothing left costs four retries and gains nothing.
        if len(products) < current_take:
            return

        next_take = current_take * 2
        next_url = (
            f"https://elitehubs.com/collections/processor?uff_pwm43v_stockStatus=1&usf_take={next_take}"
        )

        yield scrapy.Request(
            next_url,
            callback=self.parse,
            meta={
                "playwright": True,
                "playwright_page_methods": [
                    PageMethod("wait_for_selector", "div.product-collection")
                ],
            },
        )
