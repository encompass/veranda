"""The main application window and top-level controller."""

from __future__ import annotations

import glob
import logging
import subprocess

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from veranda import APP_ID, __version__
from veranda.config import AppConfig, config_dir
from veranda.deck import DeckInfo, DeckManager
from veranda.dispatch import Dispatcher
from veranda.editor import ButtonEditor
from veranda.grid import DeckGrid
from veranda.input_backend import shared_backend
from veranda.library import ActionLibrary
from veranda.pagespanel import PagesPanel
from veranda.virtualdeck import VirtualDeckManager
from veranda.models import ActionItem, ButtonConfig, DeckState, Page, Profile
from veranda.screensaver import ScreensaverMonitor
from veranda.settings import SettingsDialog, prompt_text
from veranda.statusicon import TrayIcon
from veranda.background import request_background
from veranda.dbusservice import VerandaDBusService
from veranda.searchprovider import VerandaSearchProvider
from veranda.livebuttons import LiveButtonController
from veranda.undo import UndoStack
from veranda import autostart, transfer

log = logging.getLogger(__name__)

UDEV_RULE = 'SUBSYSTEMS=="usb", ATTRS{idVendor}=="0fd9", TAG+="uaccess"'
UDEV_FIX = (
    "echo '" + UDEV_RULE + "' | sudo tee /etc/udev/rules.d/60-veranda-streamdeck.rules\n"
    "sudo udevadm control --reload-rules && sudo udevadm trigger"
)


def _usb_streamdeck_present() -> bool:
    """True if an Elgato (0fd9) device is on the USB bus, per sysfs."""
    for path in glob.glob("/sys/bus/usb/devices/*/idVendor"):
        try:
            with open(path) as fh:
                if fh.read().strip().lower() == "0fd9":
                    return True
        except OSError:
            continue
    return False


class VerandaWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application) -> None:
        super().__init__(application=app)
        self.set_title("Veranda")

        self._config = AppConfig.load()
        _settings = self._config.settings
        self.set_default_size(_settings.window_width, _settings.window_height)
        if _settings.window_maximized:
            self.maximize()

        self._input_backend = shared_backend()
        self._deck_manager = DeckManager(
            on_key_press=self._on_key_press,
            on_decks_changed=self._refresh,
        )
        self._dispatcher = Dispatcher(
            self._config,
            self._deck_manager,
            self._input_backend,
            switch_page=self._switch_page,
            switch_profile=self._switch_profile_for,
            set_brightness=self._set_device_brightness,
            notify=self.notify,
        )
        self._current_serial: str | None = None
        self._device_serials: list[str] = []
        self._updating_profiles = False
        self._updating_devices = False
        self._named_prompted: set[str] = set()

        self._screensaver = ScreensaverMonitor(self._on_screensaver_changed)
        self._screensaver.start()
        self._screensaver_active = self._screensaver.active

        self._quitting = False
        self._shutdown_done = False
        self._tray = TrayIcon(
            item_id="veranda",
            title="Veranda",
            icon_name=APP_ID,
            on_activate=self._toggle_window,
            on_show=self.present,
            on_quit=self._real_quit,
            show_label="Show Veranda",
            quit_label="Quit",
        )

        self._install_actions()
        self._build_ui()
        self.connect("close-request", self._on_close)

        # Control interface for the GNOME Shell extension.
        self._dbus = VerandaDBusService(self)
        self._dbus.register()
        self.connect("notify::visible", lambda *_a: self._dbus.notify_changed())

        # Profile search results in the GNOME Shell overview.
        self._search = VerandaSearchProvider(self)
        self._search.register()

        # Live "Special Buttons" refresh driver.
        self._live = LiveButtonController(self._repaint_live_key)
        self._undo = UndoStack()
        self._key_clipboard: ButtonConfig | None = None

        # Virtual ("software") decks: floating windows that act like devices.
        self._virtual = VirtualDeckManager(
            self.get_application(), self._deck_manager, self._config,
            refresh=self._refresh,
            open_settings=self._virtual_settings,
            windows_changed=self._dbus.notify_changed,
        )

        # Re-render keys when the system theme (light/dark) or accent changes.
        _sm = Adw.StyleManager.get_default()
        self._theme_handler = _sm.connect("notify::dark", self._on_theme_changed)
        self._accent_handler = _sm.connect("notify::accent-color", self._on_theme_changed)

        self._deck_manager.start()
        self._virtual.restore_all()  # recreate saved virtual decks + windows
        if self._config.settings.run_in_background:
            self._enable_background()
            # If the window will be visible, warn (once) about a missing tray
            # host after the watcher has had a moment to appear.
            if not self.should_start_hidden():
                GLib.timeout_add_seconds(3, self._maybe_warn_no_tray_host)
        self._refresh()

    # -- actions / menu ---------------------------------------------------

    def _install_actions(self) -> None:
        for name, handler in (
            ("preferences", self._open_settings),
            ("rename_device", self.rename_device),
            ("add-virtual-device", self._add_virtual_device),
            ("import", lambda: self.import_profile_dialog()),
            ("export", lambda: self.export_profile_dialog()),
            ("about", self._show_about),
            ("shortcuts", self._show_shortcuts),
            ("next-page", lambda: self._page_step(1)),
            ("prev-page", lambda: self._page_step(-1)),
            ("rename-page", self._rename_page),
            ("move-page-left", lambda: self._move_page(-1)),
            ("move-page-right", lambda: self._move_page(1)),
            ("undo", self._do_undo),
            ("redo", self._do_redo),
            ("quit", self._real_quit),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda _a, _p, h=handler: h())
            self.add_action(action)

        app = self.get_application()
        if app is not None:
            for action_name, accels in (
                ("win.quit", ["<Ctrl>q"]),
                ("win.preferences", ["<Ctrl>comma"]),
                ("win.shortcuts", ["<Ctrl>question", "F1"]),
                ("win.next-page", ["<Ctrl>Page_Down"]),
                ("win.prev-page", ["<Ctrl>Page_Up"]),
                ("win.undo", ["<Ctrl>z"]),
                ("win.redo", ["<Ctrl>y", "<Ctrl><Shift>z"]),
            ):
                app.set_accels_for_action(action_name, accels)

    def _build_menu(self) -> Gio.Menu:
        menu = Gio.Menu()
        menu.append("Rename Device…", "win.rename_device")
        menu.append("Add Virtual Device…", "win.add-virtual-device")
        menu.append("Preferences", "win.preferences")
        backup = Gio.Menu()
        backup.append("Import Buttons…", "win.import")
        backup.append("Export Buttons…", "win.export")
        menu.append_section(None, backup)
        about = Gio.Menu()
        about.append("Keyboard Shortcuts", "win.shortcuts")
        about.append("About Veranda", "win.about")
        about.append("Quit", "win.quit")
        menu.append_section(None, about)
        return menu

    # -- virtual devices --------------------------------------------------

    def _add_virtual_device(self) -> None:
        self._virtual_form(
            "New Virtual Device", "Virtual Deck", 2, 3, "",
            lambda name, rows, cols, bg: self._virtual.add(rows, cols, name, bg),
        )

    def _virtual_settings(self, serial: str) -> None:
        state = self._config.decks.get(serial)
        if state is None:
            return

        def apply(name: str, rows: int, cols: int, bg: str) -> None:
            if name != state.name:
                state.name = name
                self._config.save()
            self._virtual.set_background(serial, bg)
            self._virtual.resize(serial, rows, cols)  # no-op if unchanged
            self._refresh()

        self._virtual_form(
            f"{state.display_name} — Settings", state.name or "Virtual Deck",
            state.grid_rows or 2, state.grid_cols or 3,
            str(state.window.get("bg", "")), apply,
        )

    def _virtual_form(self, title, name, rows, cols, bg, on_apply) -> None:
        from gi.repository import Gdk

        from veranda import render

        dialog = Adw.Dialog()
        dialog.set_title(title)
        dialog.set_content_width(380)
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        apply_btn = Gtk.Button(label="Apply")
        apply_btn.add_css_class("suggested-action")
        header.pack_end(apply_btn)
        toolbar.add_top_bar(header)

        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup()
        name_row = Adw.EntryRow(title="Name")
        name_row.set_text(name)
        rows_row = Adw.SpinRow(
            title="Rows",
            adjustment=Gtk.Adjustment(lower=1, upper=8, step_increment=1, value=rows),
        )
        cols_row = Adw.SpinRow(
            title="Columns",
            adjustment=Gtk.Adjustment(lower=1, upper=8, step_increment=1, value=cols),
        )

        bg_row = Adw.ActionRow(title="Background", subtitle="Window colour")
        chosen = {"bg": bg}
        color_btn = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(), valign=Gtk.Align.CENTER)
        rgb = render.resolve_background(bg)
        rgba = Gdk.RGBA()
        rgba.red, rgba.green, rgba.blue, rgba.alpha = rgb[0] / 255, rgb[1] / 255, rgb[2] / 255, 1.0
        color_btn.set_rgba(rgba)  # before connecting, so it doesn't count as a choice
        color_btn.connect("notify::rgba", lambda *_a: chosen.update(
            bg="#%02x%02x%02x" % (
                round(color_btn.get_rgba().red * 255),
                round(color_btn.get_rgba().green * 255),
                round(color_btn.get_rgba().blue * 255),
            )
        ))
        reset = Gtk.Button(icon_name="edit-clear-symbolic", valign=Gtk.Align.CENTER,
                           tooltip_text="Use the theme default")
        reset.add_css_class("flat")
        reset.connect("clicked", lambda _b: chosen.update(bg=""))
        bg_row.add_suffix(color_btn)
        bg_row.add_suffix(reset)

        for row in (name_row, rows_row, cols_row, bg_row):
            group.add(row)
        page.add(group)
        toolbar.set_content(page)
        dialog.set_child(toolbar)

        def do_apply(_b):
            on_apply(
                name_row.get_text().strip() or "Virtual Deck",
                int(rows_row.get_value()), int(cols_row.get_value()), chosen["bg"],
            )
            dialog.close()

        apply_btn.connect("clicked", do_apply)
        dialog.present(self)

    # -- D-Bus surface for the Shell extension (always-on-top / position) --

    def virtual_window_geometry(self):
        """List of (title, x, y, on_top) for the extension to place/raise."""
        return self._virtual.window_geometry()

    def report_virtual_window_moved(self, title: str, x: int, y: int) -> None:
        self._virtual.report_moved(title, x, y)

    def _show_shortcuts(self) -> None:
        dialog = Adw.ShortcutsDialog()

        general = Adw.ShortcutsSection(title="General")
        for title, accel in (
            ("Undo", "<Ctrl>z"),
            ("Redo", "<Ctrl>y"),
            ("Preferences", "<Ctrl>comma"),
            ("Keyboard Shortcuts", "<Ctrl>question"),
            ("Previous Page", "<Ctrl>Page_Up"),
            ("Next Page", "<Ctrl>Page_Down"),
            ("Quit", "<Ctrl>q"),
        ):
            general.add(Adw.ShortcutsItem(title=title, accelerator=accel))
        dialog.add(general)

        editing = Adw.ShortcutsSection(title="Deck Editing")
        for title, subtitle in (
            ("Bind an action", "Drag from the action list onto a key"),
            ("Move or swap a key", "Drag one key onto another"),
            ("Edit a key", "Click a bound key"),
            ("Set a custom icon", "Drop an image file onto a key"),
        ):
            editing.add(Adw.ShortcutsItem(title=title, subtitle=subtitle))
        dialog.add(editing)

        dialog.present(self)

    # -- UI construction --------------------------------------------------

    def _build_ui(self) -> None:
        self._toasts = Adw.ToastOverlay()
        # One full-width header spanning the whole window; below it the pages
        # list, the key grid, and the action library sit side by side.
        outer = Adw.ToolbarView()
        outer.add_top_bar(self._build_header())

        self._split = Adw.OverlaySplitView(
            sidebar_position=Gtk.PackType.END,
            min_sidebar_width=300,
            max_sidebar_width=420,
            sidebar_width_fraction=0.34,
        )
        self._split.set_content(self._build_main_pane())
        self._split.set_sidebar(ActionLibrary())
        outer.set_content(self._split)

        self._toasts.set_child(outer)
        self.set_content(self._toasts)

        # The action library stays beside the grid and never collapses into an
        # overlay — overlaying the grid would hide the drop targets and break
        # drag-and-drop. Instead the window enforces a minimum width that fits
        # both panes (see _update_min_width, recomputed per device).

    def _build_header(self) -> Adw.HeaderBar:
        header = Adw.HeaderBar()

        # Device switcher (shows each deck's friendly name).
        self._device_drop = Gtk.DropDown.new_from_strings(["Device"])
        self._device_drop.set_tooltip_text("Selected device")
        self._device_drop.connect("notify::selected", self._on_device_selected)
        header.pack_start(self._device_drop)

        # Profile switcher.
        self._profile_drop = Gtk.DropDown.new_from_strings(["Default"])
        self._profile_drop.set_tooltip_text("Active profile")
        self._profile_drop.connect("notify::selected", self._on_profile_selected)
        header.pack_start(self._profile_drop)

        # Main menu (page management now lives in the left Pages panel).
        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic", tooltip_text="Main menu")
        menu_btn.set_menu_model(self._build_menu())
        header.pack_end(menu_btn)
        return header

    def _build_main_pane(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)

        self._pages_panel = PagesPanel(
            on_select=self._on_page_selected,
            on_reorder=self._reorder_pages,
            on_add=self._add_page,
            on_rename=self._rename_page_at,
            on_remove=self._remove_page_at,
        )
        box.append(self._pages_panel)
        box.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        self._body = Gtk.Stack(hexpand=True, vexpand=True)
        self._grid = DeckGrid(
            self._on_drop, self._on_select, self._on_move, self._on_file_drop,
            self._remove_button, self._on_tile_command, self._can_paste,
        )
        board = Gtk.Box(hexpand=True, vexpand=True)
        board.add_css_class("deck-board")
        board.append(self._grid)
        self._body.add_named(board, "grid")

        self._status = Adw.StatusPage(icon_name="input-tablet-symbolic")
        self._body.add_named(self._status, "status")
        box.append(self._body)
        return box

    # -- queries for settings ---------------------------------------------

    def current_state(self) -> DeckState | None:
        if self._current_serial is None:
            return None
        return self._config.decks.get(self._current_serial)

    def deck_info(self) -> DeckInfo | None:
        if self._current_serial is None:
            return None
        return self._deck_manager.info(self._current_serial)

    def reload(self) -> None:
        """Persist and re-render after an external (settings) change."""
        self._config.save()
        self._refresh()

    # -- state refresh ----------------------------------------------------

    def _refresh(self) -> bool:
        serials = self._deck_manager.serials()
        if self._current_serial not in serials:
            self._current_serial = serials[0] if serials else None

        if self._current_serial is None:
            self._set_controls_sensitive(False)
            self._show_status()
            return False

        serial = self._current_serial
        info = self._deck_manager.info(serial)
        if info is None:
            self._set_controls_sensitive(False)
            self._show_status()
            return False

        state = self._config.deck(serial, info.deck_type)

        # Give a freshly-seen device a default name and offer to customize it.
        if not state.name:
            state.name = self._unique_default_name(state.deck_type, exclude=serial)
            self._config.save()
            if serial not in self._named_prompted:
                self._named_prompted.add(serial)
                self._prompt_device_name(serial)

        profile = state.current_profile()
        page = profile.current_page()

        self._set_controls_sensitive(True)
        self._update_device_dropdown(serial)
        self._update_profile_dropdown(state)

        self._pages_panel.update([p.name for p in profile.pages], profile.active_page)

        self._grid.build(info, page)
        self._body.set_visible_child_name("grid")

        self._apply_brightness(serial)
        self._deck_manager.apply_page(serial, page)
        # Rebuild live-widget subscriptions in a strict teardown→rebuild order so
        # a widget action shared by a deck is never managed by two controllers at
        # once (the window's controller for the current device + a per-virtual
        # controller): tear self._live down first, let the virtual manager stop
        # all its controllers and re-arm only the non-current ones, then
        # subscribe the current device fresh.
        self._live.stop()
        self._virtual.sync_live(serial)  # keep non-current virtual windows live
        self._live.rebuild(page)
        self._dbus.notify_changed()
        self._update_min_width()
        return False

    def _update_min_width(self) -> None:
        """Keep the window wide enough to show the grid and library side by
        side, so the library never has to overlay the grid (which would hide
        the drop targets and break drag-and-drop)."""
        content = self._split.get_content()
        sidebar = self._split.get_sidebar()
        if content is None or sidebar is None:
            return
        cmin = content.measure(Gtk.Orientation.HORIZONTAL, -1)[0]
        smin = sidebar.measure(Gtk.Orientation.HORIZONTAL, -1)[0]
        self.set_size_request(cmin + smin + 120, -1)  # split handle + margin

    def _repaint_live_key(self, key: int) -> None:
        """Repaint one live (Special Button) key on the GUI and hardware."""
        serial = self._current_serial
        if serial is None:
            return
        button = self._config.deck(serial).current_page().buttons.get(key)
        if button is None:
            return
        self._grid.update_key(key, button)
        state = self._config.decks.get(serial)
        dimmed = self._screensaver_active and state is not None and state.dim_on_lock
        if not dimmed:
            self._deck_manager.update_button(serial, key, button)

    def _set_controls_sensitive(self, sensitive: bool) -> None:
        for widget in (self._device_drop, self._profile_drop, self._pages_panel):
            widget.set_sensitive(sensitive)

    def _update_device_dropdown(self, current_serial: str) -> None:
        self._updating_devices = True
        serials = self._deck_manager.serials()
        self._device_serials = serials
        model = Gtk.StringList()
        for serial in serials:
            model.append(self._config.deck(serial).display_name)
        self._device_drop.set_model(model)
        if current_serial in serials:
            self._device_drop.set_selected(serials.index(current_serial))
        self._device_drop.set_visible(len(serials) > 0)
        # A lone device needs no selection affordance.
        self._device_drop.set_sensitive(len(serials) > 1)
        self._updating_devices = False

    def _update_profile_dropdown(self, state: DeckState) -> None:
        self._updating_profiles = True
        model = Gtk.StringList()
        for profile in state.profiles:
            model.append(profile.name)
        self._profile_drop.set_model(model)
        self._profile_drop.set_selected(state.active_profile)
        self._updating_profiles = False

    def _show_status(self) -> None:
        if self._deck_manager.probe_failed():
            self._status.set_title("HID backend missing")
            self._status.set_description(
                "No working HID library was found. Install it with:\n\n"
                "sudo apt install libhidapi-libusb0"
            )
            self._status.set_child(None)
        elif _usb_streamdeck_present():
            self._status.set_title("Permission needed")
            self._status.set_description(
                "A Stream Deck is connected but Veranda can't access it. "
                "Install the udev rule, then unplug and replug the device."
            )
            self._status.set_child(self._udev_fix_widget())
        else:
            self._status.set_title("Connect your Stream Deck")
            self._status.set_description("Plug in a supported Elgato Stream Deck to begin.")
            self._status.set_child(None)
        self._body.set_visible_child_name("status")

    def _udev_fix_widget(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, halign=Gtk.Align.CENTER)
        label = Gtk.Label(label=UDEV_FIX, selectable=True, wrap=True)
        label.add_css_class("monospace")
        box.append(label)
        copy = Gtk.Button(label="Copy commands", halign=Gtk.Align.CENTER)
        copy.add_css_class("pill")
        copy.connect("clicked", lambda _b: (self.get_clipboard().set(UDEV_FIX),
                                            self.notify("Commands copied to clipboard")))
        box.append(copy)
        return box

    # -- key / binding callbacks ------------------------------------------

    def _on_key_press(self, serial: str, key: int) -> bool:
        self._dispatcher.dispatch(serial, key)
        return False

    def _on_drop(self, key: int, item: ActionItem) -> None:
        if self._current_serial is None:
            return
        self._record_undo()
        page = self._config.deck(self._current_serial).current_page()
        action = item.new_action()
        button = ButtonConfig(
            label=action.default_label() or action.NAME,
            icon=action.default_icon(),
            action=action,
        )
        page.buttons[key] = button
        self._config.save()
        self._grid.update_key(key, button)
        self._deck_manager.update_button(self._current_serial, key, button)
        self._open_editor(key, button)

    def _on_select(self, key: int) -> None:
        if self._current_serial is None:
            return
        button = self._config.deck(self._current_serial).current_page().buttons.get(key)
        if button is None:
            self.notify("Drag an action from the right onto this button")
            return
        self._open_editor(key, button)

    _IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp", ".bmp")

    def _on_file_drop(self, key: int, gfile) -> None:
        """Set a key's icon from an image file dropped from Files."""
        import os
        import shutil
        import uuid

        from veranda.config import config_dir

        if self._current_serial is None:
            return
        path = gfile.get_path()
        if not path:
            self.notify("That file isn't available locally")
            return
        ext = os.path.splitext(path)[1].lower()
        if ext not in self._IMAGE_EXTS:
            self.notify("Drop an image file (PNG, JPG, SVG…)")
            return
        try:
            icons = config_dir() / "icons"
            icons.mkdir(parents=True, exist_ok=True)
            dest = icons / f"{uuid.uuid4().hex}{ext}"
            shutil.copyfile(path, dest)
        except OSError as exc:
            self.notify(f"Couldn't import the image: {exc}")
            return

        self._record_undo()
        page = self._config.deck(self._current_serial).current_page()
        button = page.buttons.get(key)
        if button is None:
            button = ButtonConfig()
            page.buttons[key] = button
        button.icon = str(dest)
        self._config.save()
        self._grid.update_key(key, button)
        self._deck_manager.update_button(self._current_serial, key, button)
        self.notify("Icon set from image")

    # -- undo / redo ------------------------------------------------------

    def _snapshot(self):
        if self._current_serial is None:
            return None
        state = self._config.decks.get(self._current_serial)
        return (self._current_serial, state.to_dict()) if state is not None else None

    def _record_undo(self) -> None:
        snap = self._snapshot()
        if snap is not None:
            self._undo.record(snap)

    def _apply_snapshot(self, snap) -> None:
        serial, data = snap
        self._config.decks[serial] = DeckState.from_dict(serial, data)
        self._config.save()
        if serial == self._current_serial:
            self._refresh()
        else:
            self._deck_manager.apply_page(serial, self._config.decks[serial].current_page())

    def _do_undo(self) -> None:
        cur = self._snapshot()
        if cur is None:
            return
        snap = self._undo.undo(cur)
        if snap is None:
            self.notify("Nothing to undo")
            return
        self._apply_snapshot(snap)
        self.notify("Undone")

    def _do_redo(self) -> None:
        cur = self._snapshot()
        if cur is None:
            return
        snap = self._undo.redo(cur)
        if snap is None:
            self.notify("Nothing to redo")
            return
        self._apply_snapshot(snap)
        self.notify("Redone")

    # -- copy / paste / duplicate ----------------------------------------

    def _can_paste(self) -> bool:
        return self._key_clipboard is not None

    def _current_buttons(self):
        if self._current_serial is None:
            return None
        return self._config.deck(self._current_serial).current_page().buttons

    def _on_tile_command(self, key: int, command: str) -> None:
        if command == "copy":
            self._copy_key(key)
        elif command == "paste":
            self._paste_key(key)
        elif command == "duplicate":
            self._duplicate_key(key)

    def _copy_key(self, key: int) -> None:
        buttons = self._current_buttons()
        if buttons is None or key not in buttons:
            return
        self._key_clipboard = ButtonConfig.from_dict(buttons[key].to_dict())
        self.notify("Key copied")

    def _paste_key(self, key: int) -> None:
        if self._key_clipboard is None or self._current_serial is None:
            return
        self._record_undo()
        buttons = self._config.deck(self._current_serial).current_page().buttons
        button = ButtonConfig.from_dict(self._key_clipboard.to_dict())
        buttons[key] = button
        self._config.save()
        self._grid.update_key(key, button)
        self._deck_manager.update_button(self._current_serial, key, button)
        self._live.rebuild(self._config.deck(self._current_serial).current_page())
        self.notify("Pasted")

    def _duplicate_key(self, key: int) -> None:
        if self._current_serial is None:
            return
        buttons = self._config.deck(self._current_serial).current_page().buttons
        if key not in buttons:
            return
        info = self._deck_manager.info(self._current_serial)
        count = info.key_count if info is not None else 0
        target = next((k for k in range(count) if k not in buttons), None)
        if target is None:
            self.notify("No empty key to duplicate to")
            return
        self._record_undo()
        button = ButtonConfig.from_dict(buttons[key].to_dict())
        buttons[target] = button
        self._config.save()
        self._grid.update_key(target, button)
        self._deck_manager.update_button(self._current_serial, target, button)
        self._live.rebuild(self._config.deck(self._current_serial).current_page())
        self.notify("Duplicated")

    def _on_move(self, source_key: int, target_key: int) -> None:
        """Move/swap a binding between two keys via drag-and-drop."""
        if self._current_serial is None or source_key == target_key:
            return
        self._record_undo()
        page = self._config.deck(self._current_serial).current_page()
        src = page.buttons.get(source_key)
        if src is None:
            return
        tgt = page.buttons.get(target_key)
        page.buttons[target_key] = src
        if tgt is not None:
            page.buttons[source_key] = tgt  # swap
        else:
            page.buttons.pop(source_key, None)  # plain move

        self._config.save()
        self._grid.update_key(source_key, page.buttons.get(source_key))
        self._grid.update_key(target_key, page.buttons.get(target_key))
        for k in (source_key, target_key):
            self._deck_manager.update_button(self._current_serial, k, page.buttons.get(k))
        self._live.rebuild(page)  # re-key any live widgets that moved

    def _open_editor(self, key: int, button: ButtonConfig) -> None:
        self._grid.select(key)
        editor = ButtonEditor(
            key, button,
            on_change=lambda: self._after_edit(key, button),
            on_remove=lambda: self._remove_button(key),
        )
        editor.connect("closed", lambda _d: self._grid.select(None))
        editor.present(self)

    def _after_edit(self, key: int, button: ButtonConfig) -> None:
        self._config.save()
        self._grid.update_key(key, button)
        if self._current_serial is not None:
            self._deck_manager.update_button(self._current_serial, key, button)
            # Re-arm live timers/subscriptions if a Special Button was edited
            # (e.g. its refresh interval changed).
            if getattr(button.action, "DYNAMIC", False):
                self._live.rebuild(self._config.deck(self._current_serial).current_page())

    def _remove_button(self, key: int) -> None:
        if self._current_serial is None:
            return
        self._record_undo()
        self._config.deck(self._current_serial).current_page().buttons.pop(key, None)
        self._config.save()
        self._grid.update_key(key, None)
        self._deck_manager.update_button(self._current_serial, key, None)

    # -- profiles ---------------------------------------------------------

    def _on_profile_selected(self, drop, _pspec) -> None:
        if self._updating_profiles:
            return
        idx = drop.get_selected()
        if idx != Gtk.INVALID_LIST_POSITION:
            self.switch_profile(idx)

    def switch_profile(self, idx: int) -> None:
        state = self.current_state()
        if state is None:
            return
        idx = max(0, min(idx, len(state.profiles) - 1))
        if idx == state.active_profile:
            return
        state.active_profile = idx
        self.reload()

    # -- focus-driven profile auto-switching ------------------------------

    def set_focused_app(self, desktop_id: str) -> None:
        """Switch to the profile mapped to the focused app (if any)."""
        s = self._config.settings
        if not s.auto_switch or not desktop_id:
            return
        name = (
            s.app_profiles.get(desktop_id)
            or s.app_profiles.get(desktop_id + ".desktop")
            or s.app_profiles.get(desktop_id.removesuffix(".desktop"))
        )
        if not name:
            return
        state = self.current_state()
        if state is None:
            return
        for idx, profile in enumerate(state.profiles):
            if profile.name == name and idx != state.active_profile:
                self.switch_profile(idx)
                return

    def set_auto_switch(self, enabled: bool) -> None:
        self._config.settings.auto_switch = bool(enabled)
        self._config.save()

    def app_profiles(self) -> dict[str, str]:
        return self._config.settings.app_profiles

    def set_app_profile(self, desktop_id: str, profile_name: str) -> None:
        self._config.settings.app_profiles[desktop_id] = profile_name
        self._config.save()

    def remove_app_profile(self, desktop_id: str) -> None:
        self._config.settings.app_profiles.pop(desktop_id, None)
        self._config.save()

    def profile_names(self) -> list[str]:
        state = self.current_state()
        return [p.name for p in state.profiles] if state is not None else []

    def set_brightness(self, value: int) -> None:
        """Set brightness for the current device (used by Settings)."""
        if self._current_serial is not None:
            self._set_device_brightness(self._current_serial, value)

    def _set_device_brightness(self, serial: str, value: int) -> None:
        """Change and persist a specific device's brightness (per device)."""
        state = self._config.decks.get(serial)
        if state is None:
            return
        state.brightness = max(0, min(100, int(value)))
        self._config.save()
        self._apply_brightness(serial)
        self._dbus.notify_changed()

    def _apply_brightness(self, serial: str) -> None:
        """Push effective brightness to the device, honoring lock-dimming."""
        state = self._config.decks.get(serial)
        if state is None:
            return
        dimmed = self._screensaver_active and state.dim_on_lock
        self._deck_manager.set_brightness(serial, 0 if dimmed else state.brightness)

    # -- screensaver / lock sync -----------------------------------------

    def _on_theme_changed(self, *_a) -> None:
        from veranda import render

        render.invalidate_theme_cache()
        self._refresh()

    def _on_screensaver_changed(self, active: bool) -> None:
        self._screensaver_active = active
        for serial in self._deck_manager.serials():
            self._apply_brightness(serial)
        # On wake, repaint live keys that were skipped while the deck was dark.
        if not active and self._current_serial is not None:
            self._live.repaint_all(self._config.deck(self._current_serial).current_page())

    def screensaver_available(self) -> bool:
        return self._screensaver.available

    def set_dim_on_lock(self, enabled: bool) -> None:
        state = self.current_state()
        if state is None:
            return
        state.dim_on_lock = bool(enabled)
        self._config.save()
        self._apply_brightness(self._current_serial)

    # -- devices ----------------------------------------------------------

    def _on_device_selected(self, drop, _pspec) -> None:
        if self._updating_devices:
            return
        idx = drop.get_selected()
        if 0 <= idx < len(self._device_serials):
            serial = self._device_serials[idx]
            if serial != self._current_serial:
                self._current_serial = serial
                self._refresh()

    def _unique_default_name(self, base: str, exclude: str) -> str:
        base = base or "Stream Deck"
        taken = {
            s.name for serial, s in self._config.decks.items()
            if serial != exclude and s.name
        }
        if base not in taken:
            return base
        i = 2
        while f"{base} {i}" in taken:
            i += 1
        return f"{base} {i}"

    def _prompt_device_name(self, serial: str) -> None:
        state = self._config.decks.get(serial)
        if state is None:
            return

        def apply(name: str) -> None:
            target = self._config.decks.get(serial)
            if target is not None:
                target.name = name
                self.reload()

        prompt_text(
            self, "Name this device", state.name, apply, ok_label="Save"
        )

    def rename_device(self) -> None:
        """Rename the current device (used by the menu / settings)."""
        if self._current_serial is None:
            self.notify("Connect a device to rename it")
            return
        self._prompt_device_name(self._current_serial)

    # -- pages ------------------------------------------------------------

    def _switch_page(self, serial: str, page_index: int) -> None:
        state = self._config.decks.get(serial)
        if state is None:
            return
        profile = state.current_profile()
        profile.active_page = max(0, min(page_index, len(profile.pages) - 1))
        self._config.save()
        if serial == self._current_serial:
            self._refresh()
        else:
            self._deck_manager.apply_page(serial, profile.current_page())

    def _switch_profile_for(self, serial: str, target: str) -> bool:
        """Activate a profile by name (case-insensitive) or 0-based index.

        Serial-aware so a Switch Profile key works on any connected deck.
        Returns True when a matching profile was found (even if already active).
        """
        state = self._config.decks.get(serial)
        if state is None or not state.profiles:
            return False
        names = [p.name for p in state.profiles]
        target = str(target).strip()
        folded = target.casefold()
        idx = None
        if folded in ("next", "previous", "prev"):
            delta = 1 if folded == "next" else -1
            idx = (state.active_profile + delta) % len(names)
        elif target.isdigit() and 0 <= int(target) < len(names):
            idx = int(target)
        else:
            idx = next((i for i, n in enumerate(names) if n.casefold() == folded), None)
        if idx is None:
            return False
        if idx != state.active_profile:
            state.active_profile = idx
            self._config.save()
            if serial == self._current_serial:
                self._refresh()
            else:
                self._deck_manager.apply_page(serial, state.current_profile().current_page())
            self._dbus.notify_changed()
        return True

    def _page_step(self, delta: int) -> None:
        if self._current_serial is None:
            return
        profile = self._config.deck(self._current_serial).current_profile()
        self._switch_page(self._current_serial, profile.active_page + delta)

    def _rename_page(self) -> None:
        if self._current_serial is None:
            return
        profile = self._config.deck(self._current_serial).current_profile()
        page = profile.current_page()

        def apply(name: str) -> None:
            self._record_undo()
            page.name = name
            self._config.save()
            self._refresh()

        prompt_text(self, "Rename page", page.name, apply)

    def _move_page(self, delta: int) -> None:
        if self._current_serial is None:
            return
        profile = self._config.deck(self._current_serial).current_profile()
        dst = profile.active_page + delta
        if not (0 <= dst < len(profile.pages)):
            return
        self._record_undo()
        profile.move_page(profile.active_page, dst)
        self._config.save()
        self._refresh()

    # -- pages panel callbacks (operate on a specific page index) ---------

    def _on_page_selected(self, index: int) -> None:
        if self._current_serial is not None:
            self._switch_page(self._current_serial, index)

    def _reorder_pages(self, src: int, dst: int) -> None:
        if self._current_serial is None:
            return
        profile = self._config.deck(self._current_serial).current_profile()
        n = len(profile.pages)
        if src == dst or not (0 <= src < n) or not (0 <= dst < n):
            return
        self._record_undo()
        profile.move_page(src, dst)
        self._config.save()
        self._refresh()

    def _rename_page_at(self, index: int) -> None:
        if self._current_serial is None:
            return
        profile = self._config.deck(self._current_serial).current_profile()
        if not (0 <= index < len(profile.pages)):
            return
        page = profile.pages[index]

        def apply(name: str) -> None:
            self._record_undo()
            page.name = name
            self._config.save()
            self._refresh()

        prompt_text(self, "Rename page", page.name, apply)

    def _remove_page_at(self, index: int) -> None:
        if self._current_serial is None:
            return
        profile = self._config.deck(self._current_serial).current_profile()
        if not (0 <= index < len(profile.pages)):
            return
        if index != profile.active_page:
            self._switch_page(self._current_serial, index)
        self._remove_page()

    def _add_page(self) -> None:
        if self._current_serial is None:
            return
        self._record_undo()
        profile = self._config.deck(self._current_serial).current_profile()
        profile.pages.append(Page(name=f"Page {len(profile.pages) + 1}"))
        self._switch_page(self._current_serial, len(profile.pages) - 1)

    def _remove_page(self) -> None:
        if self._current_serial is None:
            return
        profile = self._config.deck(self._current_serial).current_profile()
        if len(profile.pages) <= 1:
            self.notify("Can't remove the last page")
            return
        page = profile.current_page()
        if page.buttons:
            dialog = Adw.AlertDialog(
                heading="Remove this page?",
                body=f"This page has {len(page.buttons)} bound button(s). "
                "This can't be undone.",
            )
            dialog.add_response("cancel", "Cancel")
            dialog.add_response("remove", "Remove")
            dialog.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
            dialog.set_default_response("cancel")
            dialog.set_close_response("cancel")
            dialog.connect(
                "response",
                lambda _d, resp: self._do_remove_page() if resp == "remove" else None,
            )
            dialog.present(self)
        else:
            self._do_remove_page()

    def _do_remove_page(self) -> None:
        if self._current_serial is None:
            return
        self._record_undo()
        profile = self._config.deck(self._current_serial).current_profile()
        idx = profile.active_page
        del profile.pages[idx]
        if not profile.pages:
            profile.pages.append(Page())
        profile.active_page = max(0, min(idx, len(profile.pages) - 1))
        self._config.save()
        self._refresh()
        self.notify("Page removed")

    # -- import / export --------------------------------------------------

    def export_profile_dialog(self) -> None:
        state = self.current_state()
        if state is None:
            self.notify("Connect a device to export a profile")
            return
        profile = state.current_profile()
        dialog = Gtk.FileDialog(title="Export profile")
        dialog.set_initial_name(f"{profile.name}.veranda.json")
        dialog.set_initial_folder(Gio.File.new_for_path(str(config_dir())))

        def done(dlg, result):
            try:
                file = dlg.save_finish(result)
            except Exception:  # noqa: BLE001 - cancelled
                return
            if file and file.get_path():
                try:
                    transfer.export_profile(profile, file.get_path())
                    self.notify(f"Exported “{profile.name}”")
                except OSError as exc:
                    self.notify(f"Export failed: {exc}")

        dialog.save(self, None, done)

    def import_profile_dialog(self, on_done=None) -> None:
        state = self.current_state()
        if state is None:
            self.notify("Connect a device to import a profile")
            return
        dialog = Gtk.FileDialog(title="Import profile")
        flt = Gtk.FileFilter()
        flt.set_name("Veranda profiles")
        flt.add_pattern("*.json")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(flt)
        dialog.set_filters(filters)

        def done(dlg, result):
            try:
                file = dlg.open_finish(result)
            except Exception:  # noqa: BLE001 - cancelled
                return
            if not (file and file.get_path()):
                return
            try:
                profile = transfer.import_profile(file.get_path())
            except (OSError, ValueError) as exc:
                self.notify(f"Import failed: {exc}")
                return
            state.profiles.append(profile)
            state.active_profile = len(state.profiles) - 1
            self.reload()
            self.notify(f"Imported “{profile.name}”")
            if on_done is not None:
                on_done()

        dialog.open(self, None, done)

    def export_config_dialog(self) -> None:
        dialog = Gtk.FileDialog(title="Back up all settings")
        dialog.set_initial_name("veranda-backup.json")
        dialog.set_initial_folder(Gio.File.new_for_path(str(config_dir())))

        def done(dlg, result):
            try:
                file = dlg.save_finish(result)
            except Exception:  # noqa: BLE001 - cancelled
                return
            if file and file.get_path():
                try:
                    transfer.export_config(self._config, file.get_path())
                    self.notify("Backed up all settings")
                except OSError as exc:
                    self.notify(f"Backup failed: {exc}")

        dialog.save(self, None, done)

    def import_config_dialog(self, on_done=None) -> None:
        dialog = Gtk.FileDialog(title="Restore from backup")
        flt = Gtk.FileFilter()
        flt.set_name("Veranda backups")
        flt.add_pattern("*.json")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(flt)
        dialog.set_filters(filters)

        def done(dlg, result):
            try:
                file = dlg.open_finish(result)
            except Exception:  # noqa: BLE001 - cancelled
                return
            if not (file and file.get_path()):
                return
            try:
                decks, settings = transfer.import_config(file.get_path())
            except (OSError, ValueError) as exc:
                self.notify(f"Restore failed: {exc}")
                return
            self._confirm_restore(decks, settings, on_done)

        dialog.open(self, None, done)

    def _confirm_restore(self, decks, settings, on_done=None) -> None:
        alert = Adw.AlertDialog(
            heading="Replace all settings?",
            body=(
                "Restoring replaces every device, profile, and page with the "
                "contents of the backup. This cannot be undone."
            ),
        )
        alert.add_response("cancel", "Cancel")
        alert.add_response("restore", "Replace")
        alert.set_response_appearance("restore", Adw.ResponseAppearance.DESTRUCTIVE)
        alert.set_default_response("cancel")
        alert.set_close_response("cancel")

        def responded(_dlg, response):
            if response == "restore":
                self._apply_restored_config(decks, settings)
                if on_done is not None:
                    on_done()

        alert.connect("response", responded)
        alert.present(self)

    def _apply_restored_config(self, decks, settings) -> None:
        self._config.decks = decks
        self._config.settings = settings
        self._config.save()
        self._refresh()
        self._dbus.notify_changed()
        self.notify("Settings restored from backup")

    # -- menu handlers ----------------------------------------------------

    def _open_settings(self) -> None:
        SettingsDialog(self).present(self)

    def _show_about(self) -> None:
        about = Adw.AboutDialog(
            application_name="Veranda",
            application_icon=APP_ID,
            version=__version__,
            developer_name="Jason \"JBear\" Brower",
            developers=['Jason "JBear" Brower <encompass@gmail.com>'],
            license_type=Gtk.License.GPL_3_0,
            comments="A modern Stream Deck manager for GNOME.",
        )
        about.present(self)

    # -- misc -------------------------------------------------------------

    def notify(self, message: str) -> None:
        self._toasts.add_toast(Adw.Toast(title=message, timeout=3))

    # -- background / tray lifecycle --------------------------------------

    def should_start_hidden(self) -> bool:
        s = self._config.settings
        return s.run_in_background and s.start_hidden

    def get_app_settings(self):
        return self._config.settings

    def set_run_in_background(self, enabled: bool) -> None:
        self._config.settings.run_in_background = bool(enabled)
        self._config.save()
        if enabled:
            self._enable_background()
            GLib.timeout_add_seconds(2, self._maybe_warn_no_tray_host)
        else:
            self._disable_background()

    def set_start_hidden(self, enabled: bool) -> None:
        self._config.settings.start_hidden = bool(enabled)
        self._config.save()

    def autostart_enabled(self) -> bool:
        return autostart.is_enabled()

    def set_autostart(self, enabled: bool) -> None:
        autostart.set_enabled(enabled)

    def _enable_background(self) -> None:
        self._tray.start()
        request_background()

    def _disable_background(self) -> None:
        self._tray.stop()

    # -- missing tray-host warning ---------------------------------------

    def _maybe_warn_no_tray_host(self) -> bool:
        s = self._config.settings
        if (
            not s.run_in_background
            or s.tray_warning_dismissed
            or self._tray.host_available
        ):
            return False  # nothing to warn about
        self._show_tray_warning()
        return False  # one-shot timeout

    def _show_tray_warning(self) -> None:
        # One-time: never auto-show again once it has been raised.
        self._config.settings.tray_warning_dismissed = True
        self._config.save()

        uuid = self._find_appindicator_uuid()
        body = (
            "Veranda is set to run in the background, but no system-tray host "
            "is running — so it won't show an icon in the top bar. You can still "
            "reopen it from its app icon, or quit it from its menu."
        )
        if uuid:
            body += "\n\nEnable the AppIndicator GNOME extension to get a top-bar icon."
        else:
            body += (
                "\n\nInstall an AppIndicator GNOME extension "
                "(e.g. “AppIndicator and KStatusNotifier Support”) for a top-bar icon."
            )

        dialog = Adw.AlertDialog(heading="No tray icon available", body=body)
        dialog.add_response("close", "Got It")
        if uuid:
            dialog.add_response("enable", "Enable Extension")
            dialog.set_response_appearance("enable", Adw.ResponseAppearance.SUGGESTED)
            dialog.set_default_response("enable")
        dialog.set_close_response("close")
        dialog.connect(
            "response",
            lambda _d, resp: self._enable_appindicator(uuid) if resp == "enable" else None,
        )
        dialog.present(self)

    def _find_appindicator_uuid(self) -> str | None:
        """Return an installed AppIndicator extension uuid, if any."""
        try:
            out = subprocess.run(
                ["gnome-extensions", "list"],
                capture_output=True, text=True, timeout=5,
            ).stdout
        except (OSError, subprocess.SubprocessError):
            return None
        installed = set(out.split())
        for uuid in (
            "ubuntu-appindicators@ubuntu.com",
            "appindicatorsupport@rgcjonas.gmail.com",
        ):
            if uuid in installed:
                return uuid
        return None

    def _enable_appindicator(self, uuid: str) -> None:
        try:
            subprocess.run(["gnome-extensions", "enable", uuid], check=True, timeout=5)
            self.notify("Enabling AppIndicator support… the icon should appear shortly.")
        except (OSError, subprocess.SubprocessError) as exc:
            self.notify(f"Could not enable the extension: {exc}")

    def _toggle_window(self) -> None:
        if self.get_visible():
            self.set_visible(False)
        else:
            self.present()

    # Public aliases used by the D-Bus control interface.
    def toggle_window(self) -> None:
        self._toggle_window()

    def real_quit(self) -> None:
        self._real_quit()

    def _real_quit(self) -> None:
        self._quitting = True
        app = self.get_application()
        if app is not None:
            app.quit()
        else:
            self._shutdown()
            self.destroy()

    def _shutdown(self) -> None:
        if self._shutdown_done:
            return
        self._shutdown_done = True
        self._config.save()
        _sm = Adw.StyleManager.get_default()
        if self._theme_handler:
            _sm.disconnect(self._theme_handler)
            self._theme_handler = 0
        if self._accent_handler:
            _sm.disconnect(self._accent_handler)
            self._accent_handler = 0
        self._live.stop()
        self._virtual.shutdown()
        self._screensaver.stop()
        self._tray.stop()
        self._dbus.unregister()
        self._search.unregister()
        self._deck_manager.stop()
        self._input_backend.close()

    def _save_window_state(self) -> None:
        s = self._config.settings
        s.window_maximized = self.is_maximized()
        if not s.window_maximized:
            s.window_width = self.get_width() or s.window_width
            s.window_height = self.get_height() or s.window_height
        self._config.save()

    def _on_close(self, _window) -> bool:
        self._save_window_state()
        # When running in the background, closing just hides to the tray.
        if not self._quitting and self._config.settings.run_in_background:
            self.set_visible(False)
            return True  # stop the default destroy
        self._shutdown()
        return False
