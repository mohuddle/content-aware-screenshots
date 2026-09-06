"""Strip markup and controls before notes, notifications, or stored titles."""

from __future__ import annotations

from cas.bounds import MAX_NOTE_BYTES, MAX_NOTE_CHARS, MAX_STDERR

_BIDI = frozenset(
    {
        0x202A,
        0x202B,
        0x202C,
        0x202D,
        0x202E,
        0x2066,
        0x2067,
        0x2068,
        0x2069,
        0x200B,
        0x200C,
        0x200D,
        0xFEFF,
    }
)


def is_unsafe_char(ch: str) -> bool:
    o = ord(ch)
    if o < 32 and ch not in "\t\n":
        return True
    if 0x7F <= o <= 0x9F:
        return True
    return o in _BIDI


def plain(text: str, max_chars: int) -> str:
    out: list[str] = []
    for ch in text:
        if ch in "<>&" or is_unsafe_char(ch):
            if ch in "\t\n":
                continue
            continue
        out.append(ch)
        if len(out) >= max_chars:
            break
    return "".join(out)


def clean_note(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    for line in text.split("\n"):
        cleaned = "".join(ch for ch in line if not is_unsafe_char(ch) and ch not in "<>&")
        lines.append(cleaned)
    joined = "\n".join(lines).strip()
    if len(joined) > MAX_NOTE_CHARS:
        joined = joined[:MAX_NOTE_CHARS]
    encoded = joined.encode("utf-8")
    if len(encoded) > MAX_NOTE_BYTES:
        joined = encoded[:MAX_NOTE_BYTES].decode("utf-8", "ignore").strip()
        if len(joined) > MAX_NOTE_CHARS:
            joined = joined[:MAX_NOTE_CHARS]
    return joined


def clean_title(text: str, max_chars: int) -> str:
    return plain(text.replace("\n", " ").replace("\r", " "), max_chars)


def stderr_msg(message: str) -> str:
    return plain(str(message), MAX_STDERR)
