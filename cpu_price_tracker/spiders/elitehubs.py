import scrapy
from scrapy_playwright.page import PageMethod

from cpu_price_tracker.items import CpuPriceTrackerItem

# usf_take is the filter app's page size. 56 was verified in a browser to render
# all 50 in-stock processors; 100 appears to exceed the app's maximum and falls
# back to its default page of 24 (measured on 2026-11-19), so bigger is not
# better here.
START_TAKE = 56


class ElitehubsSpider(scrapy.Spider):
    name = "elitehubs"
    allowed_domains = ["elitehubs.com"]

    def start_requests(self):
        yield self.page_request(START_TAKE)

    def page_request(self, take):
        # The take value is passed through cb_kwargs rather than read back from
        # response.url: the filter app rewrites the address bar with
        # history.replaceState after load, dropping usf_take. Parsing the final
        # URL therefore found no take at all and stopped the crawl after one
        # page ("Could not parse usf_take ... Stopping", 2026-11-19).
        url = (
            "https://elitehubs.com/collections/processor"
            f"?uff_pwm43v_stockStatus=1&usf_take={take}"
        )
        return scrapy.Request(
            url,
            callback=self.parse,
            cb_kwargs={"take": take},
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

    def parse(self, response, take):
        products = response.css("div.usf-results div.grid__item")

        if not products:
            self.logger.info("Elitehubs: no products on the page, stopping")
            return

        yielded = 0
        for product in products:
            name = product.css("div.product-collection__title a::text").get()
            if not name:
                # A grid tile that is not a product (promo banner, spacer).
                # It used to be yielded with name=None and link=<collection url>,
                # which later crashed the normalizer and poisoned the table.
                continue
            link = response.urljoin(
                product.css("div.product-collection__title a::attr(href)").get()
            )
            if not link:
                continue

            price_text = product.css("span.current::text").get()
            price = None
            if price_text:
                try:
                    price = int(price_text.replace("Rs.", "").replace(",", "").strip())
                except ValueError:
                    price = None

            item = CpuPriceTrackerItem()
            item["name"] = name.strip()
            item["link"] = link
            item["price"] = price
            item["vendor"] = "Elitehubs"

            yielded += 1
            yield item

        self.logger.info(
            "Elitehubs: %d tiles, %d items (usf_take=%d; the in-stock collection holds 50)",
            len(products),
            yielded,
            take,
        )

        # Only ask for another page if this one was full. Every request after the
        # first is answered with a Cloudflare 429, so asking when there is
        # nothing left costs four retries and gains nothing.
        if len(products) < take:
            return

        yield self.page_request(take + 28)
