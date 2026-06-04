"""The main application window and top-level controller."""

from __future__ import annotations

import glob
import logging

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GObject, Gtk  # noqa: E402

from veranda import APP_ID, __version__
from veranda.config import AppConfig, config_dir
from veranda.deck import DeckInfo, DeckManager
from veranda.dispatch import Dispatcher
from veranda.editor import ButtonEditor
from veranda.grid import DeckGrid
from veranda.input_backend import InputBackend
from veranda.library import ActionLibrary
from veranda.models import ActionItem, ButtonConfig, DeckState, Page, Profile
from veranda.screensaver import ScreensaverMonitor
from veranda.settings import SettingsDialog, prompt_text
from veranda.statusicon import TrayIcon
from veranda.background import request_background
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
        self.set_default_size(980, 660)

        self._config = AppConfig.load()
        self._input_backend = InputBackend()
        self._deck_manager = DeckManager(
            on_key_press=self._on_key_press,
            on_decks_changed=self._refresh,
        )
        self._dispatcher = Dispatcher(
            self._config,
            self._deck_manager,
            self._input_backend,
            switch_page=self._switch_page,
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
        self._deck_manager.start()
        if self._config.settings.run_in_background:
            self._enable_background()
        self._refresh()

    # -- actions / menu ---------------------------------------------------

    def _install_actions(self) -> None:
        for name, handler in (
            ("preferences", self._open_settings),
            ("rename_device", self.rename_device),
            ("import", lambda: self.import_profile_dialog()),
            ("export", lambda: self.export_profile_dialog()),
            ("about", self._show_about),
            ("quit", self._real_quit),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda _a, _p, h=handler: h())
            self.add_action(action)

    def _build_menu(self) -> Gio.Menu:
        menu = Gio.Menu()
        menu.append("Rename Device…", "win.rename_device")
        menu.append("Preferences", "win.preferences")
        backup = Gio.Menu()
        backup.append("Import Buttons…", "win.import")
        backup.append("Export Buttons…", "win.export")
        menu.append_section(None, backup)
        about = Gio.Menu()
        about.append("About Veranda", "win.about")
        about.append("Quit", "win.quit")
        menu.append_section(None, about)
        return menu

    # -- UI construction --------------------------------------------------

    def _build_ui(self) -> None:
        self._toasts = Adw.ToastOverlay()
        self._split = Adw.OverlaySplitView(
            sidebar_position=Gtk.PackType.END,
            min_sidebar_width=300,
            max_sidebar_width=420,
            sidebar_width_fraction=0.34,
        )
        self._toasts.set_child(self._split)
        self.set_content(self._toasts)

        self._split.set_content(self._build_content_pane())
        self._split.set_sidebar(self._build_sidebar_pane())

        breakpoint_ = Adw.Breakpoint.new(
            Adw.BreakpointCondition.parse("max-width: 720px")
        )
        breakpoint_.add_setter(self._split, "collapsed", True)
        self.add_breakpoint(breakpoint_)

    def _build_content_pane(self) -> Adw.ToolbarView:
        toolbar = Adw.ToolbarView()
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

        # Page navigation.
        nav = Gtk.Box(spacing=0)
        nav.add_css_class("linked")
        self._prev_btn = Gtk.Button(icon_name="go-previous-symbolic", tooltip_text="Previous page")
        self._prev_btn.connect("clicked", lambda _b: self._page_step(-1))
        self._next_btn = Gtk.Button(icon_name="go-next-symbolic", tooltip_text="Next page")
        self._next_btn.connect("clicked", lambda _b: self._page_step(1))
        nav.append(self._prev_btn)
        nav.append(self._next_btn)
        header.pack_start(nav)

        self._page_label = Gtk.Label(label="")
        self._page_label.add_css_class("dim-label")
        header.pack_start(self._page_label)

        add_page = Gtk.Button(icon_name="list-add-symbolic", tooltip_text="Add a page")
        add_page.connect("clicked", lambda _b: self._add_page())
        header.pack_start(add_page)
        self._remove_page_btn = Gtk.Button(
            icon_name="list-remove-symbolic", tooltip_text="Remove this page"
        )
        self._remove_page_btn.connect("clicked", lambda _b: self._remove_page())
        header.pack_start(self._remove_page_btn)

        # End: menu + sidebar toggle.
        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic", tooltip_text="Main menu")
        menu_btn.set_menu_model(self._build_menu())
        header.pack_end(menu_btn)

        toggle = Gtk.ToggleButton(icon_name="sidebar-show-right-symbolic", active=True)
        toggle.set_tooltip_text("Toggle the action library")
        self._split.bind_property(
            "show-sidebar", toggle, "active",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL,
        )
        header.pack_end(toggle)

        toolbar.add_top_bar(header)

        self._body = Gtk.Stack()
        self._grid = DeckGrid(self._on_drop, self._on_select)
        board = Gtk.Box(hexpand=True, vexpand=True)
        board.add_css_class("deck-board")
        board.append(self._grid)
        self._body.add_named(board, "grid")

        self._status = Adw.StatusPage(icon_name="input-tablet-symbolic")
        self._body.add_named(self._status, "status")
        toolbar.set_content(self._body)
        return toolbar

    def _build_sidebar_pane(self) -> Adw.ToolbarView:
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(
            Adw.WindowTitle(title="Actions", subtitle="Drag onto a button")
        )
        toolbar.add_top_bar(header)
        toolbar.set_content(ActionLibrary())
        return toolbar

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

        npages = len(profile.pages)
        self._page_label.set_text(f"Page {profile.active_page + 1} / {npages}")
        self._prev_btn.set_sensitive(profile.active_page > 0)
        self._next_btn.set_sensitive(profile.active_page < npages - 1)
        self._remove_page_btn.set_sensitive(npages > 1)

        self._grid.build(info, page)
        self._body.set_visible_child_name("grid")

        self._apply_brightness(serial)
        self._deck_manager.apply_page(serial, page)
        return False

    def _set_controls_sensitive(self, sensitive: bool) -> None:
        for widget in (
            self._device_drop, self._profile_drop,
            self._prev_btn, self._next_btn, self._remove_page_btn,
        ):
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

    def _remove_button(self, key: int) -> None:
        if self._current_serial is None:
            return
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

    def _apply_brightness(self, serial: str) -> None:
        """Push effective brightness to the device, honoring lock-dimming."""
        state = self._config.decks.get(serial)
        if state is None:
            return
        dimmed = self._screensaver_active and state.dim_on_lock
        self._deck_manager.set_brightness(serial, 0 if dimmed else state.brightness)

    # -- screensaver / lock sync -----------------------------------------

    def _on_screensaver_changed(self, active: bool) -> None:
        self._screensaver_active = active
        for serial in self._deck_manager.serials():
            self._apply_brightness(serial)

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

    def _page_step(self, delta: int) -> None:
        if self._current_serial is None:
            return
        profile = self._config.deck(self._current_serial).current_profile()
        self._switch_page(self._current_serial, profile.active_page + delta)

    def _add_page(self) -> None:
        if self._current_serial is None:
            return
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

    # -- menu handlers ----------------------------------------------------

    def _open_settings(self) -> None:
        SettingsDialog(self).present(self)

    def _show_about(self) -> None:
        about = Adw.AboutDialog(
            application_name="Veranda",
            application_icon=APP_ID,
            version=__version__,
            developer_name="Veranda contributors",
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

    def _toggle_window(self) -> None:
        if self.get_visible():
            self.set_visible(False)
        else:
            self.present()

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
        self._screensaver.stop()
        self._tray.stop()
        self._deck_manager.stop()
        self._input_backend.close()

    def _on_close(self, _window) -> bool:
        # When running in the background, closing just hides to the tray.
        if not self._quitting and self._config.settings.run_in_background:
            self.set_visible(False)
            return True  # stop the default destroy
        self._shutdown()
        return False
