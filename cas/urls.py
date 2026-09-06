"""Store-only URL checks. Nothing here fetches or opens the value."""

from __future__ import annotations

from urllib.parse import urlsplit

from cas.bounds import MAX_URL_BYTES


def parse_stored_url(raw: str | None) -> str | None:
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    if text.startswith("-"):
        return None
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in text):
        return None
    encoded = text.encode("utf-8")
    if len(encoded) > MAX_URL_BYTES:
        return None
    try:
        parts = urlsplit(text, allow_fragments=True)
    except ValueError:
        return None
    if parts.scheme not in ("http", "https"):
        return None
    if parts.username is not None or parts.password is not None:
        return None
    host = parts.hostname
    if not host:
        return None
    if "\\" in text or "\n" in text or "\r" in text:
        return None
    return text
