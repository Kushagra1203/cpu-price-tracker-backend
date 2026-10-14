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
        yield scrapy.Request(url, meta={'playwright': True, 'page': 1})
    
    def parse(self, response):
        # Select only real product blocks, avoid carousels etc.
        products = response.css("div.product-thumb")
        
        if not products:
            self.logger.info("No products found, stopping")
            return
        
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

        # Check for pagination
        current_page = response.meta.get('page', 1)
        next_page = current_page + 1
        next_url = f"https://www.vedantcomputers.com/pc-components/processor?limit=100&page={next_page}"
        
        # Try to find next page link in pagination
        next_link = response.css("ul.pagination li a::attr(href)").re_first(rf'page={next_page}')
        if not next_link:
            # Try common next page selectors
            next_link = response.css("a.next::attr(href), li.next a::attr(href), .pagination a[rel='next']::attr(href)").get()
        
        if next_link:
            yield scrapy.Request(next_link, callback=self.parse, meta={'playwright': True, 'page': next_page})
        else:
            self.logger.info(f"No next page link found for page {next_page}, stopping")
