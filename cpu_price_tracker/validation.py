"""Health checks for a scrape run.

A vendor that returns nothing is a failure, not a quiet day. This was learned
the hard way: elitehubs started answering HTTP 429 (Cloudflare
"local_rate_limited") and contributed zero rows for weeks while the run still
logged "Data inserted successfully", because an empty spider result is
indistinguishable from a successful one at the process level.

Two checks, both cheap:

* an absolute floor, so a vendor that returns nothing is always wrong;
* a comparison against the previous run, so a vendor that loses most of its
  catalogue is caught even though it still returns something.

Kept free of Scrapy and MySQL so it can be tested without either.
"""

# Below this many rows a vendor count is treated as broken outright.
MIN_ROWS_PER_VENDOR = 3

# A vendor must keep at least this share of its previous run's rows.
MIN_FRACTION_OF_PREVIOUS = 0.6

# Vendors expected to run, used to catch a spider that disappears entirely
# rather than merely returning few rows.
# Vendors the scheduled runner must see. PC Studio is deliberately absent: its
# only two runs from the runner returned HTTP 403 from Cloudflare in well under
# a second (a block on the runner's IP, not a parser problem), while the same
# spider still returns 67 rows from a home connection. Leaving it here would
# make the job fail every single night until a proxy is added, which trains you
# to ignore the one check that catches real breakage.
EXPECTED_VENDORS = [
    "Elitehubs",
    "The IT Depot",
    "MDComputers",
    "Vedant Computers",
    "Vishal Peripherals",
    "Ezpz Solutions",
]


def vendor_counts(items):
    """Count rows per vendor for a list of scraped items."""
    counts = {}
    for item in items:
        vendor = item.get("vendor")
        if not vendor:
            continue
        counts[vendor] = counts.get(vendor, 0) + 1
    return counts


def check_vendor_counts(
    current,
    previous=None,
    expected=None,
    min_rows=MIN_ROWS_PER_VENDOR,
    fraction=MIN_FRACTION_OF_PREVIOUS,
):
    """Return a list of problems; an empty list means the run looks healthy.

    ``current``  : {vendor: row_count} for this run
    ``previous`` : {vendor: row_count} for the last good run (optional)
    ``expected`` : vendors that should always appear (optional)
    """
    previous = previous or {}
    problems = []

    for vendor in expected or ():
        if vendor not in current:
            problems.append(f"{vendor}: missing from this run entirely")

    for vendor in sorted(current):
        count = current[vendor]

        if count < min_rows:
            problems.append(
                f"{vendor}: only {count} row(s), below the floor of {min_rows}"
            )
            continue

        was = previous.get(vendor)
        if was and count < was * fraction:
            share = 100.0 * count / was
            problems.append(
                f"{vendor}: {count} rows, down from {was} last run ({share:.0f}%)"
            )

    return problems
