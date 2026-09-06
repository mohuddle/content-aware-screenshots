"""Post-capture GTK4 note dialog. Caps at 500 characters. Does not fetch URLs."""

from __future__ import annotations

from cas.bounds import MAX_NOTE_CHARS, MAX_URL_BYTES
from cas.browsers import Browser
from cas.text import clean_note, plain
from cas.urls import parse_stored_url

APP_ID = "local.omarchy.cas.note"
WIN_TITLE = "Screenshot note"


def run_note_dialog(
    *,
    show_url_hint: bool,
    app_name: str,
    window_title: str = "",
    session_browser: Browser | None = None,
) -> tuple[str, str | None]:
    """Return (note, url). Skip/Esc yields empty note and no URL."""
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        gi.require_version("Gdk", "4.0")
        gi.require_version("Gio", "2.0")
        from gi.repository import Gdk, Gio, GLib, Gtk
    except (ImportError, ValueError):
        return "", None

    result: dict[str, str | None] = {"note": "", "url": None}
    url_user_edited = {"value": False}

    app = Gtk.Application(
        application_id=APP_ID,
        flags=Gio.ApplicationFlags.NON_UNIQUE,
    )

    def on_activate(_app: Gtk.Application) -> None:
        win = Gtk.ApplicationWindow(application=app)
        win.set_title(WIN_TITLE)
        win.set_default_size(560, 420 if session_browser else 380)
        win.set_modal(True)
        win.set_resizable(False)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(14)
        box.set_margin_bottom(14)
        box.set_margin_start(14)
        box.set_margin_end(14)
        win.set_child(box)

        heading = Gtk.Label(label=f"Note for {plain(app_name, 32)} screenshot")
        heading.set_xalign(0)
        heading.set_wrap(True)
        heading.set_use_markup(False)
        box.append(heading)

        counter = Gtk.Label(label=f"0 / {MAX_NOTE_CHARS}")
        counter.set_xalign(1)
        counter.set_use_markup(False)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_min_content_height(120)
        view = Gtk.TextView()
        view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        view.set_accepts_tab(False)
        buf = view.get_buffer()
        scrolled.set_child(view)
        box.append(scrolled)
        box.append(counter)

        url_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        url_entry = Gtk.Entry()
        url_entry.set_placeholder_text("https://…")
        url_entry.set_max_length(MAX_URL_BYTES)
        url_entry.set_hexpand(True)
        paste_btn = Gtk.Button(label="Paste URL")
        url_row.append(url_entry)
        url_row.append(paste_btn)

        if show_url_hint:
            hint = Gtk.Label(
                label="Browser: Alt+D then copy, or Alt+Shift+L (Copy URL), then Paste URL. Esc skips."
            )
            hint.set_wrap(True)
            hint.set_xalign(0)
            hint.set_use_markup(False)
            box.append(hint)
        else:
            optional = Gtk.Label(label="URL (optional). Esc skips the note.")
            optional.set_xalign(0)
            optional.set_use_markup(False)
            box.append(optional)
        box.append(url_row)

        status = Gtk.Label(label="")
        status.set_xalign(0)
        status.set_wrap(True)
        status.set_use_markup(False)

        if session_browser is not None:
            session_check = Gtk.CheckButton(
                label=f"Use current {session_browser.label} tab URL"
            )
            session_check.set_active(False)
            box.append(session_check)
            box.append(status)

            def on_session_toggle(btn: Gtk.CheckButton) -> None:
                if not btn.get_active():
                    status.set_text("")
                    return
                from cas.session import active_tab_url

                found = active_tab_url(session_browser, window_title=window_title)
                if found:
                    url_entry.set_text(found)
                    url_user_edited["value"] = True
                    status.set_text("")
                else:
                    status.set_text(
                        f"No current {session_browser.label} tab URL in the local session file."
                    )

            session_check.connect("toggled", on_session_toggle)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        buttons.set_halign(Gtk.Align.END)
        skip_btn = Gtk.Button(label="Skip")
        save_btn = Gtk.Button(label="Save")
        save_btn.add_css_class("suggested-action")
        buttons.append(skip_btn)
        buttons.append(save_btn)
        box.append(buttons)

        def note_text() -> str:
            start, end = buf.get_bounds()
            return buf.get_text(start, end, False)

        def update_counter(*_args: object) -> None:
            n = len(note_text())
            counter.set_text(f"{n} / {MAX_NOTE_CHARS}")

        inserting = {"on": False}

        def on_insert(buffer: Gtk.TextBuffer, loc: object, text: str, _length: int) -> None:
            if inserting["on"]:
                return
            incoming = text if isinstance(text, str) else ""
            current = buffer.get_char_count()
            allowed = MAX_NOTE_CHARS - current
            if len(incoming) <= allowed:
                return
            buffer.stop_emission_by_name("insert-text")
            if allowed > 0:
                inserting["on"] = True
                try:
                    buffer.insert(loc, incoming[:allowed])
                finally:
                    inserting["on"] = False

        buf.connect("insert-text", on_insert)
        buf.connect("changed", update_counter)

        def commit(save: bool) -> None:
            if save:
                result["note"] = clean_note(note_text())
                result["url"] = parse_stored_url(url_entry.get_text())
            win.hide()
            GLib.idle_add(app.quit)

        def fill_url(raw: str) -> None:
            if url_user_edited["value"] and url_entry.get_text().strip():
                return
            parsed = parse_stored_url(raw)
            if parsed:
                url_entry.set_text(parsed)

        def on_url_changed(_entry: Gtk.Entry) -> None:
            url_user_edited["value"] = True

        url_entry.connect("changed", on_url_changed)

        display = Gdk.Display.get_default()
        clip = display.get_clipboard() if display is not None else None

        def on_text_ready(_clip: object, res: object) -> None:
            if clip is None:
                return
            try:
                text = clip.read_text_finish(res)
            except Exception:
                return
            if text:
                fill_url(text)

        def request_clipboard_text() -> None:
            if clip is None:
                return
            if url_user_edited["value"] and url_entry.get_text().strip():
                return
            clip.read_text_async(None, on_text_ready)

        def paste_url(*_args: object) -> None:
            url_user_edited["value"] = False
            request_clipboard_text()

        paste_btn.connect("clicked", paste_url)
        if clip is not None:
            clip.connect("changed", lambda *_: request_clipboard_text())
            GLib.idle_add(request_clipboard_text)

        save_btn.connect("clicked", lambda *_: commit(True))
        skip_btn.connect("clicked", lambda *_: commit(False))

        key = Gtk.EventControllerKey()

        def on_key(_ctl: object, keyval: int, _code: int, state: Gdk.ModifierType) -> bool:
            if keyval == Gdk.KEY_Escape:
                commit(False)
                return True
            if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and state & Gdk.ModifierType.CONTROL_MASK:
                commit(True)
                return True
            return False

        key.connect("key-pressed", on_key)
        win.add_controller(key)
        win.connect("close-request", lambda *_: (commit(False), False)[1])
        win.present()
        view.grab_focus()

    app.connect("activate", on_activate)
    app.run(None)
    return result["note"] or "", result["url"]
