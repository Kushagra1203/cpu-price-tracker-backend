import scrapy
from cpu_price_tracker.items import CpuPriceTrackerItem

class TheitdepotSpider(scrapy.Spider):
    name = "theitdepot"
    allowed_domains = ["www.theitdepot.com"]
    start_urls = ["https://www.theitdepot.com/Processor?page=1&fq=1"]

    def parse(self, response):
        products=response.css("div.product-thumb")
        
        if not products:
            return
        
        for product in products:
            name = product.css("div.name a::text").get()
            link = product.css("div.name a::attr(href)").get()
            price_text = product.css("div.price span.price-new::text").get()
            
            price = None
            if price_text:
                cleaned_price = price_text.replace("₹", "").replace(".00", "").replace(",", "").strip()
                try:
                    price = int(cleaned_price)
                except ValueError:
                    price = None
            
            item = CpuPriceTrackerItem()
            item['name'] = name
            item['link'] = link
            item['price'] = price
            item['vendor'] = 'The IT Depot'
            yield item

        current_page = response.meta.get("page", 1)
        next_page = current_page + 1
        next_page_url = f"https://www.theitdepot.com/Processor?page={next_page}&fq=1"
        yield scrapy.Request(next_page_url, callback=self.parse, meta={"page": next_page})