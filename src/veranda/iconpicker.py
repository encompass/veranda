"""A searchable picker for choosing a themed icon for a button."""

from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gtk  # noqa: E402

# A curated set of broadly-useful symbolic icons shown before searching.
CURATED = [
    "media-playback-start-symbolic", "media-playback-pause-symbolic",
    "media-playback-stop-symbolic", "media-skip-forward-symbolic",
    "media-skip-backward-symbolic", "media-seek-forward-symbolic",
    "audio-volume-high-symbolic", "audio-volume-low-symbolic",
    "audio-volume-muted-symbolic", "microphone-sensitivity-high-symbolic",
    "microphone-sensitivity-muted-symbolic", "camera-photo-symbolic",
    "camera-web-symbolic", "video-display-symbolic", "display-brightness-symbolic",
    "utilities-terminal-symbolic", "web-browser-symbolic", "mail-send-symbolic",
    "mail-unread-symbolic", "chat-message-new-symbolic", "user-trash-symbolic",
    "edit-copy-symbolic", "edit-paste-symbolic", "edit-cut-symbolic",
    "edit-undo-symbolic", "edit-redo-symbolic", "edit-delete-symbolic",
    "document-save-symbolic", "document-open-symbolic", "document-new-symbolic",
    "document-edit-symbolic", "folder-symbolic", "starred-symbolic",
    "non-starred-symbolic", "emblem-favorite-symbolic", "system-search-symbolic",
    "go-home-symbolic", "go-previous-symbolic", "go-next-symbolic",
    "go-up-symbolic", "go-down-symbolic", "list-add-symbolic",
    "list-remove-symbolic", "view-refresh-symbolic", "open-menu-symbolic",
    "window-close-symbolic", "zoom-in-symbolic", "zoom-out-symbolic",
    "input-keyboard-symbolic", "input-gaming-symbolic", "printer-symbolic",
    "phone-symbolic", "computer-symbolic", "network-wireless-symbolic",
    "bluetooth-symbolic", "network-vpn-symbolic", "system-shutdown-symbolic",
    "system-lock-screen-symbolic", "system-log-out-symbolic",
    "preferences-system-symbolic", "accessories-calculator-symbolic",
    "x-office-calendar-symbolic", "alarm-symbolic", "appointment-soon-symbolic",
    "face-smile-symbolic", "help-about-symbolic", "dialog-information-symbolic",
    "dialog-warning-symbolic", "security-high-symbolic", "weather-clear-symbolic",
    "weather-clear-night-symbolic", "applications-games-symbolic",
    "applications-multimedia-symbolic", "applications-graphics-symbolic",
    "power-profile-performance-symbolic", "view-grid-symbolic",
]

MAX_RESULTS = 300


class IconPicker(Adw.Dialog):
    """Pick a themed icon name. Calls ``on_pick(name)`` on selection."""

    def __init__(self, on_pick: Callable[[str], None]) -> None:
        super().__init__()
        self._on_pick = on_pick
        self.set_title("Choose an Icon")
        self.set_content_width(520)
        self.set_content_height(560)

        self._theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        self._all_names = sorted(set(self._theme.get_icon_names()))
        self._curated = [n for n in CURATED if self._theme.has_icon(n)]

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        toolbar.add_top_bar(header)

        search_bar = Gtk.SearchBar()
        self._search = Gtk.SearchEntry(hexpand=True, placeholder_text="Search icons…")
        self._search.connect("search-changed", self._on_search)
        search_bar.set_child(self._search)
        search_bar.set_search_mode(True)
        search_bar.set_key_capture_widget(self)
        toolbar.add_top_bar(search_bar)

        self._flow = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE,
            homogeneous=True,
            max_children_per_line=8,
            min_children_per_line=4,
            row_spacing=6,
            column_spacing=6,
            margin_top=12,
            margin_bottom=12,
            margin_start=12,
            margin_end=12,
            valign=Gtk.Align.START,
        )
        scroller = Gtk.ScrolledWindow(
            hexpand=True, vexpand=True, child=self._flow
        )
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        toolbar.set_content(scroller)

        self.set_child(toolbar)
        self._populate(self._curated)

    def _on_search(self, entry: Gtk.SearchEntry) -> None:
        text = entry.get_text().strip().lower()
        if not text:
            self._populate(self._curated)
            return
        matches = [n for n in self._all_names if text in n.lower()][:MAX_RESULTS]
        self._populate(matches)

    def _populate(self, names: list[str]) -> None:
        child = self._flow.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._flow.remove(child)
            child = nxt
        for name in names:
            self._flow.append(self._make_cell(name))

    def _make_cell(self, name: str) -> Gtk.Widget:
        button = Gtk.Button()
        button.add_css_class("flat")
        button.set_tooltip_text(name)
        image = Gtk.Image.new_from_icon_name(name)
        image.set_pixel_size(32)
        button.set_child(image)
        button.connect("clicked", self._on_cell_clicked, name)
        return button

    def _on_cell_clicked(self, _button, name: str) -> None:
        self._on_pick(name)
        self.close()
