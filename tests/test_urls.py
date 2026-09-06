from __future__ import annotations

import unittest

from cas.urls import parse_stored_url


class UrlTests(unittest.TestCase):
    def test_https_ok(self) -> None:
        self.assertEqual(
            parse_stored_url("https://x.com/user/status/123"),
            "https://x.com/user/status/123",
        )

    def test_rejects_javascript(self) -> None:
        self.assertIsNone(parse_stored_url("javascript:alert(1)"))

    def test_rejects_file(self) -> None:
        self.assertIsNone(parse_stored_url("file:///etc/passwd"))

    def test_rejects_userinfo(self) -> None:
        self.assertIsNone(parse_stored_url("https://evil@example.com/"))

    def test_rejects_leading_dash(self) -> None:
        self.assertIsNone(parse_stored_url("-https://example.com/"))

    def test_rejects_controls(self) -> None:
        self.assertIsNone(parse_stored_url("https://example.com/\nhttps://evil.test"))

    def test_rejects_overlong(self) -> None:
        self.assertIsNone(parse_stored_url("https://example.com/" + ("a" * 4000)))

    def test_empty(self) -> None:
        self.assertIsNone(parse_stored_url("  "))
        self.assertIsNone(parse_stored_url(None))


if __name__ == "__main__":
    unittest.main()
