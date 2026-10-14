import scrapy
from cpu_price_tracker.items import CpuPriceTrackerItem

class VishalperipheralsSpider(scrapy.Spider):
    name = "vishalperipherals"
    allowed_domains = ["vishalperipherals.com"]
    start_urls = ["https://vishalperipherals.com/collections/processors?page=1"]

    custom_settings = {
        'DOWNLOAD_DELAY': 5,
        'USER_AGENT': 'Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0',
        'RETRY_HTTP_CODES': [429, 500, 502, 503, 504, 522, 524, 408],
        'RETRY_TIMES': 8,
        'CLOSESPIDER_PAGECOUNT': 50,
    }

    def start_requests(self):
        for url in self.start_urls:
            yield scrapy.Request(
                url,
                meta={
                    "playwright": True,
                    "playwright_page_methods": [
                        ("wait_for_selector", "div.product-collection")
                    ]
                },
            )

    def parse(self, response):
        products = response.css("div.product-collection")
        if len(products) == 0:
            self.logger.info("No products found or end of collection reached, stopping.")
            return
        for product in products:
            in_stock = product.css('div.product-collection__availability p.in_stock')
            if not in_stock:
                continue

            name = product.css('div.product-collection__title a::text').get()
            if name:
                name = name.strip()

            relative_link = product.css('div.product-collection__title a::attr(href)').get()
            link = response.urljoin(relative_link) if relative_link else None

            price_text = product.css('div.frm-price-color span.price--sale span.current::text').get()
            price = None
            if price_text:
                cleaned_price = price_text.strip().replace(",", "").replace("₹  ", "")
                try:
                    price = int(cleaned_price)
                except ValueError:
                    price = None

            item = CpuPriceTrackerItem()
            item['name'] = name
            item['link'] = link
            item['price'] = price
            item['vendor'] = 'Vishal Peripherals'

            yield item

        # Pagination with stop condition - check for next page link
        next_page_link = response.css("a.pagination__next::attr(href), a.next::attr(href), link[rel='next']::attr(href)").get()
        if next_page_link:
            yield scrapy.Request(
                next_page_link,
                callback=self.parse,
                meta={
                    "playwright": True,
                    "playwright_page_methods": [
                        ("wait_for_selector", "div.product-collection")
                    ]
                }
            )
        else:
            self.logger.info("No next page link found, stopping")
