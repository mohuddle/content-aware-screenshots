from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path

from cas.paths import open_dir_chain
from cas.store import CaptureRow, open_index


def _row(**kwargs: object) -> CaptureRow:
    base = dict(
        sha256="a" * 64,
        path="/tmp/nope.png",
        captured_at="2026-09-06T14:22:03",
        app_class="brave-browser",
        app_name="brave",
        window_title="hello",
        geometry="0,0 100x100",
        url="https://x.com/p/1",
        page_title="hello",
        note="a note",
        source="clipboard",
    )
    base.update(kwargs)
    return CaptureRow(**base)  # type: ignore[arg-type]


class StoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self._old_home = os.environ.get("HOME")
        os.environ["HOME"] = str(self.home)

    def tearDown(self) -> None:
        if self._old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self._old_home

    def test_upsert_search(self) -> None:
        with open_index() as index:
            index.upsert(_row())
            rows = index.search(query="note")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].url, "https://x.com/p/1")
            found = index.search(url="https://x.com/%")
            self.assertEqual(len(found), 1)
            by_app = index.search(app="brave")
            self.assertEqual(len(by_app), 1)
        st = os.stat(self.home / ".local" / "share" / "omarchy-cas" / "index.sqlite")
        self.assertEqual(stat.S_IMODE(st.st_mode), 0o600)
        dst = os.stat(self.home / ".local" / "share" / "omarchy-cas")
        self.assertEqual(stat.S_IMODE(dst.st_mode), 0o700)

    def test_note_cap_enforced(self) -> None:
        with open_index() as index:
            index.upsert(_row(note="x" * 800, sha256="b" * 64, path="/tmp/b.png"))
            row = index.get("b" * 64)
            assert row is not None
            self.assertEqual(len(row.note), 500)

    def test_rejects_javascript_url(self) -> None:
        with open_index() as index:
            index.upsert(_row(url="javascript:alert(1)", sha256="c" * 64, path="/tmp/c.png"))
            row = index.get("c" * 64)
            assert row is not None
            self.assertIsNone(row.url)
            self.assertEqual(row.source, "none")

    def test_write_replaces_symlink(self) -> None:
        victim = self.home / "victim"
        victim.write_bytes(b"must survive\n")
        with open_index() as index:
            index.upsert(_row())
        db = self.home / ".local" / "share" / "omarchy-cas" / "index.sqlite"
        db.unlink()
        db.symlink_to(victim)
        with self.assertRaises(Exception):
            with open_index() as index:
                index.upsert(_row(sha256="d" * 64, path="/tmp/d.png"))
        self.assertEqual(victim.read_bytes(), b"must survive\n")

    def test_dirfd_chain_refuses_dotdot(self) -> None:
        with self.assertRaises(Exception):
            open_dir_chain(("..",), private=True, create=False)


if __name__ == "__main__":
    unittest.main()
