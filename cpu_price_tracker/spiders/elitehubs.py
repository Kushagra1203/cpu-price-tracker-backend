import scrapy
from cpu_price_tracker.items import CpuPriceTrackerItem


class ElitehubsSpider(scrapy.Spider):
    name = "elitehubs"
    allowed_domains = ["elitehubs.com"]
    start_urls = [
        "https://elitehubs.com/collections/processor?uff_pwm43v_stockStatus=1&usf_take=28"
    ]

    def start_requests(self):
        url = self.start_urls[0]
        yield scrapy.Request(
            url,
            meta={
                "playwright": True,
                "playwright_page_methods": [
                    # wait until the product grid is rendered
                    ("wait_for_selector", "div.product-collection")
                ]
            },
        )

    def parse(self, response):
        products=response.css("div.usf-results div.grid__item")
        
        if not products:
            self.logger.info("No more products. Stopping.")
            return

        for product in products:
            name = product.css("div.product-collection__title a::text").get()
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
        current_take = int(response.url.split("usf_take=")[-1])
        next_take = current_take + 28
        next_url = (
            f"https://elitehubs.com/collections/processor?uff_pwm43v_stockStatus=1&usf_take={next_take}"
        )

        yield scrapy.Request(
            next_url,
            callback=self.parse,
            meta={
                "playwright": True,
                "playwright_page_methods": [
                    ("wait_for_selector", "div.product-collection")
                ],
            },
        )
