from __future__ import annotations

import unittest

from cas.names import app_token, screenshot_filename, timestamp_slug


class NameTests(unittest.TestCase):
    def test_brave_alias(self) -> None:
        self.assertEqual(app_token("brave-browser"), "brave")

    def test_unknown_class(self) -> None:
        self.assertEqual(app_token("Alacritty"), "alacritty")

    def test_rejects_path_in_class(self) -> None:
        self.assertEqual(app_token("../etc"), "unknown")
        self.assertEqual(app_token(app_token("../etc")), "unknown")

    def test_filename_shape(self) -> None:
        name = screenshot_filename("brave", "2026-09-06_14-22-03")
        self.assertEqual(name, "brave-2026-09-06_14-22-03.png")
        self.assertEqual(
            screenshot_filename("brave", "2026-09-06_14-22-03", 2),
            "brave-2026-09-06_14-22-03-2.png",
        )

    def test_filename_rejects_bad_token(self) -> None:
        with self.assertRaises(ValueError):
            screenshot_filename("..", "2026-09-06_14-22-03")
        with self.assertRaises(ValueError):
            screenshot_filename("brave/../x", "2026-09-06_14-22-03")

    def test_timestamp_slug(self) -> None:
        stamp = timestamp_slug()
        self.assertRegex(stamp, r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}$")


if __name__ == "__main__":
    unittest.main()
