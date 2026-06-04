"""Extra actions: copy text to the clipboard, open a folder in Files."""

from __future__ import annotations

from typing import Callable

from veranda import launch
from veranda.actions.base import Action, ActionContext


class CopyTextAction(Action):
    TYPE_ID = "copy_text"
    NAME = "Copy Text"
    DESCRIPTION = "Copy a snippet to the clipboard"
    ICON = "edit-copy-symbolic"
    CATEGORY = "Input"

    @property
    def text(self) -> str:
        return self.params.get("text", "")

    def default_label(self) -> str:
        return ""

    def summary(self) -> str:
        return self.text or "No text set"

    def build_editor_rows(self, button, on_change: Callable[[], None]):
        from gi.repository import Adw

        row = Adw.EntryRow(title="Text to copy")
        row.set_text(self.text)
        row.connect("changed", lambda r: (self.params.__setitem__("text", r.get_text()), on_change()))
        return [row]

    def execute(self, ctx: ActionContext) -> None:
        if not self.text:
            return
        from gi.repository import Gdk

        display = Gdk.Display.get_default()
        if display is not None:
            display.get_clipboard().set(self.text)
            ctx.notify("Copied to clipboard")


class OpenFolderAction(Action):
    TYPE_ID = "open_folder"
    NAME = "Open Folder"
    DESCRIPTION = "Open a folder in Files"
    ICON = "folder-symbolic"
    CATEGORY = "System"

    @property
    def path(self) -> str:
        return self.params.get("path", "")

    def default_label(self) -> str:
        return ""

    def summary(self) -> str:
        return self.path or "No folder set"

    def build_editor_rows(self, button, on_change: Callable[[], None]):
        from gi.repository import Adw, Gtk

        row = Adw.EntryRow(title="Folder path")
        row.set_text(self.path)
        row.connect("changed", lambda r: (self.params.__setitem__("path", r.get_text()), on_change()))

        choose = Gtk.Button(icon_name="folder-open-symbolic", valign=Gtk.Align.CENTER)
        choose.add_css_class("flat")
        choose.set_tooltip_text("Choose a folder")

        def on_choose(_btn):
            dialog = Gtk.FileDialog(title="Choose a folder")

            def done(dlg, result):
                try:
                    folder = dlg.select_folder_finish(result)
                except Exception:  # noqa: BLE001 - cancelled
                    return
                if folder is not None and folder.get_path():
                    row.set_text(folder.get_path())

            dialog.select_folder(row.get_root(), None, done)

        choose.connect("clicked", on_choose)
        row.add_suffix(choose)
        return [row]

    def execute(self, ctx: ActionContext) -> None:
        path = self.path.strip()
        if path:
            launch.run(["xdg-open", path])
