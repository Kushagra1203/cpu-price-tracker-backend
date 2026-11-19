import scrapy
from cpu_price_tracker.items import CpuPriceTrackerItem

class mdcomputerSpider(scrapy.Spider):
    name = "mdcomputers"
    allowed_domains = ["mdcomputers.in"]
    start_urls = [
        "https://mdcomputers.in/catalog/processor?page=1"
    ]

    def parse(self, response):
        products = response.css("div.product-wrapper")

        for product in products:
            name = product.css("h3.product-entities-title a::text").get()
            link = product.css("h3.product-entities-title a::attr(href)").get()

            price = product.css("span.ins span.amount::text").get()
            if not price:
                price = product.css("span.price span.amount::text").get()

            if price:
                price = price.strip().replace(",", "").replace("₹", "")
                try:
                    price = int(price)
                except ValueError:
                    price = None


            item = CpuPriceTrackerItem()
            item['name'] = name
            item['link'] = link
            item['price'] = price
            item['vendor'] = 'MDComputers'
            yield item

        current_page = response.css("ul.pagination li.active span::text").get()
        if current_page:
            current_page = int(current_page.strip())
            next_page = f"https://mdcomputers.in/catalog/processor?page={current_page + 1}"
            if response.css(f'ul.pagination li a[href*="page={current_page+1}"]'):
                yield response.follow(next_page, callback=self.parse)
