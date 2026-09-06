"""Filename and app-token rules. Reject separators instead of repairing them."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from cas.bounds import MAX_APP_TOKEN, MAX_CLASS, MAX_FILENAME

_CLASS_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_TOKEN_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_STAMP_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{2}-[0-9]{2}-[0-9]{2}$")

CLASS_ALIASES = {
    "brave-browser": "brave",
    "brave-browser-beta": "brave",
    "brave-browser-nightly": "brave",
    "google-chrome": "chrome",
    "google-chrome-beta": "chrome",
    "org.mozilla.firefox": "firefox",
    "org.chromium.chromium": "chromium",
    "com.brave.browser": "brave",
    "microsoft-edge": "edge",
    "org.omarchy.agent": "agent",
    "org.gnome.naultilus": "files",
    "org.gnome.nautilus": "files",
    "alacritty": "alacritty",
    "foot": "foot",
    "kitty": "kitty",
    "com.mitchellh.ghostty": "ghostty",
}


def sanitize_class(raw: str) -> str:
    text = raw.strip()[:MAX_CLASS]
    if not _CLASS_RE.fullmatch(text):
        return "unknown"
    return text


def app_token(class_name: str) -> str:
    lowered = sanitize_class(class_name).lower()
    if lowered in CLASS_ALIASES:
        token = CLASS_ALIASES[lowered]
    else:
        # Keep the last dotted component (org.foo.Bar -> bar).
        piece = lowered.rsplit(".", 1)[-1]
        chars: list[str] = []
        prev_dash = False
        for ch in piece:
            if ch.isalnum():
                chars.append(ch)
                prev_dash = False
            elif not prev_dash and chars:
                chars.append("-")
                prev_dash = True
        token = "".join(chars).strip("-") or "app"
    if len(token) > MAX_APP_TOKEN:
        token = token[:MAX_APP_TOKEN].rstrip("-")
    if not _TOKEN_RE.fullmatch(token):
        return "app"
    return token


def timestamp_slug(when: datetime | None = None) -> str:
    now = when or datetime.now().astimezone()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc).astimezone()
    stamp = now.strftime("%Y-%m-%d_%H-%M-%S")
    if not _STAMP_RE.fullmatch(stamp):
        raise RuntimeError("timestamp slug is invalid")
    return stamp


def screenshot_filename(token: str, stamp: str, suffix: int = 0) -> str:
    if not _TOKEN_RE.fullmatch(token) or not _STAMP_RE.fullmatch(stamp):
        raise ValueError("refusing filename inputs")
    if suffix <= 0:
        name = f"{token}-{stamp}.png"
    else:
        if suffix > 99:
            raise ValueError("too many shots in the same second")
        name = f"{token}-{stamp}-{suffix}.png"
    if name.startswith(".") or "/" in name or "\\" in name or name in (".", ".."):
        raise ValueError("refusing filename")
    if len(name) > MAX_FILENAME:
        raise ValueError("filename too long")
    return name
