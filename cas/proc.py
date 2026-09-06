"""Bounded subprocesses: absolute binaries, session, deadline, byte cap."""

from __future__ import annotations

import os
import select
import signal
import subprocess
import time
from typing import Mapping

from cas import CasError
from cas.bounds import ALLOWED_BIN_PREFIXES, MAX_PROC_STDOUT, MAX_STDERR


def minimal_env() -> dict[str, str]:
    keep = (
        "HOME",
        "USER",
        "LOGNAME",
        "XDG_RUNTIME_DIR",
        "WAYLAND_DISPLAY",
        "XDG_SESSION_TYPE",
        "HYPRLAND_INSTANCE_SIGNATURE",
        "XDG_CURRENT_DESKTOP",
        "LANG",
        "DISPLAY",
    )
    env: dict[str, str] = {}
    for key in keep:
        val = os.environ.get(key)
        if val:
            env[key] = val
    runtime = env.get("XDG_RUNTIME_DIR")
    if not runtime or not runtime.startswith("/run/user/"):
        raise CasError("XDG_RUNTIME_DIR is missing or not a /run/user path")
    env["PATH"] = "/usr/bin:/usr/share/omarchy/bin"
    env["LC_ALL"] = "C.UTF-8"
    env["PYTHONSAFEPATH"] = "1"
    return env


def _check_argv(argv: list[str]) -> None:
    if not argv:
        raise CasError("empty command")
    prog = argv[0]
    if not os.path.isabs(prog) or not any(prog.startswith(p) for p in ALLOWED_BIN_PREFIXES):
        raise CasError("refusing executable outside allowed prefixes")
    if ".." in prog.split("/"):
        raise CasError("refusing executable path")


def run_cmd(
    argv: list[str],
    *,
    timeout: float,
    max_stdout: int = MAX_PROC_STDOUT,
    stdin: bytes | None = None,
    env: Mapping[str, str] | None = None,
    ok_exit: tuple[int, ...] = (0,),
) -> bytes:
    _check_argv(argv)
    try:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=dict(env) if env is not None else minimal_env(),
            start_new_session=True,
        )
    except OSError as exc:
        raise CasError(f"cannot start {argv[0]}") from exc
    try:
        stdout, stderr = _communicate_capped(proc, stdin, timeout, max_stdout)
    except BaseException:
        _kill_group(proc)
        raise
    finally:
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            if stream is None:
                continue
            try:
                stream.close()
            except OSError:
                pass
    if len(stdout) > max_stdout:
        raise CasError("command output exceeds limit")
    if proc.returncode not in ok_exit:
        err = (stderr or b"").decode("utf-8", "replace")[:MAX_STDERR]
        raise CasError(err or f"{argv[0]} exited {proc.returncode}")
    return stdout


def spawn_session(argv: list[str], *, env: Mapping[str, str] | None = None) -> subprocess.Popen[bytes]:
    _check_argv(argv)
    return subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=dict(env) if env is not None else minimal_env(),
        start_new_session=True,
    )


def _communicate_capped(
    proc: subprocess.Popen[bytes],
    stdin: bytes | None,
    timeout: float,
    max_stdout: int,
) -> tuple[bytes, bytes]:
    assert proc.stdout is not None and proc.stderr is not None
    if stdin is not None:
        assert proc.stdin is not None
        try:
            proc.stdin.write(stdin)
        except BrokenPipeError:
            pass
        try:
            proc.stdin.close()
        except OSError:
            pass
    elif proc.stdin is not None:
        proc.stdin.close()
    out_fd = proc.stdout.fileno()
    err_fd = proc.stderr.fileno()
    open_fds = {out_fd, err_fd}
    stdout = b""
    stderr = b""
    deadline = time.monotonic() + timeout
    while open_fds:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise CasError("command timed out")
        ready, _, _ = select.select(list(open_fds), [], [], remaining)
        if not ready:
            raise CasError("command timed out")
        for fd in ready:
            chunk = os.read(fd, 65536)
            if not chunk:
                open_fds.discard(fd)
                continue
            if fd == out_fd:
                stdout += chunk
                if len(stdout) > max_stdout:
                    raise CasError("command output exceeds limit")
            else:
                stderr += chunk
                if len(stderr) > MAX_STDERR + 1:
                    stderr = stderr[: MAX_STDERR + 1]
    proc.wait(timeout=1)
    return stdout, stderr


def _kill_group(proc: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
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
