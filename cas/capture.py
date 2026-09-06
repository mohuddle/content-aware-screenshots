"""Focused-window screenshot, optional note/URL, index + PNG chunks."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from datetime import datetime

from cas import CasError
from cas.bounds import (
    GRIM_TIMEOUT_S,
    MAX_PNG_BYTES,
    SCREENSHOTS_SUBDIR,
    SLURP_TIMEOUT_S,
)
from cas.browsers import identify_class
from cas.dialog import run_note_dialog
from cas.hypr import Snapshot, match_region, parse_geometry, slurp_rects, snapshot, warp_to_focused
from cas.names import app_token, screenshot_filename, timestamp_slug
from cas.notify import send as notify
from cas.paths import open_dir_chain, xdg_pictures_parts
from cas.pngmeta import embed
from cas.proc import minimal_env, run_cmd, spawn_session
from cas.safeio import name_exists, write_atomic
from cas.store import CaptureRow, open_index
from cas.urls import parse_stored_url


def cmd_capture(*, skip_dialog: bool = False, note: str = "", url: str | None = None) -> str:
    _cancel_if_slurp_running()
    snap = snapshot()
    freeze = _start_freeze()
    try:
        warp_to_focused(snap)
        geo = _pick_region(snap)
    finally:
        _stop_freeze(freeze)
    parse_geometry(geo)
    png = _grim(geo)
    win = match_region(geo, snap)
    token = app_token(win.cls)
    when = datetime.now().astimezone()
    stamp = timestamp_slug(when)
    captured_at = when.isoformat(timespec="seconds")

    note_text = note
    url_text = parse_stored_url(url) if url else None
    source = "none"
    if not skip_dialog:
        dialog_note, dialog_url = run_note_dialog(
            show_url_hint=win.is_browser(),
            app_name=token,
            window_title=win.title,
            session_browser=identify_class(win.cls),
        )
        note_text = dialog_note
        if dialog_url:
            url_text = dialog_url
            source = "clipboard"

    tagged = embed(
        png,
        url=url_text,
        title=win.title,
        note=note_text,
        captured_at=captured_at,
    )
    dest_fd, dest_path, _subdir = _open_dest_dir()
    try:
        final_name = _unique_name(dest_fd, token, stamp)
        write_atomic(dest_fd, final_name, tagged, mode=0o644)
        digest = _sha256_bytes(tagged)
        abs_path = os.path.join(dest_path, final_name)
        row = CaptureRow(
            sha256=digest,
            path=abs_path,
            captured_at=captured_at,
            app_class=win.cls,
            app_name=token,
            window_title=win.title,
            geometry=geo,
            url=url_text,
            page_title=win.title if win.is_browser() else None,
            note=note_text,
            source=source if url_text else "none",
        )
        with open_index() as index:
            index.upsert(row)
        _copy_png(tagged)
        notify("Screenshot saved", final_name)
        return abs_path
    finally:
        os.close(dest_fd)


def _cancel_if_slurp_running() -> None:
    try:
        env = minimal_env()
    except CasError:
        return
    try:
        found = subprocess.run(
            ["/usr/bin/pgrep", "-x", "slurp"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            timeout=2,
            check=False,
            start_new_session=True,
        )
    except OSError:
        return
    if found.returncode != 0:
        return
    subprocess.run(
        ["/usr/bin/pkill", "-x", "slurp"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
        timeout=2,
        check=False,
        start_new_session=True,
    )
    raise SystemExit(0)


def _start_freeze() -> subprocess.Popen[bytes] | None:
    try:
        proc = spawn_session(["/usr/bin/hyprpicker", "-r", "-z"])
    except (CasError, OSError, FileNotFoundError):
        return None
    time.sleep(0.1)
    if proc.poll() is not None:
        return None
    return proc


def _stop_freeze(proc: subprocess.Popen[bytes] | None) -> None:
    if proc is None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except OSError:
        try:
            proc.terminate()
        except OSError:
            pass
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        try:
            proc.wait(timeout=1)
        except Exception:
            pass


def _pick_region(snap: Snapshot) -> str:
    rects = slurp_rects(snap)
    raw = run_cmd(
        ["/usr/bin/slurp"],
        timeout=SLURP_TIMEOUT_S,
        max_stdout=128,
        stdin=rects if rects else None,
        ok_exit=(0, 1),
    )
    text = raw.decode("utf-8", "replace").strip()
    if not text:
        raise SystemExit(0)
    x, y, w, h = parse_geometry(text)
    if w * h < 20 and snap.focused is not None:
        # Bare click: keep the focused window, matching omarchy smart mode.
        fx, fy, fw, fh = snap.focused.x, snap.focused.y, snap.focused.w, snap.focused.h
        if fx <= x < fx + fw and fy <= y < fy + fh:
            return snap.focused.geometry
        win = match_region(text, snap)
        return win.geometry
    return f"{x},{y} {w}x{h}"


def _grim(geo: str) -> bytes:
    parse_geometry(geo)
    data = run_cmd(
        ["/usr/bin/grim", "-t", "png", "-g", geo, "-"],
        timeout=GRIM_TIMEOUT_S,
        max_stdout=MAX_PNG_BYTES,
    )
    if not data.startswith(b"\x89PNG"):
        raise CasError("grim did not return a PNG")
    return data


def _open_dest_dir() -> tuple[int, str, str]:
    parts = xdg_pictures_parts()
    if parts[-1] != SCREENSHOTS_SUBDIR:
        parts = parts + (SCREENSHOTS_SUBDIR,)
    fd = open_dir_chain(parts, private=False, create=True, follow_user_symlink=True)
    home = os.environ.get("HOME") or os.path.expanduser("~")
    abs_path = os.path.join(home, *parts)
    return fd, abs_path, parts[-1]


def _unique_name(dirfd: int, token: str, stamp: str) -> str:
    for suffix in range(0, 100):
        name = screenshot_filename(token, stamp, suffix)
        if not name_exists(dirfd, name):
            return name
    raise CasError("too many screenshots in the same second")


def _sha256_bytes(data: bytes) -> str:
    import hashlib

    if len(data) > MAX_PNG_BYTES:
        raise CasError("file exceeds size limit")
    return hashlib.sha256(data).hexdigest()


def _copy_png(data: bytes) -> None:
    """Hand the PNG to wl-copy and return. Waiting for it to exit stalls Save
    for seconds because wl-copy stays alive as the clipboard owner."""
    try:
        env = minimal_env()
        proc = subprocess.Popen(
            ["/usr/bin/wl-copy", "--type", "image/png"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            start_new_session=True,
        )
    except OSError:
        return
    try:
        assert proc.stdin is not None
        proc.stdin.write(data)
        proc.stdin.close()
    except (BrokenPipeError, OSError):
        try:
            proc.kill()
        except OSError:
            pass
