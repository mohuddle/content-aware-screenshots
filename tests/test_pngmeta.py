from __future__ import annotations

import unittest

from cas.pngmeta import embed, parse_text, split_chunks
from pngutil import tiny_png


class PngMetaTests(unittest.TestCase):
    def test_roundtrip(self) -> None:
        blob = tiny_png()
        out = embed(
            blob,
            url="https://x.com/post/1",
            title="a title",
            note="hello note",
            captured_at="2026-09-06T14:22:03-04:00",
        )
        chunks = split_chunks(out)
        meta = parse_text(chunks)
        self.assertEqual(meta.get("Source"), "https://x.com/post/1")
        self.assertEqual(meta.get("URL"), "https://x.com/post/1")
        self.assertEqual(meta.get("Title"), "a title")
        self.assertEqual(meta.get("Comment"), "hello note")
        self.assertTrue(out.startswith(b"\x89PNG"))
        self.assertTrue(any(t == b"IHDR" for t, _ in chunks))
        self.assertEqual(chunks[-1][0], b"IEND")

    def test_replace_existing(self) -> None:
        first = embed(tiny_png(), url="https://a.example/", title="t", note="one", captured_at="t")
        second = embed(first, url="https://b.example/", title="t", note="two", captured_at="t")
        meta = parse_text(split_chunks(second))
        self.assertEqual(meta.get("Source"), "https://b.example/")
        self.assertEqual(meta.get("Comment"), "two")
        self.assertEqual(list(parse_text(split_chunks(second)).values()).count("one"), 0)


if __name__ == "__main__":
    unittest.main()
