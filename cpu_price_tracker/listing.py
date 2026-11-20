"""Read a listing page's own statement of how many products it holds.

MDComputers, Vedant and The IT Depot all print a banner of the form

    Showing 1 to 12 of 53 (5 Pages)

That number is the site's own claim about its catalogue, which makes it the
only trustworthy way to tell a complete scrape from a truncated one. Comparing
scraped rows against a hard-coded number would rot the moment a vendor adds a
CPU; comparing against the site's banner cannot.

Kept free of Scrapy so it can be tested on a plain string.
"""

import re

_SHOWING = re.compile(r"Showing\s+\d+\s+to\s+\d+\s+of\s+([\d,]+)", re.IGNORECASE)
_PAGES = re.compile(r"\((\d+)\s+Pages?\)", re.IGNORECASE)


def parse_showing_total(text):
    """Return ``(total_products, total_pages)``, either of which may be None.

    >>> parse_showing_total("Showing 1 to 12 of 53 (5 Pages)")
    (53, 5)
    """
    if not text:
        return None, None

    total = None
    match = _SHOWING.search(text)
    if match:
        total = int(match.group(1).replace(",", ""))

    pages = None
    match = _PAGES.search(text)
    if match:
        pages = int(match.group(1))

    return total, pages
