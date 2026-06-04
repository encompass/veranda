"""A dialog to edit a single button: label, icon, font, and action params."""

from __future__ import annotations

import os
from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, Gtk  # noqa: E402

from veranda.iconpicker import IconPicker  # noqa: E402
from veranda.models import ButtonConfig  # noqa: E402


class ButtonEditor(Adw.Dialog):
    """Edits a :class:`ButtonConfig` in place, notifying on every change."""

    def __init__(
        self,
        key: int,
        button: ButtonConfig,
        on_change: Callable[[], None],
        on_remove: Callable[[], None],
    ) -> None:
        super().__init__()
        self._button = button
        self._on_change = on_change
        self._on_remove = on_remove
        self._syncing = False
        self.set_title(f"Button {key + 1}")
        self.set_content_width(440)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        page = Adw.PreferencesPage()
        toolbar.set_content(page)

        # -- appearance ---------------------------------------------------
        appearance = Adw.PreferencesGroup(title="Appearance")

        self._label_row = Adw.EntryRow(title="Label")
        self._label_row.set_text(button.label)
        self._label_row.connect("changed", self._on_label_changed)
        appearance.add(self._label_row)

        self._icon_row = Adw.ActionRow(title="Icon")
        self._icon_preview = Gtk.Image()
        self._icon_preview.set_pixel_size(32)
        self._icon_row.add_prefix(self._icon_preview)

        browse = Gtk.Button(
            icon_name="view-grid-symbolic", valign=Gtk.Align.CENTER,
            tooltip_text="Browse icons",
        )
        browse.add_css_class("flat")
        browse.connect("clicked", self._on_browse_icons)
        upload = Gtk.Button(
            icon_name="document-open-symbolic", valign=Gtk.Align.CENTER,
            tooltip_text="Upload an image or SVG",
        )
        upload.add_css_class("flat")
        upload.connect("clicked", self._on_upload)
        self._clear = Gtk.Button(
            icon_name="edit-clear-symbolic", valign=Gtk.Align.CENTER,
            tooltip_text="Clear icon",
        )
        self._clear.add_css_class("flat")
        self._clear.connect("clicked", self._on_clear_icon)

        self._icon_row.add_suffix(browse)
        self._icon_row.add_suffix(upload)
        self._icon_row.add_suffix(self._clear)
        appearance.add(self._icon_row)

        font_row = Adw.SpinRow(
            title="Font size",
            adjustment=Gtk.Adjustment(
                lower=6, upper=48, step_increment=1, value=button.font_size
            ),
        )
        font_row.connect("notify::value", self._on_font_changed)
        appearance.add(font_row)

        self._bg_row = Adw.ActionRow(title="Background")
        self._color_btn = Gtk.ColorDialogButton(
            dialog=Gtk.ColorDialog(), valign=Gtk.Align.CENTER
        )
        self._color_btn.connect("notify::rgba", self._on_color_changed)
        self._bg_row.add_suffix(self._color_btn)
        accent_btn = Gtk.Button(
            label="Accent", valign=Gtk.Align.CENTER,
            tooltip_text="Follow the system accent color",
        )
        accent_btn.add_css_class("flat")
        accent_btn.connect("clicked", self._on_use_accent)
        self._bg_row.add_suffix(accent_btn)
        reset = Gtk.Button(
            icon_name="edit-clear-symbolic", valign=Gtk.Align.CENTER,
            tooltip_text="Use the theme default",
        )
        reset.add_css_class("flat")
        reset.connect("clicked", self._on_color_reset)
        self._bg_row.add_suffix(reset)
        appearance.add(self._bg_row)
        self._sync_color_button()
        page.add(appearance)

        # -- action -------------------------------------------------------
        if button.action is not None:
            action_group = Adw.PreferencesGroup(
                title="Action", description=button.action.NAME
            )
            for row in button.action.build_editor_rows(self._button, self._on_action_change):
                action_group.add(row)
            page.add(action_group)

            # Live widgets that poll expose an adjustable refresh interval.
            action = button.action
            if getattr(action, "DYNAMIC", False) and getattr(
                action, "supports_interval", lambda: False
            )():
                page.add(self._build_refresh_group(action))

        # -- remove -------------------------------------------------------
        danger = Adw.PreferencesGroup()
        remove = Gtk.Button(label="Remove Binding")
        remove.add_css_class("destructive-action")
        remove.set_halign(Gtk.Align.CENTER)
        remove.connect("clicked", self._on_remove_clicked)
        danger.add(remove)
        page.add(danger)

        self.set_child(toolbar)
        self._update_icon_preview()

    # -- icon -------------------------------------------------------------

    def _update_icon_preview(self) -> None:
        icon = self._button.icon
        if icon and "/" in icon:
            self._icon_preview.set_from_file(icon)
            self._icon_row.set_subtitle(os.path.basename(icon))
        elif icon:
            self._icon_preview.set_from_icon_name(icon)
            self._icon_row.set_subtitle(icon)
        else:
            self._icon_preview.set_from_icon_name("image-missing-symbolic")
            self._icon_row.set_subtitle("None")
        self._clear.set_sensitive(bool(icon))

    def _set_icon(self, icon: str) -> None:
        self._button.icon = icon
        self._update_icon_preview()
        self._notify()

    def _on_browse_icons(self, _btn) -> None:
        picker = IconPicker(on_pick=self._set_icon)
        picker.present(self)

    def _on_clear_icon(self, _btn) -> None:
        self._set_icon("")

    def _on_upload(self, _btn) -> None:
        dialog = Gtk.FileDialog(title="Choose an image")
        image_filter = Gtk.FileFilter()
        image_filter.set_name("Images")
        for pattern in ("*.png", "*.jpg", "*.jpeg", "*.svg", "*.gif", "*.webp", "*.bmp"):
            image_filter.add_pattern(pattern)
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(image_filter)
        dialog.set_filters(filters)
        dialog.open(self.get_root() or self, None, self._on_image_chosen)

    def _on_image_chosen(self, dialog, result) -> None:
        try:
            file = dialog.open_finish(result)
        except Exception:  # noqa: BLE001 - user cancelled
            return
        if file is not None and file.get_path():
            self._set_icon(file.get_path())

    # -- handlers ---------------------------------------------------------

    def _notify(self) -> None:
        self._on_change()

    def _build_refresh_group(self, action) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title="Refresh")
        spin = Adw.SpinRow(
            title="Update every",
            subtitle="seconds",
            adjustment=Gtk.Adjustment(
                lower=action.MIN_INTERVAL, upper=86400, step_increment=1,
                value=action.refresh_interval(),
            ),
        )

        def on_interval(row, _p):
            action.set_refresh_interval(int(row.get_value()))
            self._on_action_change()

        spin.connect("notify::value", on_interval)
        group.add(spin)
        return group

    def _on_action_change(self) -> None:
        # An action may have set the button's label/icon (e.g. picking a GNOME
        # shortcut) — reflect that in the editor fields, then persist + render.
        self._sync_appearance()
        self._notify()

    def _sync_appearance(self) -> None:
        self._syncing = True
        if self._label_row.get_text() != self._button.label:
            self._label_row.set_text(self._button.label)
        self._update_icon_preview()
        self._syncing = False

    def _on_label_changed(self, row) -> None:
        if self._syncing:
            return
        self._button.label = row.get_text()
        self._notify()

    def _on_font_changed(self, row, _pspec) -> None:
        self._button.font_size = int(row.get_value())
        self._notify()

    # -- background color -------------------------------------------------

    def _sync_color_button(self) -> None:
        from gi.repository import Gdk

        from veranda import render

        rgb = render.resolve_background(self._button.background)
        rgba = Gdk.RGBA()
        rgba.red, rgba.green, rgba.blue, rgba.alpha = (
            rgb[0] / 255, rgb[1] / 255, rgb[2] / 255, 1.0,
        )
        self._setting_color = True
        self._color_btn.set_rgba(rgba)
        self._setting_color = False
        bg = self._button.background
        self._bg_row.set_subtitle(
            "Accent color" if bg == "accent" else "Custom" if bg else "Theme default"
        )

    def _on_color_changed(self, *_a) -> None:
        if getattr(self, "_setting_color", False):
            return
        rgba = self._color_btn.get_rgba()
        self._button.background = "#%02x%02x%02x" % (
            round(rgba.red * 255), round(rgba.green * 255), round(rgba.blue * 255),
        )
        self._bg_row.set_subtitle("Custom")
        self._notify()

    def _on_use_accent(self, _btn) -> None:
        self._button.background = "accent"
        self._sync_color_button()
        self._notify()

    def _on_color_reset(self, _btn) -> None:
        self._button.background = ""  # back to the theme default
        self._sync_color_button()
        self._notify()

    def _on_remove_clicked(self, _btn) -> None:
        self._on_remove()
        self.close()
