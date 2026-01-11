import scrapy
from cpu_price_tracker.items import CpuPriceTrackerItem
class PcstudioSpider(scrapy.Spider):
    name = "pcstudio"
    allowed_domains = ["www.pcstudio.in"]
    start_urls = ["https://www.pcstudio.in/product-category/processor/?products-per-page=all"]
    custom_settings = {
        'CLOSESPIDER_TIMEOUT': 1
    }
    
    def start_requests(self):
        url="https://www.pcstudio.in/product-category/processor/?products-per-page=all"
        yield scrapy.Request(url, meta={'playwright': True})
    
    def parse(self, response):
        products = response.css("ul.products li.product")
        for product in products:
            name = product.css("li.title h2 a span::attr(title)").get()
            if not name:
                name = product.css("li.title h2 a::text").get()
            link = product.css("li.title a::attr(href)").get()
            price_text = product.css("ins bdi::text").get()

            price = None
            if price_text:
                cleaned_price = price_text.strip().replace(",", "").replace("₹", "")
                try:
                    price = int(cleaned_price)
                except ValueError:
                    price = None
            
            item = CpuPriceTrackerItem()
            item['name'] = name
            item['link'] = link
            item['price'] = price
            item['vendor'] = 'PC Studio'
            yield item