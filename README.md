# cas — screenshot, note, optional URL

A Hyprland / Omarchy helper: capture the focused window (or a cropped region),
type an optional 500-character note, and optionally attach an `http(s)` URL.
The PNG keeps that metadata in text chunks. A local SQLite index lets you
search later.

There is **no network**. Stored URLs are never fetched or opened. There is no
browser extension.

## Workflow

1. Press **Super+Shift+Print** (or run `cas capture`).
2. The picker starts on the focused window. Drag to crop, or click / press
   Enter on that window. Esc or a second press cancels; nothing is saved.
3. A floating note dialog opens in the center of the screen. Type up to 500
   characters. Esc / Skip saves the PNG with an empty note.
4. If the window was a browser, the dialog also has a URL field:
   - **Alt+D** then copy, or **Alt+Shift+L** (Omarchy Copy URL), then
     **Paste URL**.
   - A copied `http(s)` URL is picked up while the dialog is open unless you
     already edited the field.
   - If the window is **Brave, Chrome, Chromium, Edge, Vivaldi, Firefox,
     LibreWolf, or Zen**, check **Use current {browser} tab URL**. That reads
     the matching local session file for the selected tab. The box is off
     until you check it. The file can lag a moment behind a just-switched
     tab.
5. The file is `~/Pictures/screenshots/{app}-{YYYY-MM-DD}_{HH-MM-SS}.png`.

Stock **Print** is unchanged (`omarchy-capture-screenshot`). This is a second
hotkey.

## Install

Needs grim, slurp, hyprctl, hyprpicker, wl-copy, wl-paste, python-gobject
(GTK 4), and sqlite. Omarchy already has these.

```bash
git clone https://github.com/mohuddle/content-aware-screenshots.git
ln -s "$PWD/content-aware-screenshots/bin/cas" ~/.local/bin/cas
```

`~/.local/bin` should already be on your PATH.

Add a Hyprland bind (do **not** replace Print). In `~/.config/hypr/bindings.lua`:

```lua
o.bind("SUPER + SHIFT + PRINT", "Screenshot with note", "cas capture")
```

Wayland clients cannot place themselves. Float and center the dialog in
`~/.config/hypr/hyprland.lua`:

```lua
o.window("^local\\.omarchy\\.cas\\.note$", { float = true, center = true, size = { 560, 420 } })
```

Then `hyprctl reload` and `hyprctl configerrors`.

## Commands

```bash
cas capture                 # default; same as `cas`
cas search overhead
cas search --url 'https://x.com/%'
cas search --app brave
cas note /path/to/file.png      # edit the note/URL on an existing shot
cas refresh /path/to/file.png   # re-hash after tensaku-edit (Super+Alt+,)
cas reindex                     # rebuild index rows from PNG chunks
```

`cas search --url` is a SQL `LIKE` pattern (`%` / `_` are wildcards). Plain
`cas search text` matches note, path, URL, and title with those characters
escaped.

## What is stored

| Place | Path | Mode | Contents |
|---|---|---|---|
| Index | `~/.local/share/omarchy-cas/index.sqlite` | directory 0700, file 0600 | sha256, path, app, time, optional URL, note |
| PNGs | `~/Pictures/screenshots/*.png` | 0644 | pixels plus `Source` / `URL` / `Comment` / `Title` text chunks |

The index is private. The PNG is a normal picture: anyone who can read the
file can read the URL and note in its chunks. Sharing the PNG to X/Discord
often strips chunks; the local index still has the row.

Override the pictures root with `OMARCHY_SCREENSHOT_DIR` only if it is an
absolute path under `$HOME`. `cas` then writes a `screenshots` subdirectory
there.

## Session-file URL (opt-in checkbox)

The window class from Hyprland picks the store:

| Window class (examples) | Store |
|---|---|
| `brave-browser` | `~/.config/BraveSoftware/Brave-Browser/<profile>/Sessions/Session_*` |
| `chromium` | `~/.config/chromium/<profile>/Sessions/Session_*` |
| `google-chrome` | `~/.config/google-chrome/<profile>/Sessions/Session_*` |
| `microsoft-edge` | `~/.config/microsoft-edge/<profile>/Sessions/Session_*` |
| `vivaldi` | `~/.config/vivaldi/<profile>/Sessions/Session_*` |
| `firefox` | `~/.mozilla/firefox/<profile>/sessionstore-backups/recovery.jsonlz4` |
| `librewolf` | `~/.librewolf/<profile>/sessionstore-backups/recovery.jsonlz4` |
| `zen` / `zen-browser` | `~/.zen/<profile>/sessionstore-backups/recovery.jsonlz4` |

Chromium-family browsers use SNSS `Session_*` (not `Tabs_*`, which is
closed-tab restore). The profile is `Local State` `last_used`, else
`Default`. Firefox-family browsers use mozLz4 JSON; the profile comes from
`profiles.ini` (`Default=1`). Incognito is not persisted. Multiple windows:
the Hyprland window title is matched when possible.

The reader never writes those directories and never talks to the browser over
IPC or the network.

## Security notes

- Subprocesses are argv arrays with absolute `/usr/bin` (or
  `/usr/share/omarchy/bin`) paths, a session, a deadline, and a byte cap.
- The index is opened `O_NOFOLLOW` on a held directory descriptor; SQLite uses
  a memory journal so it does not create sibling `-wal` files by pathname.
- PNG writes use an exclusive temporary in the destination directory and
  `rename(2)`, which replaces a planted symlink instead of writing through it.
- Notes are capped at 500 characters and stripped of `<`, `>`, `&`, and
  control/bidi characters before storage and notifications.
- URLs must parse as `http` or `https` with no userinfo. `javascript:`,
  `file:`, and option-shaped values are dropped.
- Window titles, clipboard text, and session-file strings are untrusted. They
  are not executed and not rendered as markup.
- The session reader runs only after you check the box. Chromium `Session_*`
  files and Firefox `recovery.jsonlz4` are opened `O_NOFOLLOW` with an 8 MiB
  cap. `javascript:` / `file:` URLs are dropped.
- `XDG_RUNTIME_DIR` must be a `/run/user/` path; there is no `/tmp` fallback.
- Notifications are text only. There is no stored `--exec` action.

## Removing

1. Delete the Super+Shift+Print bind from `~/.config/hypr/bindings.lua`.
2. Delete the `local.omarchy.cas.note` window rule from
   `~/.config/hypr/hyprland.lua`.
3. Unlink `~/.local/bin/cas` if you created that symlink.
4. Screenshot PNGs under `~/Pictures/screenshots/` are left in place.
5. The index is the file `~/.local/share/omarchy-cas/index.sqlite`. Remove that
   file (and the empty `omarchy-cas` directory) if you want stored URLs and
   notes gone.

Do not delete `~/Pictures` or other tools' state.

## Tests

```bash
PYTHONPATH=. /usr/bin/python3 -m unittest discover -s tests -v
```

## Limits

- Not a full-page or DOM capture. Pixels plus provenance.
- Non-browser windows store class + title; URL is optional paste.
- The session-file URL is best-effort and can lag the visible tab.
- `tensaku-edit` after capture changes pixels; run `cas refresh` on that file
  so the index hash matches.
