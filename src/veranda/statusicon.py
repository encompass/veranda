"""A StatusNotifierItem (SNI / AppIndicator) tray icon over raw D-Bus.

GTK4 can't use the GTK3-based libappindicator, so this speaks the SNI and
``com.canonical.dbusmenu`` protocols directly via Gio. The icon only renders
when a StatusNotifierWatcher host is present (on GNOME that means the
"AppIndicator/KStatusNotifier Support" / "Ubuntu AppIndicators" extension is
enabled); if no host appears, this stays dormant and harmless.
"""

from __future__ import annotations

import logging
import os
from typing import Callable

from gi.repository import Gio, GLib

log = logging.getLogger(__name__)

WATCHER = "org.kde.StatusNotifierWatcher"
WATCHER_PATH = "/StatusNotifierWatcher"

_ITEM_XML = """
<node>
 <interface name="org.kde.StatusNotifierItem">
  <property name="Category" type="s" access="read"/>
  <property name="Id" type="s" access="read"/>
  <property name="Title" type="s" access="read"/>
  <property name="Status" type="s" access="read"/>
  <property name="IconName" type="s" access="read"/>
  <property name="IconThemePath" type="s" access="read"/>
  <property name="ItemIsMenu" type="b" access="read"/>
  <property name="Menu" type="o" access="read"/>
  <method name="Activate">
   <arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/>
  </method>
  <method name="SecondaryActivate">
   <arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/>
  </method>
  <method name="ContextMenu">
   <arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/>
  </method>
  <method name="Scroll">
   <arg name="delta" type="i" direction="in"/><arg name="orientation" type="s" direction="in"/>
  </method>
  <signal name="NewIcon"/>
  <signal name="NewTitle"/>
  <signal name="NewStatus"><arg name="status" type="s"/></signal>
 </interface>
</node>
"""

_MENU_XML = """
<node>
 <interface name="com.canonical.dbusmenu">
  <property name="Version" type="u" access="read"/>
  <property name="Status" type="s" access="read"/>
  <property name="TextDirection" type="s" access="read"/>
  <property name="IconThemePath" type="as" access="read"/>
  <method name="GetLayout">
   <arg type="i" name="parentId" direction="in"/>
   <arg type="i" name="recursionDepth" direction="in"/>
   <arg type="as" name="propertyNames" direction="in"/>
   <arg type="u" name="revision" direction="out"/>
   <arg type="(ia{sv}av)" name="layout" direction="out"/>
  </method>
  <method name="GetGroupProperties">
   <arg type="ai" name="ids" direction="in"/>
   <arg type="as" name="propertyNames" direction="in"/>
   <arg type="a(ia{sv})" name="properties" direction="out"/>
  </method>
  <method name="GetProperty">
   <arg type="i" name="id" direction="in"/>
   <arg type="s" name="name" direction="in"/>
   <arg type="v" name="value" direction="out"/>
  </method>
  <method name="Event">
   <arg type="i" name="id" direction="in"/>
   <arg type="s" name="eventId" direction="in"/>
   <arg type="v" name="data" direction="in"/>
   <arg type="u" name="timestamp" direction="in"/>
  </method>
  <method name="AboutToShow">
   <arg type="i" name="id" direction="in"/>
   <arg type="b" name="needUpdate" direction="out"/>
  </method>
  <signal name="LayoutUpdated"><arg type="u" name="revision"/><arg type="i" name="parent"/></signal>
  <signal name="ItemsPropertiesUpdated">
   <arg type="a(ia{sv})" name="updatedProps"/><arg type="a(ias)" name="removedProps"/>
  </signal>
 </interface>
</node>
"""


class TrayIcon:
    """Publishes a StatusNotifierItem with a small menu.

    Menu item ids: 1 = primary "show" action, 3 = quit.
    """

    def __init__(
        self,
        item_id: str,
        title: str,
        icon_name: str,
        on_activate: Callable[[], None],
        on_show: Callable[[], None],
        on_quit: Callable[[], None],
        show_label: str = "Show",
        quit_label: str = "Quit",
    ) -> None:
        self._id = item_id
        self._title = title
        self._icon = icon_name
        self._on_activate = on_activate
        self._on_show = on_show
        self._on_quit = on_quit
        self._show_label = show_label
        self._quit_label = quit_label

        self._conn: Gio.DBusConnection | None = None
        self._bus_name = f"org.kde.StatusNotifierItem-{os.getpid()}-1"
        self._own_id = 0
        self._watch_id = 0
        self._item_reg = 0
        self._menu_reg = 0
        self._host_available = False
        self._started = False

        self._item_iface = Gio.DBusNodeInfo.new_for_xml(_ITEM_XML).interfaces[0]
        self._menu_iface = Gio.DBusNodeInfo.new_for_xml(_MENU_XML).interfaces[0]

    @property
    def host_available(self) -> bool:
        return self._host_available

    # -- lifecycle --------------------------------------------------------

    def start(self) -> None:
        if self._started:
            return
        try:
            self._conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            self._item_reg = self._conn.register_object(
                "/StatusNotifierItem", self._item_iface,
                self._item_method, self._item_get_prop, None,
            )
            self._menu_reg = self._conn.register_object(
                "/MenuBar", self._menu_iface,
                self._menu_method, self._menu_get_prop, None,
            )
            self._own_id = Gio.bus_own_name_on_connection(
                self._conn, self._bus_name, Gio.BusNameOwnerFlags.NONE,
                self._on_name_acquired, None,
            )
            self._watch_id = Gio.bus_watch_name_on_connection(
                self._conn, WATCHER, Gio.BusNameWatcherFlags.NONE,
                self._on_watcher_up, self._on_watcher_down,
            )
            self._started = True
            log.info("tray icon published as %s", self._bus_name)
        except GLib.Error as exc:
            log.info("tray icon unavailable: %s", exc)

    def stop(self) -> None:
        if not self._started:
            return
        if self._watch_id:
            Gio.bus_unwatch_name(self._watch_id)
        if self._own_id:
            Gio.bus_unown_name(self._own_id)
        if self._conn is not None:
            if self._item_reg:
                self._conn.unregister_object(self._item_reg)
            if self._menu_reg:
                self._conn.unregister_object(self._menu_reg)
        self._watch_id = self._own_id = self._item_reg = self._menu_reg = 0
        self._host_available = False
        self._started = False

    # -- watcher registration --------------------------------------------

    def _on_name_acquired(self, _conn, _name) -> None:
        self._register_with_watcher()

    def _on_watcher_up(self, _conn, _name, _owner) -> None:
        self._host_available = True
        self._register_with_watcher()

    def _on_watcher_down(self, _conn, _name) -> None:
        self._host_available = False

    def _register_with_watcher(self) -> None:
        if self._conn is None:
            return

        def done(conn, result):
            try:
                conn.call_finish(result)
                self._host_available = True
                log.info("registered with StatusNotifierWatcher")
            except GLib.Error as exc:
                log.debug("watcher registration failed (no host yet?): %s", exc)

        self._conn.call(
            WATCHER, WATCHER_PATH, WATCHER, "RegisterStatusNotifierItem",
            GLib.Variant("(s)", (self._bus_name,)),
            None, Gio.DBusCallFlags.NONE, -1, None, done,
        )

    # -- StatusNotifierItem interface ------------------------------------

    def _item_get_prop(self, _conn, _sender, _path, _iface, name):
        values = {
            "Category": GLib.Variant("s", "ApplicationStatus"),
            "Id": GLib.Variant("s", self._id),
            "Title": GLib.Variant("s", self._title),
            "Status": GLib.Variant("s", "Active"),
            "IconName": GLib.Variant("s", self._icon),
            "IconThemePath": GLib.Variant("s", ""),
            "ItemIsMenu": GLib.Variant("b", False),
            "Menu": GLib.Variant("o", "/MenuBar"),
        }
        return values.get(name)

    def _item_method(self, _conn, _sender, _path, _iface, method, _params, invocation):
        if method in ("Activate", "SecondaryActivate"):
            self._on_activate()
        invocation.return_value(None)

    # -- com.canonical.dbusmenu interface --------------------------------

    def _menu_items(self) -> list[dict]:
        return [
            {"id": 1, "label": self._show_label},
            {"id": 2, "type": "separator"},
            {"id": 3, "label": self._quit_label},
        ]

    def _item_props(self, item: dict) -> dict:
        if item.get("type") == "separator":
            return {"type": GLib.Variant("s", "separator")}
        return {
            "label": GLib.Variant("s", item["label"]),
            "enabled": GLib.Variant("b", True),
            "visible": GLib.Variant("b", True),
        }

    def _menu_get_prop(self, _conn, _sender, _path, _iface, name):
        values = {
            "Version": GLib.Variant("u", 3),
            "Status": GLib.Variant("s", "normal"),
            "TextDirection": GLib.Variant("s", "ltr"),
            "IconThemePath": GLib.Variant("as", []),
        }
        return values.get(name)

    def _menu_method(self, _conn, _sender, _path, _iface, method, params, invocation):
        if method == "GetLayout":
            # 'av' children must be bare variants; the root is a plain tuple.
            children = [
                GLib.Variant("(ia{sv}av)", (item["id"], self._item_props(item), []))
                for item in self._menu_items()
            ]
            root = (0, {"children-display": GLib.Variant("s", "submenu")}, children)
            invocation.return_value(GLib.Variant("(u(ia{sv}av))", (1, root)))
        elif method == "GetGroupProperties":
            entries = [
                (item["id"], self._item_props(item)) for item in self._menu_items()
            ]
            invocation.return_value(GLib.Variant("(a(ia{sv}))", (entries,)))
        elif method == "GetProperty":
            item_id, prop = params.unpack()
            match = next((i for i in self._menu_items() if i["id"] == item_id), None)
            value = self._item_props(match).get(prop) if match else None
            invocation.return_value(
                GLib.Variant("(v)", (value or GLib.Variant("s", ""),))
            )
        elif method == "Event":
            item_id, event_id, _data, _ts = params.unpack()
            if event_id == "clicked":
                if item_id == 1:
                    self._on_show()
                elif item_id == 3:
                    self._on_quit()
            invocation.return_value(None)
        elif method == "AboutToShow":
            invocation.return_value(GLib.Variant("(b)", (False,)))
        else:
            invocation.return_value(None)
