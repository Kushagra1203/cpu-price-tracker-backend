import scrapy
from cpu_price_tracker.items import CpuPriceTrackerItem

class VishalperipheralsSpider(scrapy.Spider):
    name = "vishalperipherals"
    allowed_domains = ["vishalperipherals.com"]
    start_urls = ["https://vishalperipherals.com/collections/processors?page=1"]

    custom_settings = {
        'DOWNLOAD_DELAY': 2,
        'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0 Safari/537.36',
        'RETRY_HTTP_CODES': [429, 500, 502, 503, 504, 522, 524, 408],
        'RETRY_TIMES': 5,
    }

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

        current_page = response.meta.get("page", 1)
        next_page = current_page + 1
        next_page_url = f"https://vishalperipherals.com/collections/processors?page={next_page}"
        yield scrapy.Request(next_page_url, callback=self.parse, meta={"page": next_page})
