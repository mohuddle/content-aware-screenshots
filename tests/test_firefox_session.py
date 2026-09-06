from __future__ import annotations

import json
import os
import tempfile
import unittest

from cas.browsers import FIREFOX
from cas.firefox_session import (
    active_tab_url,
    decode_mozlz4,
    parse_session_json,
    wrap_mozlz4,
)


def _store(url: str, title: str, *, selected_window: int = 1) -> bytes:
    payload = {
        "selectedWindow": selected_window,
        "windows": [
            {
                "selected": 1,
                "tabs": [
                    {
                        "index": 1,
                        "entries": [{"url": url, "title": title}],
                    }
                ],
            }
        ],
    }
    return json.dumps(payload).encode()


class FirefoxSessionTests(unittest.TestCase):
    def test_json_selected_https(self) -> None:
        raw = _store("https://example.com/app", "Example")
        self.assertEqual(parse_session_json(raw), "https://example.com/app")

    def test_rejects_javascript(self) -> None:
        raw = _store("javascript:alert(1)", "x")
        self.assertIsNone(parse_session_json(raw))

    def test_title_picks_window(self) -> None:
        payload = {
            "selectedWindow": 1,
            "windows": [
                {
                    "selected": 1,
                    "tabs": [
                        {
                            "index": 1,
                            "entries": [{"url": "https://a.example/one", "title": "Alpha"}],
                        }
                    ],
                },
                {
                    "selected": 1,
                    "tabs": [
                        {
                            "index": 1,
                            "entries": [{"url": "https://b.example/two", "title": "Beta"}],
                        }
                    ],
                },
            ],
        }
        raw = json.dumps(payload).encode()
        self.assertEqual(
            parse_session_json(raw, window_title="Beta - Firefox"),
            "https://b.example/two",
        )

    def test_mozlz4_roundtrip(self) -> None:
        raw = _store("https://example.com/lz4", "Lz4")
        blob = wrap_mozlz4(raw)
        self.assertTrue(blob.startswith(b"mozLz40\0"))
        plain = decode_mozlz4(blob)
        self.assertEqual(plain, raw)
        self.assertEqual(parse_session_json(plain), "https://example.com/lz4")

    def test_missing_profile_is_none(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        old = os.environ.get("HOME")
        os.environ["HOME"] = tmp.name
        try:
            self.assertIsNone(active_tab_url(root_parts=FIREFOX.root_parts))
        finally:
            if old is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old


if __name__ == "__main__":
    unittest.main()
