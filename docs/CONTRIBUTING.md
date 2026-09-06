# Contributing

This is a local desktop helper, not an Omarchy Quattro plugin. It still follows
the same I/O rules: `O_NOFOLLOW` opens, atomic rename writes, producer-side
byte caps, absolute binaries, no shell strings.

```bash
PYTHONPATH=. /usr/bin/python3 -m unittest discover -s tests -v
```

Do not add `AGENTS.md`, `CLAUDE.md`, or other agent instruction files.
Do not fetch URLs. Stored `http`/`https` values are data, not requests.
Do not edit `/usr/share/omarchy/`. User Hyprland overrides go in
`~/.config/hypr/`.

Layout:

| Path | Role |
|---|---|
| `bin/cas` | `python3 -I` launcher |
| `cas/capture.py` | grim/slurp wrapper |
| `cas/dialog.py` | GTK 4 note dialog |
| `cas/browsers.py` | Window class → Brave/Chrome/Firefox/… |
| `cas/session.py` | Dispatches to Chromium SNSS or Firefox mozLz4 |
| `cas/chromium_session.py` | SNSS `Session_*` reader |
| `cas/firefox_session.py` | `recovery.jsonlz4` reader |
| `cas/store.py` | SQLite index |
| `cas/safeio.py` | descriptor-bound read/write |
| `cas/pngmeta.py` | PNG text chunks |
| `tests/` | unittest (no display required) |
