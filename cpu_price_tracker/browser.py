"""Playwright helpers shared by the spiders.

One lesson, learned at the cost of a whole vendor on 2026-11-19.

``wait_for_selector`` raises on timeout, and scrapy-playwright then throws
the whole response away. That is how a Cloudflare 403 body -- which has no
product tiles -- became a silent "20 second timeout" with the HTTP status
thrown away with it. The status is the only thing that explains a block, so
this helper waits but never raises, and the spider reads ``response.status``
instead.

It also documents the one browser policy that was tried and reverted.

Kept free of Scrapy and Playwright imports at module level so it can be
tested without either.
"""


async def wait_for_selector_or_none(page, selector, timeout=15000, state="attached"):
    """Wait for a selector, but never raise.

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
