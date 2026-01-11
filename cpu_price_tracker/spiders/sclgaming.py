import scrapy
from cpu_price_tracker.items import CpuPriceTrackerItem

class SclgamingSpider(scrapy.Spider):
    name = "sclgaming"
    allowed_domains = ["sclgaming.in"]
    start_urls = ["https://sclgaming.in/product-category/processor/page/1/"]

    def parse(self, response):
        products = response.css('li.product')
        for product in products:
            # Try discounted price first
            price_text = product.css('.price ins span.woocommerce-Price-amount bdi::text').get()
            # If no discounted price, try regular price
            if not price_text:
                price_text = product.css('.price span.woocommerce-Price-amount bdi::text').get()

            price = None
            if price_text:
                cleaned_price = price_text.replace(",", "").strip()
                try:
                    price = int(cleaned_price)
                except ValueError:
                    price = None

            if price is not None:
                name = product.css('h2.woocommerce-loop-product__title::text').get()
                link = product.css('a.woocommerce-LoopProduct-link::attr(href)').get()
                
                item = CpuPriceTrackerItem()
                item['name'] = name
                item['link'] = link
                item['price'] = price
                item['vendor'] = 'SCL Gaming'
                yield item

            current_page = response.meta.get("page", 1)
            next_page = current_page + 1
            next_page_url = f"https://sclgaming.in/product-category/processor/page/{next_page}/"
            yield scrapy.Request(next_page_url, callback=self.parse, meta={"page": next_page})