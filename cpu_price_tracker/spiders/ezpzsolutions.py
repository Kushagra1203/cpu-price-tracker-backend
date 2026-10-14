import scrapy
from cpu_price_tracker.items import CpuPriceTrackerItem

class EzpzsolutionsSpider(scrapy.Spider):
    name = "ezpzsolutions"
    allowed_domains = ["www.ezpzsolutions.in"]
    start_urls = ["https://www.ezpzsolutions.in/processors/page/1/"]
    custom_settings = {
        'CLOSESPIDER_PAGECOUNT': 50,
        'DOWNLOAD_DELAY': 3,
    }

    def parse(self, response):
        products = response.css("div.woocommerce-card__header")
        if not products:
            self.logger.info("No products found, stopping")
            return

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

        # Pagination with stop condition
        next_page = response.css("a.next.page-numbers::attr(href)").get()
        if next_page:
            yield scrapy.Request(next_page, callback=self.parse)
        else:
            self.logger.info("No next page link found, stopping")
            
