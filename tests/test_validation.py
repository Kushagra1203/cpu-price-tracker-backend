import unittest

from cpu_price_tracker.validation import check_vendor_counts, vendor_counts


class VendorCountsTests(unittest.TestCase):
    def test_counts_rows_per_vendor(self):
        items = [
            {"vendor": "PC Studio"},
            {"vendor": "PC Studio"},
            {"vendor": "MDComputers"},
        ]

        self.assertEqual(vendor_counts(items), {"PC Studio": 2, "MDComputers": 1})

    def test_rows_without_a_vendor_are_ignored(self):
        self.assertEqual(vendor_counts([{"name": "x"}, {"vendor": None}]), {})


class CheckVendorCountsTests(unittest.TestCase):
    def test_a_healthy_run_has_no_problems(self):
        current = {"PC Studio": 67, "MDComputers": 64}
        previous = {"PC Studio": 65, "MDComputers": 70}

        self.assertEqual(check_vendor_counts(current, previous), [])

    def test_a_vendor_below_the_absolute_floor_is_flagged(self):
        # This is the elitehubs case: zero rows, run otherwise "succeeds".
        problems = check_vendor_counts({"Elitehubs": 0})

        self.assertEqual(len(problems), 1)
        self.assertIn("Elitehubs", problems[0])
        self.assertIn("below the floor", problems[0])

    def test_a_vendor_that_loses_most_of_its_catalogue_is_flagged(self):
        problems = check_vendor_counts({"MDComputers": 20}, {"MDComputers": 64})

        self.assertEqual(len(problems), 1)
        self.assertIn("down from 64", problems[0])
        self.assertIn("31%", problems[0])

    def test_a_moderate_drop_is_tolerated(self):
        # 50 of 64 is a 22% drop: noisy day, not a broken spider.
        self.assertEqual(check_vendor_counts({"MDComputers": 50}, {"MDComputers": 64}), [])

    def test_an_expected_vendor_missing_entirely_is_flagged(self):
        problems = check_vendor_counts(
            {"PC Studio": 67}, previous={"PC Studio": 67}, expected=["PC Studio", "Elitehubs"]
        )

        self.assertEqual(len(problems), 1)
        self.assertIn("Elitehubs", problems[0])
        self.assertIn("missing", problems[0])

    def test_first_run_with_no_history_only_checks_the_floor(self):
        self.assertEqual(check_vendor_counts({"PC Studio": 67}, {}), [])

    def test_a_new_vendor_without_history_is_not_flagged(self):
        problems = check_vendor_counts({"New Shop": 12}, {"PC Studio": 67})

        self.assertEqual(problems, [])

    def test_previous_run_with_zero_rows_does_not_divide_by_zero(self):
        self.assertEqual(check_vendor_counts({"MDComputers": 40}, {"MDComputers": 0}), [])


if __name__ == "__main__":
    unittest.main()
