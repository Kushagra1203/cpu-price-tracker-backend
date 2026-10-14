import scrapy
from cpu_price_tracker.items import CpuPriceTrackerItem

class PcstudioSpider(scrapy.Spider):
    name = "pcstudio"
    allowed_domains = ["www.pcstudio.in"]
    start_urls = ["https://www.pcstudio.in/product-category/processor/"]
    custom_settings = {
        'CLOSESPIDER_PAGECOUNT': 50,
        'DOWNLOAD_DELAY': 3,
    }
    
    def start_requests(self):
        for url in self.start_urls:
            yield scrapy.Request(url, meta={'playwright': True})
    
    def parse(self, response):
        products = response.css("ul.products li.product")
        if not products:
            self.logger.info("No products found, stopping")
            return
        
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
        
        # Pagination - check for next page link
        next_page = response.css("a.next.page-numbers::attr(href)").get()
        if not next_page:
            next_page = response.css("a.page-numbers.next::attr(href)").get()
        if next_page:
            yield scrapy.Request(next_page, callback=self.parse, meta={'playwright': True})