"""Desktop notifications with stripped text. No stored --exec actions."""

from __future__ import annotations

from cas.bounds import MAX_NOTIFY, NOTIFY_TIMEOUT_S
from cas.proc import run_cmd
from cas.text import plain


def send(summary: str, body: str = "") -> None:
    summary_p = plain(summary, MAX_NOTIFY) or "Screenshot"
    body_p = plain(body, MAX_NOTIFY)
    argv = [
        "/usr/share/omarchy/bin/omarchy-notification-send",
        "-t",
        "2000",
        summary_p,
        body_p,
    ]
    try:
        run_cmd(argv, timeout=NOTIFY_TIMEOUT_S, max_stdout=4096, ok_exit=(0, 1))
        return
    except Exception:
        pass
    try:
        run_cmd(
            ["/usr/bin/notify-send", "--", summary_p, body_p],
            timeout=NOTIFY_TIMEOUT_S,
            max_stdout=4096,
            ok_exit=(0, 1),
        )
    except Exception:
        return
