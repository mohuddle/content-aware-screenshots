from __future__ import annotations

import unittest

from cas.browsers import BRAVE, CHROME, CHROMIUM, FIREFOX, identify_class, identify_token


class BrowserIdentifyTests(unittest.TestCase):
    def test_exact_classes(self) -> None:
        self.assertEqual(identify_class("brave-browser"), BRAVE)
        self.assertEqual(identify_class("chromium"), CHROMIUM)
        self.assertEqual(identify_class("google-chrome"), CHROME)
        self.assertEqual(identify_class("firefox"), FIREFOX)
        self.assertEqual(identify_class("org.mozilla.firefox"), FIREFOX)

    def test_prefix_classes(self) -> None:
        self.assertEqual(identify_class("brave-browser-nightly"), BRAVE)
        self.assertEqual(identify_class("google-chrome-unstable"), CHROME)

    def test_unknown(self) -> None:
        self.assertIsNone(identify_class("Alacritty"))
        self.assertIsNone(identify_class("org.gnome.epiphany"))

    def test_tokens(self) -> None:
        self.assertEqual(identify_token("brave"), BRAVE)
        self.assertEqual(identify_token("chrome"), CHROME)
        self.assertEqual(identify_token("firefox"), FIREFOX)
        self.assertIsNone(identify_token("foot"))


if __name__ == "__main__":
    unittest.main()
