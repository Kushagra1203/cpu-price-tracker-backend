import unittest

from cpu_price_tracker.browser import abort_request


class FakeRequest:
    """The two attributes abort_request looks at."""

    def __init__(self, url, resource_type):
        self.url = url
        self.resource_type = resource_type


class AbortRequestTests(unittest.TestCase):
    def test_mdcomputers_keeps_only_the_document(self):
        # The listing is server-rendered: one request is enough, and 90 was
        # what page 1 used to cost.
        self.assertFalse(
            abort_request(
                FakeRequest("https://mdcomputers.in/catalog/processor?page=1", "document")
            )
        )
        self.assertTrue(
            abort_request(
                FakeRequest("https://mdcomputers.in/extension/x/style.css", "stylesheet")
            )
        )
        self.assertTrue(
            abort_request(
                FakeRequest("https://mdcomputers.in/extension/x/app.js", "script")
            )
        )
        self.assertTrue(
            abort_request(FakeRequest("https://mdcomputers.in/image/a.png", "image"))
        )

    def test_other_hosts_keep_their_scripts(self):
        # Elitehubs renders its grid client-side, so its scripts must run.
        self.assertFalse(
            abort_request(
                FakeRequest("https://elitehubs.com/collections/processor", "document")
            )
        )
        self.assertFalse(
            abort_request(
                FakeRequest("https://elitehubs.com/cdn/shop/t/97/app.js", "script")
            )
        )
        self.assertFalse(
            abort_request(
                FakeRequest("https://elitehubs.com/cdn/shop/t/97/style.css", "stylesheet")
            )
        )

    def test_other_hosts_still_drop_images_and_fonts(self):
        self.assertTrue(
            abort_request(
                FakeRequest("https://vishalperipherals.com/cdn/a.webp", "image")
            )
        )
        self.assertTrue(
            abort_request(
                FakeRequest("https://vishalperipherals.com/cdn/a.woff2", "font")
            )
        )
        self.assertTrue(
            abort_request(
                FakeRequest("https://vishalperipherals.com/cdn/a.mp4", "media")
            )
        )

    def test_a_host_that_merely_ends_with_the_same_name_is_not_caught(self):
        # mdcomputers.in must match exactly, not by suffix.
        self.assertFalse(
            abort_request(
                FakeRequest("https://not-mdcomputers.in/catalog/processor", "document")
            )
        )


if __name__ == "__main__":
    unittest.main()
