"""Dispatch session-file URL lookup by identified browser."""

from __future__ import annotations

from cas.browsers import Browser


def active_tab_url(browser: Browser, *, window_title: str = "") -> str | None:
    if browser.kind == "chromium":
        from cas.chromium_session import active_tab_url as chromium_url

        return chromium_url(root_parts=browser.root_parts, window_title=window_title)
    if browser.kind == "firefox":
        from cas.firefox_session import active_tab_url as firefox_url

        return firefox_url(root_parts=browser.root_parts, window_title=window_title)
    return None
