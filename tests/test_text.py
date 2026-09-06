from __future__ import annotations

import unittest

from cas.bounds import MAX_NOTE_CHARS
from cas.text import clean_note, plain


class TextTests(unittest.TestCase):
    def test_strips_markup(self) -> None:
        self.assertEqual(clean_note("<img src=x>hello"), "img src=xhello")
        self.assertEqual(plain("<b>x</b>", 20), "bx/b")

    def test_note_cap(self) -> None:
        note = clean_note("a" * (MAX_NOTE_CHARS + 50))
        self.assertEqual(len(note), MAX_NOTE_CHARS)

    def test_strips_bidi(self) -> None:
        self.assertEqual(clean_note("ab\u202ecdef"), "abcdef")


if __name__ == "__main__":
    unittest.main()
