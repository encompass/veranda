"""A collapsible left-sidebar section: a clickable header (disclosure arrow +
title) with an optional add button, over a revealer holding the content."""

from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402


class CollapsibleSection(Gtk.Box):
    def __init__(
        self,
        title: str,
        on_add: Callable[[], None] | None = None,
        add_tooltip: str = "",
        vexpand: bool = False,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("sidebar-section")

        header = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            margin_top=8, margin_bottom=2, margin_start=6, margin_end=6,
        )
        self._arrow = Gtk.Image.new_from_icon_name("pan-down-symbolic")
        tbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        tbox.append(self._arrow)
        label = Gtk.Label(label=title, xalign=0.0, hexpand=True)
        label.add_css_class("heading")
        tbox.append(label)
        toggle = Gtk.Button(child=tbox, hexpand=True)
        toggle.add_css_class("flat")
        toggle.connect("clicked", lambda _b: self._toggle())
        header.append(toggle)

        if on_add is not None:
            add = Gtk.Button(
                icon_name="list-add-symbolic", valign=Gtk.Align.CENTER,
                tooltip_text=add_tooltip,
            )
            add.add_css_class("flat")
            add.connect("clicked", lambda _b: on_add())
            header.append(add)
        self.append(header)

        self._revealer = Gtk.Revealer(
            reveal_child=True, vexpand=vexpand,
            transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN,
        )
        self.append(self._revealer)
        if vexpand:
            self.set_vexpand(True)

    def set_content(self, widget: Gtk.Widget) -> None:
        self._revealer.set_child(widget)

    def _toggle(self) -> None:
        revealed = not self._revealer.get_reveal_child()
        self._revealer.set_reveal_child(revealed)
        self._arrow.set_from_icon_name(
            "pan-down-symbolic" if revealed else "pan-end-symbolic"
        )
