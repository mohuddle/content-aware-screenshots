"""Map a Hyprland window class to a local browser session store."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Browser:
    kind: str  # "chromium" | "firefox"
    label: str
    # Chromium: config dir under $HOME (.../Brave-Browser). Firefox: profiles root.
    root_parts: tuple[str, ...]


_CHROMIUM: dict[str, Browser] = {}
_FIREFOX: dict[str, Browser] = {}


def _c(label: str, *parts: str) -> Browser:
    return Browser(kind="chromium", label=label, root_parts=parts)


def _f(label: str, *parts: str) -> Browser:
    return Browser(kind="firefox", label=label, root_parts=parts)


BRAVE = _c("Brave", ".config", "BraveSoftware", "Brave-Browser")
BRAVE_BETA = _c("Brave", ".config", "BraveSoftware", "Brave-Browser-Beta")
CHROMIUM = _c("Chromium", ".config", "chromium")
CHROME = _c("Chrome", ".config", "google-chrome")
CHROME_BETA = _c("Chrome", ".config", "google-chrome-beta")
EDGE = _c("Edge", ".config", "microsoft-edge")
VIVALDI = _c("Vivaldi", ".config", "vivaldi")
FIREFOX = _f("Firefox", ".mozilla", "firefox")
LIBREWOLF = _f("LibreWolf", ".librewolf")
ZEN = _f("Zen", ".zen")

_EXACT: dict[str, Browser] = {
    "brave-browser": BRAVE,
    "brave-browser-beta": BRAVE_BETA,
    "brave-browser-nightly": BRAVE,
    "com.brave.browser": BRAVE,
    "chromium": CHROMIUM,
    "org.chromium.chromium": CHROMIUM,
    "google-chrome": CHROME,
    "google-chrome-beta": CHROME_BETA,
    "microsoft-edge": EDGE,
    "microsoft-edge-dev": EDGE,
    "vivaldi": VIVALDI,
    "vivaldi-stable": VIVALDI,
    "firefox": FIREFOX,
    "firefox-esr": FIREFOX,
    "org.mozilla.firefox": FIREFOX,
    "librewolf": LIBREWOLF,
    "io.github.librewolf-community": LIBREWOLF,
    "zen": ZEN,
    "zen-alpha": ZEN,
    "zen-browser": ZEN,
}

_TOKEN: dict[str, Browser] = {
    "brave": BRAVE,
    "chromium": CHROMIUM,
    "chrome": CHROME,
    "edge": EDGE,
    "vivaldi": VIVALDI,
    "firefox": FIREFOX,
    "librewolf": LIBREWOLF,
    "zen": ZEN,
}


def identify_class(cls: str) -> Browser | None:
    lowered = cls.strip().lower()
    if not lowered:
        return None
    found = _EXACT.get(lowered)
    if found:
        return found
    if lowered.startswith("brave"):
        return BRAVE
    if lowered.startswith("google-chrome"):
        return CHROME
    if lowered.startswith("chromium"):
        return CHROMIUM
    if lowered.startswith("microsoft-edge"):
        return EDGE
    if lowered.startswith("vivaldi"):
        return VIVALDI
    if lowered.startswith("firefox"):
        return FIREFOX
    if lowered.startswith("librewolf"):
        return LIBREWOLF
    if lowered.startswith("zen"):
        return ZEN
    return None


def identify_token(token: str) -> Browser | None:
    return _TOKEN.get(token.strip().lower())
