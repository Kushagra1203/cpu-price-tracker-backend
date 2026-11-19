"""How the Playwright spiders talk to a site.

Two things happen in a browser page load that do not happen in a plain HTTP
request, and both of them cost rows on this project's vendors.

**The browser is made to impersonate something it is not.** By default
scrapy-playwright copies Scrapy's request headers onto the navigation
request, so a Chromium 139 was announcing itself as Firefox 128 with
Scrapy's narrow ``Accept`` and ``Accept-Encoding`` headers. A WAF that
compares the ``User-Agent`` against the TLS fingerprint sees a browser
whose fingerprint contradicts its own header, and a plain
``Accept-Encoding: gzip, deflate`` is not something Chromium would send.
On 2026-11-19 MDComputers answered page 1 with 200 and then answered
page 2 with 403 in 0.2 s, from the same browser, in the same session.
The fix is to let the browser send its own headers: see
``PLAYWRIGHT_PROCESS_REQUEST_HEADERS = None`` in settings.py.

**A page load is a hundred requests.** One MDComputers listing page pulls
30 scripts, 20 stylesheets, 40 images and 5 fonts from the same host --
90 requests for 20 products. Cloudflare's error page (``cf.errors.css``,
``cf-no-screenshot-error.png``, no ``challenge-platform``) is a WAF rule,
not a JavaScript challenge, so nothing on that page needs a script to be
read. The rules below cut the volume where the data allows it.

Kept free of Scrapy and Playwright imports at module level so it can be
tested without either.
"""

from urllib.parse import urlsplit

# Listing pages that are server-rendered: the products and the site's own
# count are already in the initial HTML, so nothing but the document is
# needed.
#
# Verified on 2026-11-19 by fetching the page without a browser at all: the
# response carried 20 product titles, 20 "product-wrapper" blocks inside
# the listing grid, and the banner "Showing 1 to 20 of 62 (4 Pages)".
# It also carried a 21st "product-wrapper" outside the grid -- a hidden
# template -- which is what made Playwright's default wait-for-visible
# time out on a page that had loaded perfectly.
DOCUMENT_ONLY_HOSTS = {"mdcomputers.in"}

# Assets no spider reads. Dropping these is safe everywhere and cuts the
# heaviest pages down: Elitehubs made 290 requests in one run and Vishal
# 808, nearly all of them images and stylesheets.
HEAVY_ASSET_TYPES = {"image", "font", "media"}


def abort_request(request):
    """Return True to stop a browser request before it is sent.

    Wired in through the ``PLAYWRIGHT_ABORT_REQUEST`` setting, which
    scrapy-playwright calls with the Playwright request object.
    """
    host = urlsplit(request.url).hostname or ""

    if host in DOCUMENT_ONLY_HOSTS:
        # Keep the document; every other request is decoration.
        return request.resource_type != "document"

    return request.resource_type in HEAVY_ASSET_TYPES


async def wait_for_selector_or_none(page, selector, timeout=15000, state="attached"):
    """Wait for a selector, but never raise.

    Playwright's ``wait_for_selector`` raises on timeout, and scrapy-playwright
    then throws the whole response away. That is how a Cloudflare 403 body --
    which has no product tiles -- became a silent "20 second timeout" with
    the HTTP status thrown away with it. The status is the only thing that
    explains a block, so it is worth keeping.

    Returns True if the selector appeared, False if it did not.
    """
    # Imported here so this module can be imported without Playwright
    # installed, which keeps it testable.
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError

    try:
        await page.wait_for_selector(selector, state=state, timeout=timeout)
    except PlaywrightTimeoutError:
        return False
    return True
