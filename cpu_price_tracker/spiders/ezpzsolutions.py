import scrapy
from cpu_price_tracker.items import CpuPriceTrackerItem

class EzpzsolutionsSpider(scrapy.Spider):
    name = "ezpzsolutions"
    allowed_domains = ["www.ezpzsolutions.in"]
    start_urls = ["https://www.ezpzsolutions.in/processors/page/1/"]

    def parse(self, response):
        products=response.css("div.woocommerce-card__header")
        for product in products:
            name = product.css("div.woocommerce-loop-product__title a::text").get()
            link = product.css("div.woocommerce-loop-product__title a::attr(href)").get()

            price_text = product.css("ins bdi::text").get()
            price = None
            if price_text:
                cleaned_price = price_text.strip().replace(",", "")
                try:
                    price = int(cleaned_price)
                except ValueError:
                    price = None

            item = CpuPriceTrackerItem()
            item['name'] = name
            item['link'] = link
            item['price'] = price
            item['vendor'] = 'Ezpz Solutions'
            yield item

        current_page = response.meta.get("page", 1)
        next_page = current_page + 1
        next_page_url = f"https://www.ezpzsolutions.in/processors/page/{next_page}/"
        yield scrapy.Request(next_page_url, callback=self.parse, meta={"page": next_page})
            
