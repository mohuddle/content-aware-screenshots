"""cas capture | search | note | refresh | reindex."""

from __future__ import annotations

import argparse
import os
import sys

from cas import CasError, __version__
from cas.bounds import MAX_PNG_BYTES, MAX_SEARCH_ROWS, SCREENSHOTS_SUBDIR
from cas.capture import cmd_capture
from cas.dialog import run_note_dialog
from cas.names import app_token
from cas.paths import home_dir, open_dir_chain, xdg_pictures_parts
from cas.pngmeta import embed, parse_text, split_chunks
from cas.safeio import read_bounded_fd, sha256_fd, write_atomic
from cas.store import CaptureRow, open_index
from cas.text import stderr_msg
from cas.urls import parse_stored_url


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="cas",
        description="Screenshot with an optional note and pasted URL. Local index only; no network.",
    )
    parser.add_argument("--version", action="version", version=f"cas {__version__}")
    sub = parser.add_subparsers(dest="cmd")

    cap = sub.add_parser("capture", help="focused-window screenshot plus note dialog")
    cap.add_argument("--skip-dialog", action="store_true", help="do not open the note dialog")
    cap.add_argument("--note", default="", help="note text (skips dialog if set with --skip-dialog)")
    cap.add_argument("--url", default="", help="store this URL (must be http or https)")

    search = sub.add_parser("search", help="query the local index")
    search.add_argument("query", nargs="?", default="", help="match note, path, url, or title")
    search.add_argument("--url", dest="url_pat", default="", help="SQL LIKE pattern against stored URL")
    search.add_argument("--app", default="", help="filter by app token, e.g. brave")
    search.add_argument("--limit", type=int, default=MAX_SEARCH_ROWS)

    note = sub.add_parser("note", help="add or replace the note on an existing PNG")
    note.add_argument("path")

    refresh = sub.add_parser("refresh", help="re-hash a PNG after editing and update the index")
    refresh.add_argument("path")

    reindex = sub.add_parser("reindex", help="rebuild index rows from PNG chunks in the screenshots dir")
    reindex.add_argument("directory", nargs="?", default="")

    if not argv or argv[0] not in {
        "capture",
        "search",
        "note",
        "refresh",
        "reindex",
        "-h",
        "--help",
        "--version",
    }:
        argv = ["capture", *argv]

    args = parser.parse_args(argv)
    try:
        if args.cmd == "capture":
            path = cmd_capture(
                skip_dialog=bool(args.skip_dialog),
                note=args.note,
                url=args.url or None,
            )
            sys.stdout.write(path + "\n")
            return 0
        if args.cmd == "search":
            return cmd_search(args.query, args.url_pat, args.app, args.limit)
        if args.cmd == "note":
            return cmd_note(args.path)
        if args.cmd == "refresh":
            return cmd_refresh(args.path)
        if args.cmd == "reindex":
            return cmd_reindex(args.directory)
        parser.print_help()
        return 2
    except CasError as exc:
        sys.stderr.write(stderr_msg(str(exc)) + "\n")
        return exc.code
    except BrokenPipeError:
        return 0


def cmd_search(query: str, url_pat: str, app: str, limit: int) -> int:
    with open_index() as index:
        rows = index.search(query=query, url=url_pat or None, app=app or None, limit=limit)
    if not rows:
        return 0
    for row in rows:
        url = row.url or "-"
        note = row.note.replace("\n", " ")
        sys.stdout.write(f"{row.captured_at}\t{row.app_name}\t{row.path}\t{url}\t{note}\n")
    return 0


def cmd_note(path: str) -> int:
    abs_path, dirfd, name, blob, digest = _open_png(path)
    try:
        meta = parse_text(split_chunks(blob))
        token = app_token(name.split("-")[0])
        show_hint = token in {"brave", "chrome", "chromium", "firefox", "edge"}
        note, url = run_note_dialog(
            show_url_hint=show_hint,
            app_name=token,
            window_title=str(meta.get("Title") or ""),
            offer_brave_session=token == "brave",
        )
        if url is None:
            url = parse_stored_url(meta.get("Source") or meta.get("URL") or "")
        captured = meta.get("Creation Time") or ""
        title = meta.get("Title") or ""
        tagged = embed(blob, url=url, title=title, note=note, captured_at=captured)
        write_atomic(dirfd, name, tagged, mode=0o644)
        file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=dirfd)
        try:
            new_digest = sha256_fd(file_fd, MAX_PNG_BYTES)
        finally:
            os.close(file_fd)
        _upsert_file(abs_path, new_digest, tagged, note=note, url=url)
        sys.stdout.write(abs_path + "\n")
        return 0
    finally:
        os.close(dirfd)


def cmd_refresh(path: str) -> int:
    abs_path, dirfd, name, blob, digest = _open_png(path)
    os.close(dirfd)
    _upsert_file(abs_path, digest, blob)
    sys.stdout.write(abs_path + "\n")
    return 0


def cmd_reindex(directory: str) -> int:
    from cas.bounds import MAX_REINDEX_FILES

    if directory:
        if not os.path.isabs(directory):
            raise CasError("reindex directory must be absolute")
        parts = _parts_under_home_public(directory)
    else:
        parts = xdg_pictures_parts()
        if parts[-1] != SCREENSHOTS_SUBDIR:
            parts = parts + (SCREENSHOTS_SUBDIR,)
    dirfd = open_dir_chain(parts, private=False, create=False, follow_user_symlink=True)
    count = 0
    try:
        with os.scandir(f"/proc/self/fd/{dirfd}") as entries:
            names = []
            for entry in entries:
                if count + len(names) >= MAX_REINDEX_FILES:
                    break
                if not entry.is_file(follow_symlinks=False):
                    continue
                if not entry.name.endswith(".png") or entry.name.startswith("."):
                    continue
                names.append(entry.name)
        with open_index() as index:
            for name in names:
                try:
                    abs_path, _d, _n, blob, digest = _open_png_in(dirfd, parts, name)
                    row = _row_from_png(abs_path, digest, blob)
                    index.upsert(row)
                    count += 1
                except (CasError, OSError):
                    continue
    finally:
        os.close(dirfd)
    sys.stdout.write(f"{count}\n")
    return 0


def _open_png(path: str) -> tuple[str, int, str, bytes, str]:
    if not path or "\x00" in path:
        raise CasError("bad path")
    abs_path = path if os.path.isabs(path) else os.path.abspath(path)
    if not abs_path.endswith(".png"):
        raise CasError("not a PNG path")
    parent, name = os.path.split(abs_path)
    if not name or name.startswith(".") or "/" in name:
        raise CasError("bad file name")
    parent_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        st = os.fstat(parent_fd)
        if st.st_uid != os.geteuid():
            raise CasError("refusing directory owned by another user")
        return _open_png_in(parent_fd, (), name, abs_path=abs_path)
    except BaseException:
        os.close(parent_fd)
        raise


def _open_png_in(
    dirfd: int,
    parts: tuple[str, ...],
    name: str,
    abs_path: str | None = None,
) -> tuple[str, int, str, bytes, str]:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=dirfd)
    try:
        blob = read_bounded_fd(fd, MAX_PNG_BYTES)
        os.lseek(fd, 0, os.SEEK_SET)
        digest = sha256_fd(fd, MAX_PNG_BYTES)
    finally:
        os.close(fd)
    if abs_path is None:
        abs_path = os.path.join(home_dir(), *parts, name)
    # Caller owns dirfd except _open_png which passes parent_fd as dirfd to return.
    return abs_path, dirfd, name, blob, digest


def _row_from_png(abs_path: str, digest: str, blob: bytes, note: str | None = None, url: str | None = None) -> CaptureRow:
    meta = parse_text(split_chunks(blob))
    stored_url = url if url is not None else parse_stored_url(meta.get("Source") or meta.get("URL") or "")
    stored_note = note if note is not None else (meta.get("Comment") or "")
    title = meta.get("Title") or ""
    captured = meta.get("Creation Time") or ""
    base = os.path.basename(abs_path)
    token = base.split("-")[0] if "-" in base else "app"
    return CaptureRow(
        sha256=digest,
        path=abs_path,
        captured_at=captured or "unknown",
        app_class=token,
        app_name=app_token(token),
        window_title=title,
        geometry="",
        url=stored_url,
        page_title=title or None,
        note=stored_note,
        source="clipboard" if stored_url else "none",
    )


def _upsert_file(abs_path: str, digest: str, blob: bytes, note: str | None = None, url: str | None = None) -> None:
    row = _row_from_png(abs_path, digest, blob, note=note, url=url)
    with open_index() as index:
        index.upsert(row)


def _parts_under_home_public(path: str) -> tuple[str, ...]:
    from cas.paths import _parts_under_home

    return _parts_under_home(path)
