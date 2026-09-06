"""Held-descriptor directory walks from $HOME. Index dirs stay 0700."""

from __future__ import annotations

import errno
import os
import re
import stat

from cas import CasError

COMPONENT_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_DOT_CONFIG_OK = re.compile(r"^[A-Za-z0-9._-]+$")


def home_dir() -> str:
    home = os.environ.get("HOME") or os.path.expanduser("~")
    if not home or not os.path.isabs(home):
        raise CasError("HOME is not an absolute path")
    return home


def _check_component(name: str) -> None:
    if name in (".", "..") or "/" in name or "\\" in name or not name:
        raise CasError("bad path component")
    if name.startswith(".") and name not in (".local", ".config"):
        # Hidden components we create ourselves.
        if not COMPONENT_RE.fullmatch(name.lstrip(".")):
            raise CasError("bad path component")
        return
    if not COMPONENT_RE.fullmatch(name) and not _DOT_CONFIG_OK.fullmatch(name):
        raise CasError("bad path component")


def _fstat_dir(fd: int, *, private: bool) -> None:
    st = os.fstat(fd)
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.geteuid():
        raise CasError("untrusted directory")
    if private and (st.st_mode & 0o077):
        os.fchmod(fd, 0o700)


def open_dir_chain(
    parts: tuple[str, ...],
    *,
    private: bool,
    create: bool = True,
    follow_user_symlink: bool = False,
) -> int:
    """Walk from $HOME with held descriptors. Returns the final dirfd."""
    if not parts:
        raise CasError("empty directory chain")
    home = home_dir()
    fd = os.open(home, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        last = len(parts) - 1
        for i, name in enumerate(parts):
            _check_component(name)
            nfd = _open_component(
                fd,
                name,
                private=private and i == last,
                create=create,
                follow_user_symlink=follow_user_symlink and not private,
            )
            os.close(fd)
            fd = nfd
        _fstat_dir(fd, private=private)
        return fd
    except BaseException:
        os.close(fd)
        raise


def _open_component(
    parent_fd: int,
    name: str,
    *,
    private: bool,
    create: bool,
    follow_user_symlink: bool,
) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        nfd = os.open(name, flags, dir_fd=parent_fd)
    except FileNotFoundError:
        if not create:
            raise
        mode = 0o700 if private else 0o755
        os.mkdir(name, mode, dir_fd=parent_fd)
        nfd = os.open(name, flags, dir_fd=parent_fd)
    except OSError as exc:
        if not follow_user_symlink or exc.errno != errno.ELOOP:
            raise
        st = os.lstat(name, dir_fd=parent_fd)
        if not stat.S_ISLNK(st.st_mode) or st.st_uid != os.geteuid():
            raise CasError("refusing directory symlink") from exc
        nfd = os.open(
            name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC,
            dir_fd=parent_fd,
        )
        stt = os.fstat(nfd)
        if not stat.S_ISDIR(stt.st_mode) or stt.st_uid != os.geteuid():
            os.close(nfd)
            raise CasError("symlink target is not a user directory")
        return nfd
    try:
        _fstat_dir(nfd, private=private)
        return nfd
    except BaseException:
        os.close(nfd)
        raise


def xdg_pictures_parts() -> tuple[str, ...]:
    """Return path parts under $HOME for the pictures directory."""
    configured = os.environ.get("OMARCHY_SCREENSHOT_DIR", "").strip()
    if configured:
        return _parts_under_home(configured)
    home = home_dir()
    # Optional user-dirs.dirs; ignore if missing or hostile.
    try:
        cfg_fd = open_dir_chain((".config",), private=False, create=False, follow_user_symlink=True)
    except (FileNotFoundError, CasError, OSError):
        return ("Pictures",)
    try:
        raw = _read_user_dirs(cfg_fd)
    finally:
        os.close(cfg_fd)
    if raw:
        return raw
    if os.path.isdir(os.path.join(home, "Pictures")):
        return ("Pictures",)
    return ("Pictures",)


def _parts_under_home(path: str) -> tuple[str, ...]:
    home = home_dir()
    if not os.path.isabs(path):
        raise CasError("screenshot directory must be absolute")
    real_home = os.path.realpath(home)
    # Do not resolve the target (symlink Pictures is allowed later). Compare prefix on the given path.
    home_slash = home.rstrip("/") + "/"
    if path.rstrip("/") != home.rstrip("/") and not path.startswith(home_slash):
        if not path.startswith(real_home.rstrip("/") + "/"):
            raise CasError("screenshot directory is outside HOME")
        rel = path[len(real_home.rstrip("/")) + 1 :]
    else:
        rel = path[len(home.rstrip("/")) + 1 :]
    parts = tuple(p for p in rel.split("/") if p)
    if not parts:
        raise CasError("screenshot directory is HOME itself")
    for part in parts:
        _check_component(part)
    return parts


def _read_user_dirs(cfg_fd: int) -> tuple[str, ...] | None:
    from cas.safeio import read_bounded_name

    try:
        data = read_bounded_name(cfg_fd, "user-dirs.dirs", max_bytes=8192)
    except (FileNotFoundError, CasError, OSError):
        return None
    if data is None:
        return None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    home = home_dir()
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("XDG_PICTURES_DIR="):
            continue
        value = line.split("=", 1)[1].strip().strip('"')
        value = value.replace("$HOME", home)
        if not value.startswith(home):
            return None
        try:
            return _parts_under_home(value)
        except CasError:
            return None
    return None
