import json
import os
import tempfile
import unittest

from cpu_price_tracker.normalize_cpu_names import standardize_cpu_names


DICTIONARY = {"amd ryzen 5 5600": {"cores": 6, "threads": 12, "series": "Ryzen 5"}}


class StandardizeCpuNamesTests(unittest.TestCase):
    def run_pipeline(self, items, dictionary=None):
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "processors.json")
            matched = os.path.join(tmp, "standardized.json")
            unmatched = os.path.join(tmp, "unmatched.json")

            with open(source, "w", encoding="utf-8") as f:
                json.dump(items, f)

            standardize_cpu_names(source, matched, unmatched, dictionary or {})

            with open(matched, "r", encoding="utf-8") as f:
                matched_items = json.load(f)
            with open(unmatched, "r", encoding="utf-8") as f:
                unmatched_items = json.load(f)
            return matched_items, unmatched_items

    def test_a_null_name_is_skipped_instead_of_crashing(self):
        # The 2026-11-19 run died here: a spider yielded {"name": None}, and
        # `item.get("name", "")` does not help because the key exists with a
        # null value. One bad row must not abort the whole pipeline.
        items = [{"name": None, "vendor": "PC Studio", "link": "https://x/1"}]

        matched, unmatched = self.run_pipeline(items)

        self.assertEqual(matched, [])
        self.assertEqual(unmatched, [])

    def test_an_absent_name_is_skipped(self):
        items = [{"vendor": "PC Studio", "link": "https://x/2"}]

        matched, unmatched = self.run_pipeline(items)

        self.assertEqual(matched, [])
        self.assertEqual(unmatched, [])

    def test_blank_names_are_skipped(self):
        items = [
            {"name": "", "link": "https://x/3"},
            {"name": "   ", "link": "https://x/4"},
        ]

        matched, unmatched = self.run_pipeline(items)

        self.assertEqual(matched, [])
        self.assertEqual(unmatched, [])

    def test_a_bad_row_does_not_discard_the_good_ones(self):
        items = [
            {"name": None, "vendor": "Vendor A", "link": "https://x/bad"},
            {"name": "AMD Ryzen 5 5600", "vendor": "Vendor B", "link": "https://x/good"},
            {"name": "Some Unknown CPU", "vendor": "Vendor C", "link": "https://x/unknown"},
        ]

        matched, unmatched = self.run_pipeline(items, DICTIONARY)

        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["standard_name"], "amd ryzen 5 5600")
        self.assertEqual(matched[0]["cores"], 6)
        self.assertEqual(len(unmatched), 1)
        self.assertEqual(unmatched[0]["name"], "Some Unknown CPU")


if __name__ == "__main__":
    unittest.main()
