from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path

from cas import CasError
from cas.paths import open_dir_chain
from cas.safeio import read_bounded_name, write_atomic


class SafeIoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self._old = os.environ.get("HOME")
        os.environ["HOME"] = str(self.home)

    def tearDown(self) -> None:
        if self._old is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self._old

    def test_atomic_write_mode(self) -> None:
        dirfd = open_dir_chain((".local", "share", "omarchy-cas"), private=True, create=True)
        try:
            write_atomic(dirfd, "note.txt", b"hello", mode=0o600)
            data = read_bounded_name(dirfd, "note.txt", 100, owner_only=True)
            self.assertEqual(data, b"hello")
        finally:
            os.close(dirfd)
        st = os.stat(self.home / ".local" / "share" / "omarchy-cas" / "note.txt")
        self.assertEqual(stat.S_IMODE(st.st_mode), 0o600)

    def test_write_does_not_follow_symlink(self) -> None:
        victim = self.home / "victim"
        victim.write_bytes(b"must survive\n")
        dirfd = open_dir_chain((".local", "share", "omarchy-cas"), private=True, create=True)
        try:
            write_atomic(dirfd, "note.txt", b"first", mode=0o600)
            target = self.home / ".local" / "share" / "omarchy-cas" / "note.txt"
            target.unlink()
            target.symlink_to(victim)
            write_atomic(dirfd, "note.txt", b"second", mode=0o600)
        finally:
            os.close(dirfd)
        self.assertEqual(victim.read_bytes(), b"must survive\n")
        self.assertEqual((self.home / ".local" / "share" / "omarchy-cas" / "note.txt").read_bytes(), b"second")

    def test_read_rejects_oversize(self) -> None:
        dirfd = open_dir_chain((".local", "share", "omarchy-cas"), private=True, create=True)
        try:
            write_atomic(dirfd, "note.txt", b"abcdef", mode=0o600)
            with self.assertRaises(CasError):
                read_bounded_name(dirfd, "note.txt", 3)
        finally:
            os.close(dirfd)


if __name__ == "__main__":
    unittest.main()
