"""Read the selected tab URL from Firefox-family sessionstore JSON (mozLz4)."""

from __future__ import annotations

import json
import os
import re

from cas import CasError
from cas.bounds import MAX_SESSION_BYTES, MAX_SESSION_TABS, MAX_TITLE
from cas.paths import open_dir_chain, open_subdir
from cas.safeio import read_bounded_fd, read_bounded_name
from cas.text import clean_title
from cas.urls import parse_stored_url

MOZLZ4_MAGIC = b"mozLz40\0"
PROFILE_LINE = re.compile(r"^([A-Za-z]+)=(.*)$")
INI_SECTION = re.compile(r"^\[Profile[0-9]{1,4}\]$")
REL_PATH_RE = re.compile(r"^[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)?$")
MAX_WINDOWS = 16
MAX_TABS = MAX_SESSION_TABS
MAX_ENTRIES = 64
MAX_PROFILES_INI = 65536


def parse_session_json(data: bytes, *, window_title: str = "") -> str | None:
    try:
        obj = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(obj, dict):
        return None
    windows = obj.get("windows")
    if not isinstance(windows, list) or not windows or len(windows) > MAX_WINDOWS:
        return None
    selected_window = obj.get("selectedWindow")
    candidates: list[tuple[str, str]] = []
    for win in windows:
        got = _window_selected_url(win)
        if got:
            candidates.append(got)
    if not candidates:
        return None
    wanted = _strip_browser_suffix(window_title).casefold()
    if wanted:
        for url, title in candidates:
            t = title.casefold()
            if t and (t in wanted or wanted in t):
                return url
    if isinstance(selected_window, int) and 1 <= selected_window <= len(windows):
        picked = _window_selected_url(windows[selected_window - 1])
        if picked:
            return picked[0]
    return candidates[-1][0]


def _window_selected_url(win: object) -> tuple[str, str] | None:
    if not isinstance(win, dict):
        return None
    tabs = win.get("tabs")
    if not isinstance(tabs, list) or not tabs or len(tabs) > MAX_TABS:
        return None
    selected = win.get("selected")
    if not isinstance(selected, int) or selected < 1 or selected > len(tabs):
        selected = 1
    tab = tabs[selected - 1]
    if not isinstance(tab, dict):
        return None
    entries = tab.get("entries")
    if not isinstance(entries, list) or not entries or len(entries) > MAX_ENTRIES:
        typed = tab.get("userTypedValue")
        if isinstance(typed, str):
            parsed = parse_stored_url(typed)
            if parsed:
                return parsed, ""
        return None
    index = tab.get("index")
    if not isinstance(index, int) or index < 1 or index > len(entries):
        index = len(entries)
    entry = entries[index - 1]
    if not isinstance(entry, dict):
        return None
    raw = entry.get("url")
    if not isinstance(raw, str):
        return None
    parsed = parse_stored_url(raw)
    if parsed is None:
        return None
    title = entry.get("title")
    title_s = clean_title(title, MAX_TITLE) if isinstance(title, str) else ""
    return parsed, title_s


def decode_mozlz4(blob: bytes) -> bytes | None:
    if len(blob) < 12 or not blob.startswith(MOZLZ4_MAGIC):
        return None
    size = int.from_bytes(blob[8:12], "little")
    if size <= 0 or size > MAX_SESSION_BYTES:
        return None
    try:
        out = _lz4_decompress_block(blob[12:], size)
    except ValueError:
        return None
    if len(out) > MAX_SESSION_BYTES:
        return None
    return out


def _lz4_decompress_block(src: bytes, max_out: int) -> bytes:
    i = 0
    out = bytearray()
    slen = len(src)
    while i < slen:
        if len(out) > max_out:
            raise ValueError("lz4 output too large")
        token = src[i]
        i += 1
        lit = token >> 4
        if lit == 15:
            while True:
                if i >= slen:
                    raise ValueError("lz4 truncated")
                extra = src[i]
                i += 1
                lit += extra
                if extra != 255:
                    break
        if lit:
            if i + lit > slen:
                raise ValueError("lz4 literals")
            out.extend(src[i : i + lit])
            i += lit
        if i >= slen:
            break
        if i + 2 > slen:
            raise ValueError("lz4 offset")
        offset = int.from_bytes(src[i : i + 2], "little")
        i += 2
        if offset == 0 or offset > len(out):
            raise ValueError("lz4 bad offset")
        match = (token & 15) + 4
        if (token & 15) == 15:
            while True:
                if i >= slen:
                    raise ValueError("lz4 truncated")
                extra = src[i]
                i += 1
                match += extra
                if extra != 255:
                    break
        for _ in range(match):
            out.append(out[-offset])
            if len(out) > max_out:
                raise ValueError("lz4 output too large")
    return bytes(out)


def lz4_compress_literals(data: bytes) -> bytes:
    """Literal-only LZ4 block, for tests."""
    n = len(data)
    out = bytearray()
    lit = n
    token_lit = 15 if lit >= 15 else lit
    out.append(token_lit << 4)
    if lit >= 15:
        rest = lit - 15
        while rest >= 255:
            out.append(255)
            rest -= 255
        out.append(rest)
    out.extend(data)
    return bytes(out)


def wrap_mozlz4(plain: bytes) -> bytes:
    return MOZLZ4_MAGIC + len(plain).to_bytes(4, "little") + lz4_compress_literals(plain)


def active_tab_url(*, root_parts: tuple[str, ...], window_title: str = "") -> str | None:
    try:
        root_fd = open_dir_chain(
            root_parts,
            private=False,
            create=False,
            follow_user_symlink=True,
        )
    except (FileNotFoundError, OSError, CasError):
        return None
    prof_fd = None
    backups_fd = None
    try:
        rel = _default_profile_rel(root_fd)
        if rel is None:
            return None
        parent = root_fd
        opened: list[int] = []
        try:
            for part in rel:
                nfd = open_subdir(
                    parent,
                    part,
                    private=False,
                    create=False,
                    follow_user_symlink=True,
                )
                opened.append(nfd)
                parent = nfd
            prof_fd = parent
            try:
                backups_fd = open_subdir(
                    prof_fd,
                    "sessionstore-backups",
                    private=False,
                    create=False,
                    follow_user_symlink=True,
                )
            except (FileNotFoundError, OSError):
                backups_fd = None
            for dirfd, name in (
                (backups_fd, "recovery.jsonlz4") if backups_fd is not None else (None, None),
                (backups_fd, "recovery.baklz4") if backups_fd is not None else (None, None),
                (prof_fd, "sessionstore.jsonlz4"),
            ):
                if dirfd is None or name is None:
                    continue
                url = _read_named_session(dirfd, name, window_title=window_title)
                if url:
                    return url
            return None
        finally:
            for nfd in reversed(opened):
                if nfd != prof_fd:
                    try:
                        os.close(nfd)
                    except OSError:
                        pass
    except (OSError, ValueError, CasError):
        return None
    finally:
        if backups_fd is not None:
            try:
                os.close(backups_fd)
            except OSError:
                pass
        if prof_fd is not None:
            try:
                os.close(prof_fd)
            except OSError:
                pass
        os.close(root_fd)


def _read_named_session(dirfd: int, name: str, *, window_title: str) -> str | None:
    try:
        fd = os.open(
            name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
            dir_fd=dirfd,
        )
    except OSError:
        return None
    try:
        blob = read_bounded_fd(fd, MAX_SESSION_BYTES)
    except (OSError, ValueError, CasError):
        os.close(fd)
        return None
    os.close(fd)
    plain = decode_mozlz4(blob)
    if plain is None:
        return None
    return parse_session_json(plain, window_title=window_title)


def _default_profile_rel(root_fd: int) -> tuple[str, ...] | None:
    try:
        raw = read_bounded_name(root_fd, "profiles.ini", MAX_PROFILES_INI)
    except (FileNotFoundError, OSError, ValueError):
        return None
    if not raw:
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    profiles: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in text.splitlines():
        line = line.strip()
        if INI_SECTION.match(line):
            current = {}
            profiles.append(current)
            continue
        if current is None:
            continue
        m = PROFILE_LINE.match(line)
        if not m:
            continue
        current[m.group(1)] = m.group(2)
    chosen: dict[str, str] | None = None
    for item in profiles:
        if item.get("Default") == "1":
            chosen = item
            break
    if chosen is None and profiles:
        chosen = profiles[0]
    if chosen is None:
        return None
    path = chosen.get("Path", "")
    relative = chosen.get("IsRelative", "1")
    if relative != "1":
        return None
    if not REL_PATH_RE.fullmatch(path):
        return None
    parts = tuple(p for p in path.split("/") if p)
    if not parts or any(p in (".", "..") for p in parts):
        return None
    return parts


def _strip_browser_suffix(title: str) -> str:
    text = clean_title(title, MAX_TITLE)
    for suffix in (
        " — Mozilla Firefox",
        " - Mozilla Firefox",
        " - Firefox",
        " — LibreWolf",
        " - LibreWolf",
        " - Zen Browser",
        " - Zen",
    ):
        if text.endswith(suffix):
            return text[: -len(suffix)].rstrip()
    return text
