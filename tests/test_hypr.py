from __future__ import annotations

import unittest

from cas import CasError
from cas.hypr import Snapshot, WindowInfo, match_region, parse_geometry


class HyprTests(unittest.TestCase):
    def test_parse_geometry(self) -> None:
        self.assertEqual(parse_geometry("10,20 300x200"), (10, 20, 300, 200))
        self.assertEqual(parse_geometry("-12,40 100x50"), (-12, 40, 100, 50))

    def test_rejects_injection_geometry(self) -> None:
        with self.assertRaises(CasError):
            parse_geometry("0,0 1x1; rm -rf /")
        with self.assertRaises(CasError):
            parse_geometry("")

    def test_match_largest_overlap(self) -> None:
        brave = WindowInfo("brave-browser", "post - Brave", 0, 0, 800, 600, True)
        term = WindowInfo("Alacritty", "zsh", 800, 0, 800, 600, False)
        snap = Snapshot(focused=brave, clients=(brave, term), cursor=(10, 10))
        matched = match_region("10,10 100x100", snap)
        self.assertEqual(matched.cls, "brave-browser")
        self.assertTrue(matched.is_browser())
        other = match_region("850,10 100x100", snap)
        self.assertEqual(other.cls, "Alacritty")
        self.assertFalse(other.is_browser())


if __name__ == "__main__":
    unittest.main()
