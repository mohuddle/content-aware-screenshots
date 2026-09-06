"""Bounded hyprctl JSON. Window titles are untrusted input."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from cas import CasError
from cas.bounds import (
    BROWSER_CLASSES,
    HYPR_TIMEOUT_S,
    MAX_CLASS,
    MAX_CLIENTS,
    MAX_HYPR_JSON,
    MAX_TITLE,
)
from cas.proc import run_cmd
from cas.text import clean_title

GEO_RE = re.compile(r"^(-?\d{1,6}),(-?\d{1,6}) (\d{1,6})x(\d{1,6})$")
HYPRCTL = "/usr/bin/hyprctl"


@dataclass(frozen=True)
class WindowInfo:
    cls: str
    title: str
    x: int
    y: int
    w: int
    h: int
    focused: bool

    @property
    def geometry(self) -> str:
        return f"{self.x},{self.y} {self.w}x{self.h}"

    def is_browser(self) -> bool:
        return self.cls.lower() in BROWSER_CLASSES


@dataclass(frozen=True)
class Snapshot:
    focused: WindowInfo | None
    clients: tuple[WindowInfo, ...]
    cursor: tuple[int, int] | None


def parse_geometry(text: str) -> tuple[int, int, int, int]:
    match = GEO_RE.fullmatch(text.strip())
    if not match:
        raise CasError("invalid region geometry")
    x, y, w, h = (int(match.group(i)) for i in range(1, 5))
    if w <= 0 or h <= 0 or w * h < 1:
        raise CasError("empty region")
    if w > 100000 or h > 100000:
        raise CasError("region too large")
    return x, y, w, h


def _hypr(*args: str) -> object:
    raw = run_cmd(
        [HYPRCTL, *args],
        timeout=HYPR_TIMEOUT_S,
        max_stdout=MAX_HYPR_JSON,
    )
    if len(raw) > MAX_HYPR_JSON:
        raise CasError("hyprctl output too large")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CasError("hyprctl returned invalid JSON") from exc


def _window_from_obj(obj: object, *, focused: bool) -> WindowInfo | None:
    if not isinstance(obj, dict):
        return None
    at = obj.get("at")
    size = obj.get("size")
    if not (isinstance(at, list) and isinstance(size, list) and len(at) == 2 and len(size) == 2):
        return None
    try:
        x, y = int(at[0]), int(at[1])
        w, h = int(size[0]), int(size[1])
    except (TypeError, ValueError):
        return None
    if w <= 0 or h <= 0:
        return None
    cls = clean_title(str(obj.get("class") or "unknown"), MAX_CLASS)
    if not cls:
        cls = "unknown"
    title = clean_title(str(obj.get("title") or ""), MAX_TITLE)
    hidden = obj.get("hidden") is True
    mapped = obj.get("mapped", True)
    if hidden or mapped is False:
        return None
    return WindowInfo(cls=cls, title=title, x=x, y=y, w=w, h=h, focused=focused)


def snapshot() -> Snapshot:
    focused_raw = _hypr("activewindow", "-j")
    clients_raw = _hypr("clients", "-j")
    cursor = None
    try:
        pos = run_cmd(
            [HYPRCTL, "cursorpos"],
            timeout=HYPR_TIMEOUT_S,
            max_stdout=64,
        ).decode("utf-8").strip()
        if "," in pos:
            xs, ys = pos.split(",", 1)
            cursor = (int(xs.strip()), int(ys.strip()))
    except (CasError, ValueError):
        cursor = None

    focused = _window_from_obj(focused_raw, focused=True)
    clients: list[WindowInfo] = []
    if isinstance(clients_raw, list):
        for item in clients_raw[:MAX_CLIENTS]:
            win = _window_from_obj(item, focused=False)
            if win is None:
                continue
            if focused and win.x == focused.x and win.y == focused.y and win.w == focused.w and win.h == focused.h and win.cls == focused.cls:
                clients.append(
                    WindowInfo(
                        cls=win.cls,
                        title=win.title,
                        x=win.x,
                        y=win.y,
                        w=win.w,
                        h=win.h,
                        focused=True,
                    )
                )
            else:
                clients.append(win)
    if len(clients) > MAX_CLIENTS:
        raise CasError("too many windows")
    return Snapshot(focused=focused, clients=tuple(clients), cursor=cursor)


def match_region(geo: str, snap: Snapshot) -> WindowInfo:
    x, y, w, h = parse_geometry(geo)
    best: WindowInfo | None = None
    best_area = 0
    for win in snap.clients:
        ix = max(x, win.x)
        iy = max(y, win.y)
        ax = min(x + w, win.x + win.w)
        ay = min(y + h, win.y + win.h)
        if ax <= ix or ay <= iy:
            continue
        area = (ax - ix) * (ay - iy)
        if area > best_area or (area == best_area and win.focused):
            best = win
            best_area = area
    if best is not None:
        return best
    if snap.focused is not None:
        return snap.focused
    return WindowInfo(cls="unknown", title="", x=x, y=y, w=w, h=h, focused=False)


def slurp_rects(snap: Snapshot) -> bytes:
    lines = [win.geometry.encode("ascii") for win in snap.clients]
    return b"\n".join(lines) + (b"\n" if lines else b"")


def warp_to_focused(snap: Snapshot) -> None:
    win = snap.focused
    if win is None:
        return
    cx = win.x + win.w // 2
    cy = win.y + win.h // 2
    if abs(cx) > 100000 or abs(cy) > 100000:
        return
    try:
        run_cmd(
            [HYPRCTL, "dispatch", "movecursor", str(cx), str(cy)],
            timeout=HYPR_TIMEOUT_S,
            max_stdout=4096,
            ok_exit=(0, 1),
        )
    except CasError:
        return
