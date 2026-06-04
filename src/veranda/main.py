"""Application entry point: sets up libadwaita, CSS, and the main window."""

from __future__ import annotations

import logging
import sys
from importlib import resources

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, Gtk  # noqa: E402

from veranda import APP_ID, autostart, cli  # noqa: E402
from veranda.window import VerandaWindow  # noqa: E402

log = logging.getLogger(__name__)


def _load_css() -> None:
    provider = Gtk.CssProvider()
    css = resources.files("veranda").joinpath("style.css").read_bytes()
    provider.load_from_data(css)
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(),
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )


class VerandaApp(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )
        self._window: VerandaWindow | None = None
        self._first_activation = True
        cli.register_options(self)

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        _load_css()
        autostart.ensure_icon()
        autostart.ensure_app_desktop_entry()  # launchable + lets the extension start us
        autostart.ensure_search_provider()  # profiles in the Shell overview search
        # "app.show" lets a notification (or the bus) bring the window forward.
        show = Gio.SimpleAction.new("show", None)
        show.connect("activate", lambda *_a: self._present())
        self.add_action(show)

    def do_command_line(self, command_line: Gio.ApplicationCommandLine) -> int:
        opts = command_line.get_options_dict()
        if cli.has_control_options(opts):
            # Control options act on a running instance. When invoked over the
            # bus (is_remote), self._window is the live primary window. When no
            # instance is running, this process briefly became primary but has
            # no window to drive — report that and exit without launching a UI.
            if self._window is None:
                command_line.printerr_literal("Veranda is not running.\n")
                command_line.set_exit_status(1)
                return 1
            status = cli.handle(
                self._window,
                opts,
                command_line.print_literal,
                command_line.printerr_literal,
            )
            command_line.set_exit_status(status)
            return status
        # No control options: behave like a normal launch / re-activation.
        self.activate()
        return 0

    def do_activate(self) -> None:
        # Track our own window reference: active_window is None while hidden,
        # so relying on it would spawn duplicate invisible windows.
        if self._window is None:
            self._window = VerandaWindow(self)
        first = self._first_activation
        self._first_activation = False
        # Only the very first launch honors "start hidden"; any later
        # activation (clicking the app icon, a second launch) shows the window.
        if first and self._window.should_start_hidden():
            self._notify_running_hidden()
            return
        self._present()

    def _present(self) -> None:
        if self._window is not None:
            self._window.present()

    def _notify_running_hidden(self) -> None:
        note = Gio.Notification.new("Veranda is running in the background")
        note.set_body(
            "Open it again from its app icon, or quit it from the tray menu. "
            "For a top-bar icon, enable the AppIndicator GNOME extension."
        )
        note.set_default_action("app.show")
        try:
            self.send_notification("veranda-running", note)
        except Exception:  # noqa: BLE001 - notifications are best-effort
            pass


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app = VerandaApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
