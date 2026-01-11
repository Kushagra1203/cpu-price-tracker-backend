import scrapy
from cpu_price_tracker.items import CpuPriceTrackerItem

class VedantcomputersSpider(scrapy.Spider):
    name = "vedantcomputers"
    allowed_domains = ["vedantcomputers.com"]
    start_urls = ["https://www.vedantcomputers.com/pc-components/processor?limit=100"]
    custom_settings = {
        'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
        'ROBOTSTXT_OBEY': False,
        'DOWNLOAD_DELAY': 3,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 2,
        'CLOSESPIDER_TIMEOUT': 300,
        'DOWNLOAD_HANDLERS': {
            "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
            "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
        },
        'TWISTED_REACTOR': "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
        'COOKIES_ENABLED': True,
        'RETRY_ENABLED': True,
        'RETRY_TIMES': 3,
    }
    
    def start_requests(self):
        url="https://www.vedantcomputers.com/pc-components/processor?limit=100"
        yield scrapy.Request(url, meta={'playwright': True})

    def parse(self, response):
        # Select only real product blocks, avoid carousels etc.
        products = response.css("div.product-thumb")
        
        for product in products:
            name = product.css('div.name a::text').get()
            if name:
                name = name.strip()

            link = product.css('div.name a::attr(href)').get()

            price_text = product.css('span.price-new::text').get()
            price = None
            if price_text:
                cleaned_price = price_text.strip().replace(",", "").replace("₹", "").replace(".00", "")
                try:
                    price = int(cleaned_price)
                except ValueError:
                    price = None
                    
            item = CpuPriceTrackerItem()
            item['name'] = name
            item['link'] = link
            item['price'] = price
            item['vendor'] = 'Vedant Computers'
            yield item
