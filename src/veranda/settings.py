"""Settings window: manage profiles, device brightness, and backup."""

from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from veranda.models import Profile  # noqa: E402


def prompt_text(
    parent: Gtk.Widget,
    heading: str,
    initial: str,
    on_ok: Callable[[str], None],
    ok_label: str = "Save",
) -> None:
    """Show a small dialog with a single text entry."""
    dialog = Adw.AlertDialog(heading=heading)
    entry = Gtk.Entry(text=initial, activates_default=True)
    dialog.set_extra_child(entry)
    dialog.add_response("cancel", "Cancel")
    dialog.add_response("ok", ok_label)
    dialog.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
    dialog.set_default_response("ok")
    dialog.set_close_response("cancel")

    def on_response(_d, response):
        if response == "ok":
            name = entry.get_text().strip()
            if name:
                on_ok(name)

    dialog.connect("response", on_response)
    dialog.present(parent)


class SettingsDialog(Adw.PreferencesDialog):
    """Preferences UI bound to the main window's current deck."""

    def __init__(self, window) -> None:
        super().__init__()
        self._window = window
        self.set_title("Settings")
        self.set_search_enabled(False)

        self._profile_rows: list[Gtk.Widget] = []
        self._building = False

        self._map_rows: list = []
        self.add(self._build_general_page())
        self.add(self._build_profiles_page())
        self.add(self._build_automation_page())
        self.add(self._build_device_page())
        self.add(self._build_backup_page())

    # -- automation (focus-driven profile switching) ----------------------

    def _build_automation_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage(
            title="Automation", icon_name="emblem-synchronizing-symbolic"
        )
        group = Adw.PreferencesGroup(
            title="Profile auto-switch",
            description="Switch the active profile when a chosen app is focused. "
            "Requires the Veranda GNOME Shell extension to be enabled.",
        )
        toggle = Adw.SwitchRow(title="Switch profiles when apps are focused")
        toggle.set_active(self._window.get_app_settings().auto_switch)
        toggle.connect(
            "notify::active", lambda r, _p: self._window.set_auto_switch(r.get_active())
        )
        group.add(toggle)
        page.add(group)

        self._map_group = Adw.PreferencesGroup(title="App → Profile")
        add_btn = Gtk.Button(
            icon_name="list-add-symbolic", valign=Gtk.Align.CENTER,
            tooltip_text="Map an app to a profile",
        )
        add_btn.add_css_class("flat")
        add_btn.connect("clicked", self._on_add_mapping)
        self._map_group.set_header_suffix(add_btn)
        page.add(self._map_group)
        self._reload_mappings()
        return page

    def _reload_mappings(self) -> None:
        for row in self._map_rows:
            self._map_group.remove(row)
        self._map_rows.clear()

        names = self._window.profile_names()
        mapping = self._window.app_profiles()
        if not mapping:
            row = Adw.ActionRow(
                title="No apps mapped",
                subtitle="Add an app to switch to a profile when it’s focused",
            )
            self._map_group.add(row)
            self._map_rows.append(row)
            return

        for desktop_id, profile_name in sorted(mapping.items()):
            row = Adw.ComboRow(title=self._app_name(desktop_id), subtitle=desktop_id)
            model = Gtk.StringList()
            for name in names:
                model.append(name)
            row.set_model(model)
            if profile_name in names:
                row.set_selected(names.index(profile_name))
            row.connect("notify::selected", self._on_mapping_changed, desktop_id, names)
            remove = Gtk.Button(
                icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER
            )
            remove.add_css_class("flat")
            remove.connect("clicked", self._on_remove_mapping, desktop_id)
            row.add_suffix(remove)
            self._map_group.add(row)
            self._map_rows.append(row)

    def _on_mapping_changed(self, row, _pspec, desktop_id, names) -> None:
        idx = row.get_selected()
        if 0 <= idx < len(names):
            self._window.set_app_profile(desktop_id, names[idx])

    def _on_remove_mapping(self, _btn, desktop_id) -> None:
        self._window.remove_app_profile(desktop_id)
        self._reload_mappings()

    def _on_add_mapping(self, _btn) -> None:
        from veranda.apppicker import AppPicker

        names = self._window.profile_names()
        if not names:
            self._window.notify("Connect a device with profiles first")
            return

        def on_pick(desktop_id, _name, _icon):
            self._window.set_app_profile(desktop_id, names[0])
            self._reload_mappings()

        AppPicker(on_pick).present(self._window)

    def _app_name(self, desktop_id: str) -> str:
        try:
            from gi.repository import GioUnix

            did = desktop_id if desktop_id.endswith(".desktop") else desktop_id + ".desktop"
            app = GioUnix.DesktopAppInfo.new(did)
            if app is not None:
                return app.get_display_name()
        except Exception:  # noqa: BLE001
            pass
        return desktop_id

    # -- general ----------------------------------------------------------

    def _build_general_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage(title="General", icon_name="preferences-system-symbolic")
        settings = self._window.get_app_settings()

        group = Adw.PreferencesGroup(
            title="Background",
            description="Keep Veranda running in the top bar when its window is closed.",
        )
        run = Adw.SwitchRow(
            title="Run in the background",
            subtitle="Close to the top bar instead of quitting",
        )
        run.set_active(settings.run_in_background)

        hidden = Adw.SwitchRow(
            title="Start hidden",
            subtitle="Launch into the background without showing the window",
        )
        hidden.set_active(settings.start_hidden)
        hidden.set_sensitive(settings.run_in_background)

        autostart_row = Adw.SwitchRow(
            title="Open at login",
            subtitle="Start Veranda automatically when you log in",
        )
        autostart_row.set_active(self._window.autostart_enabled())

        def on_run(row, _p):
            active = row.get_active()
            self._window.set_run_in_background(active)
            hidden.set_sensitive(active)

        def on_hidden(row, _p):
            self._window.set_start_hidden(row.get_active())

        def on_autostart(row, _p):
            self._window.set_autostart(row.get_active())

        run.connect("notify::active", on_run)
        hidden.connect("notify::active", on_hidden)
        autostart_row.connect("notify::active", on_autostart)
        group.add(run)
        group.add(hidden)
        group.add(autostart_row)
        page.add(group)
        return page

    # -- profiles ---------------------------------------------------------

    def _build_profiles_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage(title="Profiles", icon_name="view-list-symbolic")
        self._profiles_group = Adw.PreferencesGroup(
            title="Profiles",
            description="Each profile is an independent set of pages and buttons.",
        )
        add_btn = Gtk.Button(icon_name="list-add-symbolic", valign=Gtk.Align.CENTER)
        add_btn.add_css_class("flat")
        add_btn.set_tooltip_text("Add a profile")
        add_btn.connect("clicked", self._on_add_profile)
        self._profiles_group.set_header_suffix(add_btn)
        page.add(self._profiles_group)
        self._reload_profiles()
        return page

    def _reload_profiles(self) -> None:
        for row in self._profile_rows:
            self._profiles_group.remove(row)
        self._profile_rows.clear()

        state = self._window.current_state()
        if state is None:
            row = Adw.ActionRow(
                title="No device", subtitle="Connect a Stream Deck to manage profiles"
            )
            self._profiles_group.add(row)
            self._profile_rows.append(row)
            return

        self._building = True
        group_leader: Gtk.CheckButton | None = None
        for idx, profile in enumerate(state.profiles):
            row = Adw.ActionRow(
                title=profile.name,
                subtitle=f"{len(profile.pages)} page(s)",
            )
            radio = Gtk.CheckButton(valign=Gtk.Align.CENTER)
            radio.set_tooltip_text("Make active")
            if group_leader is None:
                group_leader = radio
            else:
                radio.set_group(group_leader)
            radio.set_active(idx == state.active_profile)
            radio.connect("toggled", self._on_activate_profile, idx)
            row.add_prefix(radio)

            row.add_suffix(self._row_button(
                "document-edit-symbolic", "Rename", self._on_rename_profile, idx))
            row.add_suffix(self._row_button(
                "edit-copy-symbolic", "Duplicate", self._on_duplicate_profile, idx))
            delete = self._row_button(
                "user-trash-symbolic", "Delete", self._on_delete_profile, idx)
            delete.set_sensitive(len(state.profiles) > 1)
            row.add_suffix(delete)

            self._profiles_group.add(row)
            self._profile_rows.append(row)
        self._building = False

    def _row_button(self, icon, tip, handler, idx) -> Gtk.Button:
        btn = Gtk.Button(icon_name=icon, valign=Gtk.Align.CENTER)
        btn.add_css_class("flat")
        btn.set_tooltip_text(tip)
        btn.connect("clicked", handler, idx)
        return btn

    def _on_add_profile(self, _btn) -> None:
        state = self._window.current_state()
        if state is None:
            return
        default = f"Profile {len(state.profiles) + 1}"

        def create(name):
            state.profiles.append(Profile(name=name))
            state.active_profile = len(state.profiles) - 1
            self._window.reload()
            self._reload_profiles()

        prompt_text(self._window, "New profile name", default, create, ok_label="Add")

    def _on_rename_profile(self, _btn, idx) -> None:
        state = self._window.current_state()
        if state is None or idx >= len(state.profiles):
            return

        def rename(name):
            state.profiles[idx].name = name
            self._window.reload()
            self._reload_profiles()

        prompt_text(self._window, "Rename profile", state.profiles[idx].name, rename)

    def _on_duplicate_profile(self, _btn, idx) -> None:
        state = self._window.current_state()
        if state is None or idx >= len(state.profiles):
            return
        clone = state.profiles[idx].clone(f"{state.profiles[idx].name} copy")
        state.profiles.insert(idx + 1, clone)
        self._window.reload()
        self._reload_profiles()

    def _on_delete_profile(self, _btn, idx) -> None:
        state = self._window.current_state()
        if state is None or len(state.profiles) <= 1 or idx >= len(state.profiles):
            return
        name = state.profiles[idx].name
        dialog = Adw.AlertDialog(
            heading="Delete profile?",
            body=f"“{name}” and all of its pages will be removed.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Delete")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def on_response(_d, response):
            if response != "delete":
                return
            del state.profiles[idx]
            state.active_profile = max(0, min(state.active_profile, len(state.profiles) - 1))
            self._window.reload()
            self._reload_profiles()

        dialog.connect("response", on_response)
        dialog.present(self._window)

    def _on_activate_profile(self, radio, idx) -> None:
        if self._building or not radio.get_active():
            return
        self._window.switch_profile(idx)
        self._reload_profiles()

    # -- device -----------------------------------------------------------

    def _build_device_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage(title="Device", icon_name="input-tablet-symbolic")
        state = self._window.current_state()
        info = self._window.deck_info()

        identity = Adw.PreferencesGroup(title="Identity")
        name_row = Adw.EntryRow(title="Device name")
        name_row.set_text(state.name if state else "")
        name_row.set_sensitive(state is not None)
        name_row.set_show_apply_button(True)

        def on_name_apply(row):
            st = self._window.current_state()
            if st is not None:
                st.name = row.get_text().strip()
                self._window.reload()

        name_row.connect("apply", on_name_apply)
        identity.add(name_row)
        page.add(identity)

        controls = Adw.PreferencesGroup(title="Display")
        bright = Adw.SpinRow(
            title="Brightness",
            subtitle="Percent",
            adjustment=Gtk.Adjustment(
                lower=0, upper=100, step_increment=5,
                value=(state.brightness if state else 60),
            ),
        )
        bright.set_sensitive(state is not None)
        bright.connect("notify::value", lambda r, _p: self._window.set_brightness(int(r.get_value())))
        controls.add(bright)

        dim = Adw.SwitchRow(
            title="Blank screen when locked",
            subtitle="Turn the deck off while the session is locked, restore on unlock",
        )
        dim.set_active(state.dim_on_lock if state else False)
        available = self._window.screensaver_available()
        dim.set_sensitive(state is not None and available)
        if not available:
            dim.set_subtitle("Requires the GNOME screensaver service")
        dim.connect("notify::active", lambda r, _p: self._window.set_dim_on_lock(r.get_active()))
        controls.add(dim)
        page.add(controls)

        about = Adw.PreferencesGroup(title="Connected Device")
        if info is not None:
            for title, value in (
                ("Model", info.deck_type),
                ("Serial", info.serial),
                ("Keys", f"{info.key_count} ({info.cols}×{info.rows})"),
            ):
                row = Adw.ActionRow(title=title, subtitle=value)
                row.add_css_class("property")
                about.add(row)
        else:
            about.add(Adw.ActionRow(title="No device connected"))
        page.add(about)
        return page

    # -- backup -----------------------------------------------------------

    def _build_backup_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage(title="Backup", icon_name="folder-download-symbolic")
        group = Adw.PreferencesGroup(
            title="Import and Export",
            description="Share a profile's buttons as a file, or load one in.",
        )

        export_row = Adw.ActionRow(
            title="Export current profile", subtitle="Save this profile's buttons to a file"
        )
        export_btn = Gtk.Button(label="Export…", valign=Gtk.Align.CENTER)
        export_btn.connect("clicked", lambda _b: self._window.export_profile_dialog())
        export_row.add_suffix(export_btn)
        export_row.set_activatable_widget(export_btn)
        group.add(export_row)

        import_row = Adw.ActionRow(
            title="Import profile", subtitle="Add a profile from a file"
        )
        import_btn = Gtk.Button(label="Import…", valign=Gtk.Align.CENTER)
        import_btn.connect(
            "clicked",
            lambda _b: self._window.import_profile_dialog(on_done=self._reload_profiles),
        )
        import_row.add_suffix(import_btn)
        import_row.set_activatable_widget(import_btn)
        group.add(import_row)

        page.add(group)
        return page
