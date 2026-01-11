import scrapy
from cpu_price_tracker.items import CpuPriceTrackerItem

class ShwetacomputersSpider(scrapy.Spider):
    name = "shwetacomputers"
    allowed_domains = ["shwetacomputers.com"]
    start_urls = ["https://shwetacomputers.com/collections/processor?filter.v.price.gte=0&filter.v.price.lte=69699&filter.v.availability=1&sort_by=manual&page=1"]
    custom_settings = {
        'DOWNLOAD_DELAY': 2,
        'ROBOTSTXT_OBEY': False,
        'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0 Safari/537.36',
        'RETRY_HTTP_CODES': [429, 500, 502, 503, 504, 522, 524, 408],
        'RETRY_TIMES': 5,
    }
    def parse(self, response):
        products = response.css("div.\\#product-card")
        base_url = "https://shwetacomputers.com"
        
        if not products:
            return
        
        for product in products:
            raw_text = product.css("span.\\#text-truncate::text").get()
            name = " ".join(raw_text.split()).strip() if raw_text else None

            relative_url = product.css('a.stretched-link::attr(href)').get()
            link = base_url + relative_url if relative_url else None

            price_text = product.css('span.\\#price-value::text').get()
            price = None
            if price_text:
                cleaned_price = price_text.replace("Rs. ", "").replace(",","").strip()
                try:
                    price = int(cleaned_price)
                except ValueError:
                    price = None

            item = CpuPriceTrackerItem()
            item['name'] = name
            item['link'] = link
            item['price'] = price
            item['vendor'] = 'Shweta Computers'
            yield item

        current_page = response.meta.get("page", 1)
        next_page = current_page + 1
        next_page_url = f"https://shwetacomputers.com/collections/processor?filter.v.price.gte=0&filter.v.price.lte=69699&filter.v.availability=1&sort_by=manual&page={next_page}"
        yield scrapy.Request(next_page_url, callback=self.parse, meta={"page": next_page})