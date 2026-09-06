"""SQLite index opened through a validated descriptor; memory journal."""

from __future__ import annotations

import os
import sqlite3
import stat
from dataclasses import dataclass
from typing import Iterator

from cas import CasError
from cas.bounds import (
    INDEX_NAME,
    INDEX_PARTS,
    MAX_CLASS,
    MAX_GEOMETRY,
    MAX_NOTE_CHARS,
    MAX_PATH,
    MAX_SEARCH_QUERY,
    MAX_SEARCH_ROWS,
    MAX_SHA256_HEX,
    MAX_SOURCE,
    MAX_TITLE,
    MAX_URL_BYTES,
    SQLITE_TIMEOUT_S,
)
from cas.paths import open_dir_chain
from cas.text import clean_note, clean_title
from cas.urls import parse_stored_url

SCHEMA = """
CREATE TABLE IF NOT EXISTS captures (
  sha256 TEXT PRIMARY KEY CHECK(length(sha256) = 64),
  path TEXT NOT NULL CHECK(length(path) <= 4096),
  captured_at TEXT NOT NULL CHECK(length(captured_at) <= 64),
  app_class TEXT NOT NULL CHECK(length(app_class) <= 128),
  app_name TEXT NOT NULL CHECK(length(app_name) <= 32),
  window_title TEXT NOT NULL CHECK(length(window_title) <= 512),
  geometry TEXT NOT NULL CHECK(length(geometry) <= 64),
  url TEXT CHECK(url IS NULL OR length(url) <= 2048),
  page_title TEXT CHECK(page_title IS NULL OR length(page_title) <= 512),
  note TEXT NOT NULL DEFAULT '' CHECK(length(note) <= 500),
  source TEXT NOT NULL CHECK(source IN ('clipboard', 'none'))
);
CREATE INDEX IF NOT EXISTS captures_url ON captures(url);
CREATE INDEX IF NOT EXISTS captures_app ON captures(app_name);
CREATE INDEX IF NOT EXISTS captures_time ON captures(captured_at);
"""


@dataclass(frozen=True)
class CaptureRow:
    sha256: str
    path: str
    captured_at: str
    app_class: str
    app_name: str
    window_title: str
    geometry: str
    url: str | None
    page_title: str | None
    note: str
    source: str


class Index:
    def __init__(self, dirfd: int, fd: int, conn: sqlite3.Connection) -> None:
        self._dirfd = dirfd
        self._fd = fd
        self._conn = conn

    def close(self) -> None:
        try:
            self._conn.close()
        finally:
            try:
                os.close(self._fd)
            except OSError:
                pass
            try:
                os.close(self._dirfd)
            except OSError:
                pass

    def __enter__(self) -> "Index":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def upsert(self, row: CaptureRow) -> None:
        checked = _validate_row(row)
        self._conn.execute(
            """
            INSERT INTO captures (
              sha256, path, captured_at, app_class, app_name, window_title,
              geometry, url, page_title, note, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sha256) DO UPDATE SET
              path=excluded.path,
              captured_at=excluded.captured_at,
              app_class=excluded.app_class,
              app_name=excluded.app_name,
              window_title=excluded.window_title,
              geometry=excluded.geometry,
              url=excluded.url,
              page_title=excluded.page_title,
              note=excluded.note,
              source=excluded.source
            """,
            (
                checked.sha256,
                checked.path,
                checked.captured_at,
                checked.app_class,
                checked.app_name,
                checked.window_title,
                checked.geometry,
                checked.url,
                checked.page_title,
                checked.note,
                checked.source,
            ),
        )

    def get(self, sha256: str) -> CaptureRow | None:
        if len(sha256) != MAX_SHA256_HEX or any(c not in "0123456789abcdef" for c in sha256):
            raise CasError("bad sha256")
        cur = self._conn.execute("SELECT * FROM captures WHERE sha256 = ?", (sha256,))
        item = cur.fetchone()
        return _row_from_sql(item) if item else None

    def search(
        self,
        *,
        query: str = "",
        url: str | None = None,
        app: str | None = None,
        limit: int = MAX_SEARCH_ROWS,
    ) -> list[CaptureRow]:
        if limit < 1 or limit > MAX_SEARCH_ROWS:
            limit = MAX_SEARCH_ROWS
        clauses: list[str] = []
        args: list[object] = []
        if query:
            if len(query) > MAX_SEARCH_QUERY:
                raise CasError("search query too long")
            like = _like_contains(query)
            clauses.append(
                "(note LIKE ? ESCAPE '\\' OR path LIKE ? ESCAPE '\\' "
                "OR IFNULL(url,'') LIKE ? ESCAPE '\\' "
                "OR window_title LIKE ? ESCAPE '\\')"
            )
            args.extend([like, like, like, like])
        if url:
            if len(url) > MAX_URL_BYTES:
                raise CasError("url pattern too long")
            if any(ord(ch) < 32 for ch in url):
                raise CasError("url pattern has controls")
            clauses.append("IFNULL(url,'') LIKE ? ESCAPE '\\'")
            args.append(url.replace("\\", "\\\\"))
        if app:
            token = app.strip().lower()
            if len(token) > 32 or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789-" for ch in token):
                raise CasError("bad app filter")
            clauses.append("app_name = ?")
            args.append(token)
        sql = "SELECT * FROM captures"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY captured_at DESC LIMIT ?"
        args.append(limit)
        cur = self._conn.execute(sql, args)
        return [_row_from_sql(item) for item in cur.fetchall()]


def open_index() -> Index:
    dirfd = open_dir_chain(INDEX_PARTS, private=True, create=True)
    try:
        return _open_index_at(dirfd)
    except BaseException:
        os.close(dirfd)
        raise


def open_index_at(dirfd: int) -> Index:
    """Test helper: caller keeps ownership of dirfd; we dup it."""
    dup = os.dup(dirfd)
    try:
        return _open_index_at(dup)
    except BaseException:
        os.close(dup)
        raise


def _open_index_at(dirfd: int) -> Index:
    try:
        fd = os.open(
            INDEX_NAME,
            os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=dirfd,
        )
    except FileNotFoundError:
        fd = os.open(
            INDEX_NAME,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=dirfd,
        )
        os.fchmod(fd, 0o600)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid() or st.st_nlink != 1:
            raise CasError("refusing index database")
        if st.st_mode & 0o077:
            os.fchmod(fd, 0o600)
        uri = f"file:/proc/self/fd/{fd}?mode=rw"
        conn = sqlite3.connect(uri, uri=True, isolation_level=None, timeout=SQLITE_TIMEOUT_S)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=MEMORY")
            conn.execute("PRAGMA synchronous=FULL")
            conn.execute("PRAGMA temp_store=MEMORY")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.executescript(SCHEMA)
        except BaseException:
            conn.close()
            raise
        return Index(dirfd, fd, conn)
    except BaseException:
        os.close(fd)
        raise


def _like_contains(query: str) -> str:
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _validate_row(row: CaptureRow) -> CaptureRow:
    sha = row.sha256.lower()
    if len(sha) != MAX_SHA256_HEX or any(c not in "0123456789abcdef" for c in sha):
        raise CasError("bad sha256")
    if not row.path or len(row.path) > MAX_PATH or "\x00" in row.path:
        raise CasError("bad path")
    if not os.path.isabs(row.path):
        raise CasError("path must be absolute")
    note = clean_note(row.note)
    if len(note) > MAX_NOTE_CHARS:
        raise CasError("note too long")
    url = parse_stored_url(row.url) if row.url else None
    source = row.source if row.source in ("clipboard", "none") else "none"
    if len(source) > MAX_SOURCE:
        source = "none"
    title = clean_title(row.window_title, MAX_TITLE)
    page = clean_title(row.page_title or "", MAX_TITLE) or None
    geometry = row.geometry.strip()
    if len(geometry) > MAX_GEOMETRY:
        raise CasError("geometry too long")
    cls = row.app_class.strip()[:MAX_CLASS]
    name = row.app_name.strip()[:32]
    captured = row.captured_at.strip()[:64]
    return CaptureRow(
        sha256=sha,
        path=row.path,
        captured_at=captured,
        app_class=cls,
        app_name=name,
        window_title=title,
        geometry=geometry,
        url=url,
        page_title=page,
        note=note,
        source=source if url else "none",
    )


def _row_from_sql(item: sqlite3.Row) -> CaptureRow:
    return CaptureRow(
        sha256=str(item["sha256"]),
        path=str(item["path"]),
        captured_at=str(item["captured_at"]),
        app_class=str(item["app_class"]),
        app_name=str(item["app_name"]),
        window_title=str(item["window_title"]),
        geometry=str(item["geometry"]),
        url=item["url"],
        page_title=item["page_title"],
        note=str(item["note"] or ""),
        source=str(item["source"]),
    )


def iter_rows(index: Index) -> Iterator[CaptureRow]:
    yield from index.search(limit=MAX_SEARCH_ROWS)
