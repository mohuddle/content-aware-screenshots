from __future__ import annotations

import os
import unittest

from cas import CasError
from cas.proc import run_cmd


class ProcTests(unittest.TestCase):
    def setUp(self) -> None:
        uid = os.geteuid()
        os.environ.setdefault("XDG_RUNTIME_DIR", f"/run/user/{uid}")
        os.environ.setdefault("WAYLAND_DISPLAY", os.environ.get("WAYLAND_DISPLAY", "wayland-1"))

    def test_stdout_cap(self) -> None:
        with self.assertRaises(CasError):
            run_cmd(
                ["/usr/bin/head", "-c", "10000", "/dev/zero"],
                timeout=2.0,
                max_stdout=64,
            )

    def test_echo(self) -> None:
        out = run_cmd(["/usr/bin/printf", "ok"], timeout=2.0, max_stdout=16)
        self.assertEqual(out, b"ok")

    def test_rejects_relative_binary(self) -> None:
        with self.assertRaises(CasError):
            run_cmd(["printf", "ok"], timeout=1.0, max_stdout=16)


if __name__ == "__main__":
    unittest.main()
