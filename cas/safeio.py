"""Descriptor-bound reads and atomic writes. Never re-resolve a pathname."""

from __future__ import annotations

import os
import stat

from cas import CasError


def read_bounded_fd(fd: int, max_bytes: int) -> bytes:
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode):
        raise CasError("not a regular file")
    if st.st_nlink != 1:
        raise CasError("refusing file with extra links")
    if st.st_size > max_bytes:
        raise CasError("file exceeds size limit")
    try:
        os.set_blocking(fd, True)
    except OSError:
        pass
    data = b""
    while len(data) <= max_bytes:
        chunk = os.read(fd, min(65536, max_bytes + 1 - len(data)))
        if not chunk:
            break
        data += chunk
    if len(data) > max_bytes:
        raise CasError("file grew past the limit")
    return data


def read_bounded_name(dirfd: int, name: str, max_bytes: int, *, owner_only: bool = False) -> bytes | None:
    if name in (".", "..") or "/" in name or "\\" in name:
        raise CasError("bad file name")
    try:
        fd = os.open(
            name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
            dir_fd=dirfd,
        )
    except FileNotFoundError:
        return None
    try:
        st = os.fstat(fd)
        if st.st_uid != os.geteuid():
            raise CasError("refusing file owned by another user")
        if owner_only and (st.st_mode & 0o077):
            raise CasError("refusing group/other-accessible file")
        return read_bounded_fd(fd, max_bytes)
    finally:
        os.close(fd)


def write_atomic(dirfd: int, name: str, data: bytes, *, mode: int = 0o600) -> None:
    if name in (".", "..") or "/" in name or "\\" in name or name.startswith("."):
        raise CasError("bad file name")
    tmp = f".{name}.{os.urandom(8).hex()}.tmp"
    fd = os.open(
        tmp,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
        mode,
        dir_fd=dirfd,
    )
    try:
        os.fchmod(fd, mode)
        view = memoryview(data)
        while view:
            n = os.write(fd, view)
            if n <= 0:
                raise CasError("short write")
            view = view[n:]
        os.fsync(fd)
        os.rename(tmp, name, src_dir_fd=dirfd, dst_dir_fd=dirfd)
        tmp = ""
        os.fsync(dirfd)
    except BaseException:
        if tmp:
            try:
                os.unlink(tmp, dir_fd=dirfd)
            except OSError:
                pass
        raise
    finally:
        os.close(fd)


def open_exclusive(dirfd: int, name: str, *, mode: int = 0o644) -> int:
    if name in (".", "..") or "/" in name or "\\" in name or name.startswith("."):
        raise CasError("bad file name")
    fd = os.open(
        name,
        os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
        mode,
        dir_fd=dirfd,
    )
    try:
        os.fchmod(fd, mode)
        return fd
    except BaseException:
        os.close(fd)
        try:
            os.unlink(name, dir_fd=dirfd)
        except OSError:
            pass
        raise


def name_exists(dirfd: int, name: str) -> bool:
    try:
        st = os.lstat(name, dir_fd=dirfd)
    except FileNotFoundError:
        return False
    return True if st else True


def sha256_fd(fd: int, max_bytes: int) -> str:
    import hashlib

    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
        raise CasError("refusing hash of non-regular file")
    if st.st_size > max_bytes:
        raise CasError("file exceeds size limit")
    os.lseek(fd, 0, os.SEEK_SET)
    h = hashlib.sha256()
    remaining = max_bytes + 1
    while remaining > 0:
        chunk = os.read(fd, min(65536, remaining))
        if not chunk:
            break
        h.update(chunk)
        remaining -= len(chunk)
    if remaining <= 0:
        raise CasError("file grew past the limit")
    os.lseek(fd, 0, os.SEEK_SET)
    return h.hexdigest()
