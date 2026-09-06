"""Read the selected tab URL from Brave's local SNSS Session_* file.

No network. The file is only opened after the user checks the dialog box.
"""

from __future__ import annotations

import os
import re
import stat
from collections import defaultdict

from cas.bounds import MAX_SESSION_BYTES, MAX_SESSION_COMMANDS, MAX_SESSION_TABS, MAX_TITLE
from cas.paths import open_dir_chain
from cas.safeio import read_bounded_fd
from cas.text import clean_title
from cas.urls import parse_stored_url

SESSION_NAME_RE = re.compile(r"^Session_[0-9]{10,24}$")
SESSION_PARTS = (".config", "BraveSoftware", "Brave-Browser", "Default", "Sessions")

CMD_SET_TAB_WINDOW = 0
CMD_SET_TAB_INDEX = 2
CMD_UPDATE_NAV = 6
CMD_SEL_NAV = 7
CMD_SEL_TAB = 8


class _Pickle:
    def __init__(self, data: bytes) -> None:
        if len(data) < 4:
            raise ValueError("short pickle")
        self.buf = data[4:]
        self.i = 0

    def _align(self) -> None:
        self.i = (self.i + 3) & ~3

    def u32(self) -> int:
        if self.i + 4 > len(self.buf):
            raise ValueError("u32")
        v = int.from_bytes(self.buf[self.i : self.i + 4], "little")
        self.i += 4
        return v

    def i32(self) -> int:
        if self.i + 4 > len(self.buf):
            raise ValueError("i32")
        v = int.from_bytes(self.buf[self.i : self.i + 4], "little", signed=True)
        self.i += 4
        return v

    def string(self) -> bytes:
        n = self.u32()
        if n > MAX_SESSION_BYTES or self.i + n > len(self.buf):
            raise ValueError("string")
        s = self.buf[self.i : self.i + n]
        self.i += n
        self._align()
        return s

    def string16(self) -> str:
        n = self.u32()
        nbytes = n * 2
        if nbytes > MAX_SESSION_BYTES or self.i + nbytes > len(self.buf):
            raise ValueError("string16")
        s = self.buf[self.i : self.i + nbytes].decode("utf-16le", "replace")
        self.i += nbytes
        self._align()
        return s


def _iter_commands(data: bytes) -> list[tuple[int, bytes]]:
    if len(data) < 8 or data[:4] != b"SNSS":
        return []
    version = int.from_bytes(data[4:8], "little")
    if version < 1 or version > 8:
        return []
    out: list[tuple[int, bytes]] = []
    i = 8
    while i + 2 <= len(data) and len(out) < MAX_SESSION_COMMANDS:
        size = int.from_bytes(data[i : i + 2], "little")
        i += 2
        if size < 1 or i + size > len(data):
            break
        out.append((data[i], data[i + 1 : i + size]))
        i += size
    return out


def parse_active_tab_url(data: bytes, *, window_title: str = "") -> str | None:
    """Replay a Session_* blob; return the selected tab's http(s) URL or None."""
    tab_window: dict[int, int] = {}
    tab_visual: dict[int, int] = {}
    sel_nav: dict[int, int] = {}
    selected: dict[int, int] = {}
    selected_order: list[int] = []
    navs: dict[int, dict[int, tuple[str, str]]] = defaultdict(dict)

    for cid, payload in _iter_commands(data):
        if cid == CMD_SET_TAB_WINDOW and len(payload) >= 8:
            win = int.from_bytes(payload[0:4], "little", signed=True)
            tab = int.from_bytes(payload[4:8], "little", signed=True)
            tab_window[tab] = win
        elif cid == CMD_SET_TAB_INDEX and len(payload) >= 8:
            tab = int.from_bytes(payload[0:4], "little", signed=True)
            vis = int.from_bytes(payload[4:8], "little", signed=True)
            tab_visual[tab] = vis
        elif cid == CMD_SEL_NAV and len(payload) >= 8:
            tab = int.from_bytes(payload[0:4], "little", signed=True)
            sel_nav[tab] = int.from_bytes(payload[4:8], "little", signed=True)
        elif cid == CMD_SEL_TAB and len(payload) >= 8:
            win = int.from_bytes(payload[0:4], "little", signed=True)
            vis = int.from_bytes(payload[4:8], "little", signed=True)
            selected[win] = vis
            if win not in selected_order:
                selected_order.append(win)
            else:
                selected_order.remove(win)
                selected_order.append(win)
        elif cid == CMD_UPDATE_NAV:
            try:
                pkl = _Pickle(payload)
                tab = pkl.i32()
                index = pkl.i32()
                url = pkl.string().decode("utf-8")
                title = pkl.string16()
            except (ValueError, UnicodeDecodeError):
                continue
            parsed = parse_stored_url(url)
            if parsed is None:
                continue
            navs[tab][index] = (parsed, clean_title(title, MAX_TITLE))
            if len(navs) > MAX_SESSION_TABS:
                return None

    win_visual_tab = {}
    for tab, vis in tab_visual.items():
        win = tab_window.get(tab)
        if win is not None:
            win_visual_tab[(win, vis)] = tab

    candidates: list[tuple[str, str]] = []
    for win, vis in selected.items():
        tab = win_visual_tab.get((win, vis))
        if tab is None:
            continue
        navmap = navs.get(tab, {})
        if not navmap:
            continue
        ni = sel_nav.get(tab)
        if ni not in navmap:
            ni = max(navmap)
        url, title = navmap[ni]
        candidates.append((url, title))

    if not candidates:
        return None
    wanted = _strip_browser_suffix(window_title).casefold()
    if wanted:
        for url, title in candidates:
            t = title.casefold()
            if t and (t in wanted or wanted in t):
                return url
    if selected_order:
        last_win = selected_order[-1]
        vis = selected.get(last_win)
        if vis is not None:
            tab = win_visual_tab.get((last_win, vis))
            if tab is not None and tab in navs:
                navmap = navs[tab]
                ni = sel_nav.get(tab)
                if ni not in navmap:
                    ni = max(navmap)
                return navmap[ni][0]
    return candidates[-1][0]


def active_tab_url(*, window_title: str = "") -> str | None:
    """Open the newest Session_* under the Brave profile and return its active URL."""
    try:
        dirfd = open_dir_chain(
            SESSION_PARTS,
            private=False,
            create=False,
            follow_user_symlink=True,
        )
    except (FileNotFoundError, OSError):
        return None
    fd = None
    try:
        newest_mtime = -1.0
        with os.scandir(f"/proc/self/fd/{dirfd}") as entries:
            names = []
            for entry in entries:
                if not SESSION_NAME_RE.fullmatch(entry.name):
                    continue
                if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                    continue
                names.append(entry.name)
                if len(names) > 32:
                    break
        for name in names:
            try:
                nfd = os.open(
                    name,
                    os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                    dir_fd=dirfd,
                )
            except OSError:
                continue
            try:
                st = os.fstat(nfd)
                if not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid() or st.st_nlink != 1:
                    os.close(nfd)
                    continue
                if st.st_size > MAX_SESSION_BYTES:
                    os.close(nfd)
                    continue
                mtime = st.st_mtime
                if mtime >= newest_mtime:
                    if fd is not None:
                        os.close(fd)
                    fd = nfd
                    newest_mtime = mtime
                else:
                    os.close(nfd)
            except OSError:
                try:
                    os.close(nfd)
                except OSError:
                    pass
        if fd is None:
            return None
        blob = read_bounded_fd(fd, MAX_SESSION_BYTES)
        return parse_active_tab_url(blob, window_title=window_title)
    except (OSError, ValueError):
        return None
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        os.close(dirfd)


def _strip_browser_suffix(title: str) -> str:
    text = clean_title(title, MAX_TITLE)
    for suffix in (" - Brave", " - Chromium", " - Google Chrome"):
        if text.endswith(suffix):
            return text[: -len(suffix)].rstrip()
    return text
