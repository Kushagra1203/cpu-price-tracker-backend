import scrapy
from cpu_price_tracker.items import CpuPriceTrackerItem

class ShwetacomputersSpider(scrapy.Spider):
    name = "shwetacomputers"
    allowed_domains = ["shwetacomputers.com"]
    start_urls = ["https://shwetacomputers.com/collections/processor?filter.v.price.gte=0&filter.v.price.lte=69699&filter.v.availability=1&sort_by=manual&page=1"]
    custom_settings = {
        'DOWNLOAD_DELAY': 3,
        'ROBOTSTXT_OBEY': False,
        'USER_AGENT': 'Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0',
        'RETRY_HTTP_CODES': [429, 500, 502, 503, 504, 522, 524, 408],
        'RETRY_TIMES': 5,
        'CLOSESPIDER_PAGECOUNT': 30,
    }
    def parse(self, response):
        # Common Shopify product card selectors
        products = response.css('div.product-card, div.grid-view-item, article.product-item, li.product-item')
        
        if not products:
            self.logger.info("No products found, stopping")
            return
        
        for product in products:
            # Try multiple common selectors for name
            name = (product.css('a.product-title::text').get() or
                    product.css('h3.product-title a::text').get() or
                    product.css('h3 a::text').get() or
                    product.css('a.full-unstyled-link::text').get() or
                    product.css('span.text-truncate::text').get() or
                    product.css('div.product-info a::text').get())
            if name:
                name = " ".join(name.split()).strip()
            
            # Link - common Shopify pattern
            relative_url = (product.css('a.full-unstyled-link::attr(href)').get() or
                           product.css('a.product-title::attr(href)').get() or
                           product.css('h3 a::attr(href)').get() or
                           product.css('a.stretched-link::attr(href)').get())
            base_url = "https://shwetacomputers.com"
            link = base_url + relative_url if relative_url else None
            
            # Price - common patterns
            price_text = (product.css('span.price-item--regular::text').get() or
                         product.css('span.price__regular .price-item::text').get() or
                         product.css('span.price-value::text').get() or
                         product.css('span.price-item--sale::text').get() or
                         product.css('div.price__container span::text').get())
            price = None
            if price_text:
                cleaned_price = price_text.replace("Rs.", "").replace("₹", "").replace(",", "").strip()
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
        # Stop if we got very few products (likely last page)
        if len(products) < 6:
            self.logger.info(f"Only {len(products)} products on page {current_page}, likely last page")
            return
        next_page_url = f"https://shwetacomputers.com/collections/processor?filter.v.price.gte=0&filter.v.price.lte=69699&filter.v.availability=1&sort_by=manual&page={next_page}"
        yield scrapy.Request(next_page_url, callback=self.parse, meta={"page": next_page})