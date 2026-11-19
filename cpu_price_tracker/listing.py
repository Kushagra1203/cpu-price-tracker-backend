"""Read a listing page's own statement of how many products it holds.

MDComputers, Vedant and The IT Depot all print a banner of the form

    Showing 1 to 12 of 53 (5 Pages)

Somewhere in the page. That number is the site's own claim about its
catalogue, which makes it the only trustworthy way to tell a complete scrape
from a truncated one. Comparing scraped rows against a hard-coded number would
rot the moment a vendor adds a CPU; comparing against the site's banner cannot.

Kept free of Scrapy so it can be tested on a plain string.
"""

import re

_SHOWING = re.compile(r"Showing\s+(\d+)\s+to\s+(\d+)\s+of\s+([\d,]+)", re.IGNORECASE)
_PAGES = re.compile(r"\((\d+)\s+Pages?\)", re.IGNORECASE)


def parse_showing_range(text):
    """Return ``(first, last, total_products, total_pages)``.

    The banner states the range this page shows as well as the catalogue
    total, so it can say that page 2 must contain 40 products and not just
    that there are 62 altogether::

        >>> parse_showing_range("Showing 1 to 12 of 53 (5 Pages)")
        (1, 12, 53, 5)

    Any element may be ``None`` when the banner is absent or partial.
    """
    if not text:
        return None, None, None, None

    first = last = total = None
    pages = None

    match = _SHOWING.search(text)
    if match:
        first = int(match.group(1))
        last = int(match.group(2))
        total = int(match.group(3).replace(",", ""))

    match = _PAGES.search(text)
    if match:
        pages = int(match.group(1))

    return first, last, total, pages


def parse_showing_total(text):
    """Return ``(total_products, total_pages)``, either of which may be None.

    >>> parse_showing_total("Showing 1 to 12 of 53 (5 Pages)")
    (53, 5)
    """
    _, _, total, pages = parse_showing_range(text)
    return total, pages
