# Scrapy settings for cpu_price_tracker project
#
# For simplicity, this file contains only settings considered important or
# commonly used. You can find more settings consulting the documentation:
#
#     https://docs.scrapy.org/en/latest/topics/settings.html
#     https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#     https://docs.scrapy.org/en/latest/topics/spider-middleware.html

BOT_NAME = "cpu_price_tracker"

SPIDER_MODULES = ["cpu_price_tracker.spiders"]
NEWSPIDER_MODULE = "cpu_price_tracker.spiders"


# Crawl responsibly by identifying yourself (and your website) on the user-agent
# Use a browser UA: some vendors (e.g. mdcomputers) 403 the default Scrapy UA
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"

# ITEM_PIPELINES = {
#     'cpu_price_tracker.pipelines.MySQLPipeline': 300,
# }

# Obey robots.txt rules
ROBOTSTXT_OBEY = False

# Configure maximum concurrent requests performed by Scrapy (default: 16)
#CONCURRENT_REQUESTS = 32

# Configure a delay for requests for the same website (default: 0)
# See https://docs.scrapy.org/en/latest/topics/settings.html#download-delay
# See also autothrottle settings and docs
#DOWNLOAD_DELAY = 3
# The download delay setting will honor only one of:
#CONCURRENT_REQUESTS_PER_DOMAIN = 16
#CONCURRENT_REQUESTS_PER_IP = 16

# Disable cookies (enabled by default)
#COOKIES_ENABLED = False

# Disable Telnet Console (enabled by default)
#TELNETCONSOLE_ENABLED = False

# Override the default request headers:
#DEFAULT_REQUEST_HEADERS = {
#    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
#    "Accept-Language": "en",
#}

# Enable or disable spider middlewares
# See https://docs.scrapy.org/en/latest/topics/spider-middleware.html
#SPIDER_MIDDLEWARES = {
#    "cpu_price_tracker.middlewares.CpuPriceTrackerSpiderMiddleware": 543,
#}

# Enable or disable downloader middlewares
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#DOWNLOADER_MIDDLEWARES = {
#    "cpu_price_tracker.middlewares.CpuPriceTrackerDownloaderMiddleware": 543,
#}

# Enable or disable extensions
# See https://docs.scrapy.org/en/latest/topics/extensions.html
#EXTENSIONS = {
#    "scrapy.extensions.telnet.TelnetConsole": None,
#}

# Configure item pipelines
# See https://docs.scrapy.org/en/latest/topics/item-pipeline.html
#ITEM_PIPELINES = {
#    "cpu_price_tracker.pipelines.CpuPriceTrackerPipeline": 300,
#}

# Enable and configure the AutoThrottle extension (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/autothrottle.html
#AUTOTHROTTLE_ENABLED = True
# The initial download delay
#AUTOTHROTTLE_START_DELAY = 5
# The maximum download delay to be set in case of high latencies
#AUTOTHROTTLE_MAX_DELAY = 60
# The average number of requests Scrapy should be sending in parallel to
# each remote server
#AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0
# Enable showing throttling stats for every response received:
#AUTOTHROTTLE_DEBUG = False

# Enable and configure HTTP caching (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html#httpcache-middleware-settings
#HTTPCACHE_ENABLED = True
#HTTPCACHE_EXPIRATION_SECS = 0
#HTTPCACHE_DIR = "httpcache"
#HTTPCACHE_IGNORE_HTTP_CODES = []
#HTTPCACHE_STORAGE = "scrapy.extensions.httpcache.FilesystemCacheStorage"

# Set settings whose default value is deprecated to a future-proof value
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
# FEED_FORMAT = "json"
# FEED_URI = "cpu_price_tracker/data/<spider_name>.json"
FEED_EXPORT_ENCODING = "utf-8"

# Configure Scrapy-Playwright
DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}

TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
# Playwright launch options
# channel="chromium" forces the full Chromium build instead of the stripped
# chromium-headless-shell, so a single browser build serves both headless and
# headful runs (and saves ~270 MB in ~/.cache/ms-playwright).
PLAYWRIGHT_LAUNCH_OPTIONS = {
    "headless": True,
    "channel": "chromium",
    "args": ["--no-sandbox", "--disable-dev-shm-usage"],
}

# Never wait forever. Without this, a page whose load event never fires
# hangs the spider for the whole job.
PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT = 30000

# Two browser policies were tried on 2026-11-19 and both are recorded here so
# they are not retried on a hunch.
#
# PLAYWRIGHT_PROCESS_REQUEST_HEADERS = None -- let the browser send its own
# headers instead of Scrapy's (a Chromium 139 announcing itself as Firefox
# 128). Reverted: it was changed in the same run as the policy below, so the
# run could not say which of the two caused what, and the known-good state
# is the default.
#
# PLAYWRIGHT_ABORT_REQUEST = "cpu_price_tracker.browser.abort_request" --
# stop the browser fetching assets no spider reads. One MDComputers listing
# page pulls 90 requests for 20 products, which reads as waste, and the
# first attempt dropped everything but the document on that host. It took
# MDComputers from 23 rows to 0: the 403 page Cloudflare serves carries
# cdn-cgi/challenge-platform/scripts/jsd/main.js, its JavaScript bot
# detection, and that spider had blocked every script on the host. Cloudflare
# runs that script on every page it serves, blocked or not, and a page with
# no JavaScript signals at all scores as a bot.

# Other settings
DOWNLOAD_DELAY = 3
COOKIES_ENABLED = True
RETRY_ENABLED = True
RETRY_TIMES = 3

# 429 is an explicit "you are going too fast", not a transient error. elitehubs
# answers with `429 local_rate_limited` and `Retry-After: 60` from Cloudflare
# when the request rate is too high, which used to yield an empty result set
# that the pipeline recorded as a successful run.
RETRY_HTTP_CODES = [408, 429, 500, 502, 503, 504, 522, 524]

# Throttle automatically instead of hammering a vendor into a rate limit.
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 5
AUTOTHROTTLE_MAX_DELAY = 60
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0

# Scrapy has no per-request download delay -- request.meta["download_delay"]
# is not read by the downloader -- but it does have per-slot settings, and a
# request chooses its slot with request.meta["download_slot"]. MDComputers
# gets a slow, strictly serial slot of its own: page 1 was answered 200 and
# page 2 was refused with 403 in 0.2 s from the same browser session on
# 2026-11-19, so the site's WAF does not like its request pattern, and a
# refused page is asked again after the same 30 s rather than ending the
# crawl.
DOWNLOAD_SLOTS = {
    "md-slow": {"concurrency": 1, "delay": 30},
}
