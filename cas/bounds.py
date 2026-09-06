"""Hard caps. Every untrusted string and subprocess output hits these first."""

from __future__ import annotations

MAX_NOTE_CHARS = 500
MAX_NOTE_BYTES = 2000
MAX_URL_BYTES = 2048
MAX_CLASS = 128
MAX_TITLE = 512
MAX_APP_TOKEN = 32
MAX_GEOMETRY = 64
MAX_PATH = 4096
MAX_SHA256_HEX = 64
MAX_SOURCE = 16
MAX_PNG_BYTES = 50 * 1024 * 1024
MAX_HYPR_JSON = 1 * 1024 * 1024
MAX_CLIENTS = 256
MAX_CLIPBOARD = 8192
MAX_STDERR = 200
MAX_NOTIFY = 80
MAX_SEARCH_ROWS = 100
MAX_SEARCH_QUERY = 256
MAX_REINDEX_FILES = 5000
MAX_FILENAME = 180
MAX_CHUNKS = 1024
MAX_CHUNK = 16 * 1024
MAX_PROC_STDOUT = 1 * 1024 * 1024
MAX_SESSION_BYTES = 8 * 1024 * 1024
MAX_SESSION_COMMANDS = 20000
MAX_SESSION_TABS = 256

HYPR_TIMEOUT_S = 5.0
GRIM_TIMEOUT_S = 20.0
SLURP_TIMEOUT_S = 300.0
WL_TIMEOUT_S = 3.0
NOTIFY_TIMEOUT_S = 5.0
SQLITE_TIMEOUT_S = 5.0

INDEX_PARTS = (".local", "share", "omarchy-cas")
INDEX_NAME = "index.sqlite"
SCREENSHOTS_SUBDIR = "screenshots"

BROWSER_CLASSES = frozenset(
    {
        "brave-browser",
        "brave-browser-beta",
        "brave-browser-nightly",
        "chromium",
        "google-chrome",
        "google-chrome-beta",
        "firefox",
        "firefox-esr",
        "zen",
        "zen-alpha",
        "zen-browser",
        "vivaldi",
        "vivaldi-stable",
        "microsoft-edge",
        "microsoft-edge-dev",
        "org.mozilla.firefox",
        "org.chromium.chromium",
        "com.brave.browser",
        "org.gnome.epiphany",
    }
)

ALLOWED_BIN_PREFIXES = (
    "/usr/bin/",
    "/usr/share/omarchy/bin/",
)
