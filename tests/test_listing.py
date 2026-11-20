import unittest

from cpu_price_tracker.listing import parse_showing_total


class ParseShowingTotalTests(unittest.TestCase):
    def test_it_depot_banner(self):
        self.assertEqual(
            parse_showing_total("Showing 1 to 12 of 53 (5 Pages)"), (53, 5)
        )

    def test_mdcomputers_banner(self):
        self.assertEqual(
            parse_showing_total("Showing 1 to 20 of 62 (4 Pages)"), (62, 4)
        )

    def test_vedant_single_page(self):
        self.assertEqual(
            parse_showing_total("Showing 1 to 41 of 41 (1 Pages)"), (41, 1)
        )

    def test_thousands_separator(self):
        self.assertEqual(
            parse_showing_total("Showing 1 to 20 of 1,234 (62 Pages)"), (1234, 62)
        )

    def test_extra_whitespace_and_lowercase(self):
        self.assertEqual(
            parse_showing_total("showing 1  to  20  of  9  (2 pages)"), (9, 2)
        )

    def test_absent_banner_returns_none(self):
        self.assertEqual(parse_showing_total("<html><body>nothing</body></html>"), (None, None))

    def test_empty_input(self):
        self.assertEqual(parse_showing_total(""), (None, None))
        self.assertEqual(parse_showing_total(None), (None, None))


if __name__ == "__main__":
    unittest.main()
