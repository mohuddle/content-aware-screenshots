"""Compatibility wrapper. Prefer cas.session.active_tab_url."""

from cas.browsers import BRAVE
from cas.chromium_session import active_tab_url as _chromium_url
from cas.chromium_session import parse_active_tab_url

__all__ = ["active_tab_url", "parse_active_tab_url"]


def active_tab_url(*, window_title: str = "") -> str | None:
    return _chromium_url(root_parts=BRAVE.root_parts, window_title=window_title)
