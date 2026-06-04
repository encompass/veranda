"""Application entry point: sets up libadwaita, CSS, and the main window."""

from __future__ import annotations

import logging
import sys
from importlib import resources

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, Gtk  # noqa: E402

from veranda import APP_ID  # noqa: E402
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
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        _load_css()

    def do_activate(self) -> None:
        window = self.props.active_window
        if window is None:
            window = VerandaWindow(self)
            # On first launch, honor "start hidden" (stay in the background).
            if window.should_start_hidden():
                return
        window.present()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app = VerandaApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
