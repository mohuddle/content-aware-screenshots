from __future__ import annotations

import os
import tempfile
import unittest

from cas.chromium_session import parse_active_tab_url


def _i32(n: int) -> bytes:
    return int(n).to_bytes(4, "little", signed=True)


def _u32(n: int) -> bytes:
    return int(n).to_bytes(4, "little", signed=False)


def _pad(buf: bytes) -> bytes:
    return buf + (b"\x00" * ((4 - (len(buf) % 4)) % 4))


def _pstr(s: str) -> bytes:
    raw = s.encode("utf-8")
    return _pad(_u32(len(raw)) + raw)


def _pstr16(s: str) -> bytes:
    raw = s.encode("utf-16le")
    return _pad(_u32(len(s)) + raw)


def _pickle(*chunks: bytes) -> bytes:
    payload = b"".join(chunks)
    return _u32(len(payload)) + payload


def _cmd(cid: int, payload: bytes) -> bytes:
    body = bytes([cid]) + payload
    return len(body).to_bytes(2, "little") + body


def _snss(*commands: bytes) -> bytes:
    return b"SNSS" + _u32(3) + b"".join(commands)


def _nav(tab: int, index: int, url: str, title: str) -> bytes:
    return _cmd(6, _pickle(_i32(tab), _i32(index), _pstr(url), _pstr16(title)))


def _session(*, win: int = 1, tab: int = 10, vis: int = 0, url: str, title: str, nav: int = 0) -> bytes:
    return _snss(
        _cmd(0, _i32(win) + _i32(tab)),
        _cmd(2, _i32(tab) + _i32(vis)),
        _nav(tab, nav, url, title),
        _cmd(7, _i32(tab) + _i32(nav)),
        _cmd(8, _i32(win) + _i32(vis)),
    )


class BraveSessionTests(unittest.TestCase):
    def test_selected_https_url(self) -> None:
        blob = _session(
            url="https://gemini.google.com/app/b598f5bcd496f053",
            title="Google Gemini",
        )
        self.assertEqual(
            parse_active_tab_url(blob),
            "https://gemini.google.com/app/b598f5bcd496f053",
        )

    def test_rejects_javascript(self) -> None:
        blob = _session(url="javascript:alert(1)", title="x")
        self.assertIsNone(parse_active_tab_url(blob))

    def test_title_picks_matching_window(self) -> None:
        blob = _snss(
            _cmd(0, _i32(1) + _i32(10)),
            _cmd(2, _i32(10) + _i32(0)),
            _nav(10, 0, "https://a.example/one", "Alpha"),
            _cmd(7, _i32(10) + _i32(0)),
            _cmd(8, _i32(1) + _i32(0)),
            _cmd(0, _i32(2) + _i32(20)),
            _cmd(2, _i32(20) + _i32(0)),
            _nav(20, 0, "https://b.example/two", "Beta"),
            _cmd(7, _i32(20) + _i32(0)),
            _cmd(8, _i32(2) + _i32(0)),
        )
        self.assertEqual(
            parse_active_tab_url(blob, window_title="Beta - Brave"),
            "https://b.example/two",
        )
        self.assertEqual(
            parse_active_tab_url(blob, window_title="Alpha - Brave"),
            "https://a.example/one",
        )

    def test_last_selected_window_without_title(self) -> None:
        blob = _snss(
            _cmd(0, _i32(1) + _i32(10)),
            _cmd(2, _i32(10) + _i32(0)),
            _nav(10, 0, "https://a.example/one", "Alpha"),
            _cmd(8, _i32(1) + _i32(0)),
            _cmd(0, _i32(2) + _i32(20)),
            _cmd(2, _i32(20) + _i32(0)),
            _nav(20, 0, "https://b.example/two", "Beta"),
            _cmd(8, _i32(2) + _i32(0)),
        )
        self.assertEqual(parse_active_tab_url(blob), "https://b.example/two")

    def test_garbage_is_none(self) -> None:
        self.assertIsNone(parse_active_tab_url(b"not snss"))
        self.assertIsNone(parse_active_tab_url(b"SNSS" + _u32(3)))

    def test_missing_profile_is_none(self) -> None:
        from cas.chromium_session import active_tab_url
        from cas.browsers import BRAVE

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        old = os.environ.get("HOME")
        os.environ["HOME"] = tmp.name
        try:
            self.assertIsNone(active_tab_url(root_parts=BRAVE.root_parts))
        finally:
            if old is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old


if __name__ == "__main__":
    unittest.main()
