import asyncio
import importlib.util
import unittest

from cpu_price_tracker.browser import wait_for_selector_or_none

PLAYWRIGHT_AVAILABLE = importlib.util.find_spec("playwright") is not None


class FakePage:
    """Just enough of a Playwright page to exercise the helper."""

    def __init__(self, behaviour):
        self.behaviour = behaviour
        self.calls = []

    async def wait_for_selector(self, selector, state=None, timeout=None):
        self.calls.append((selector, state, timeout))
        if self.behaviour == "timeout":
            from playwright.async_api import TimeoutError

            raise TimeoutError("Timeout 15000ms exceeded.")
        return None


@unittest.skipUnless(
    PLAYWRIGHT_AVAILABLE,
    "playwright is not installed; the helper imports it lazily",
)
class WaitForSelectorOrNoneTests(unittest.TestCase):
    def test_returns_true_when_the_selector_appears(self):
        page = FakePage("found")

        async def run():
            return await wait_for_selector_or_none(page, "div.product-wrapper")

        self.assertTrue(asyncio.run(run()))
        self.assertEqual(page.calls, [("div.product-wrapper", "attached", 15000)])

    def test_returns_false_instead_of_raising_on_timeout(self):
        # This is the whole point of the helper: a raising wait makes
        # scrapy-playwright discard the response, and with it the HTTP status
        # that explains a block.
        page = FakePage("timeout")

        async def run():
            return await wait_for_selector_or_none(page, "div.product-wrapper")

        self.assertFalse(asyncio.run(run()))

    def test_waits_for_attached_not_visible(self):
        # A hidden template tile is attached but never visible, and waiting
        # for visible times out on a page that loaded perfectly.
        page = FakePage("found")

        async def run():
            return await wait_for_selector_or_none(page, "div.x")

        asyncio.run(run())
        self.assertEqual(page.calls[0][1], "attached")


if __name__ == "__main__":
    unittest.main()
