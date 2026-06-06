// Veranda GNOME Shell extension — a native Quick Settings entry + top-bar
// indicator that drives the running Veranda app over D-Bus.

import GObject from 'gi://GObject';
import Gio from 'gi://Gio';
import GioUnix from 'gi://GioUnix';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import St from 'gi://St';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import * as QuickSettings from 'resource:///org/gnome/shell/ui/quickSettings.js';
import {Slider} from 'resource:///org/gnome/shell/ui/slider.js';

const BUS_NAME = 'com.encompass.Veranda';
const OBJ_PATH = '/com/encompass/Veranda';
const APP_DESKTOP = 'com.encompass.Veranda.desktop';
const ICON = 'input-tablet-symbolic';

const ControlIface = `
<node>
 <interface name="com.encompass.Veranda.Control">
  <method name="Show"/>
  <method name="Hide"/>
  <method name="ToggleVisible"/>
  <method name="Quit"/>
  <method name="SetActiveProfile"><arg type="u" direction="in"/></method>
  <method name="SetBrightness"><arg type="i" direction="in"/></method>
  <method name="GetState"><arg type="a{sv}" direction="out"/></method>
  <method name="GetVirtualWindows"><arg type="a(siib)" direction="out"/></method>
  <method name="ReportVirtualWindowMoved">
   <arg type="s" direction="in"/><arg type="i" direction="in"/><arg type="i" direction="in"/>
  </method>
  <signal name="StateChanged"/>
 </interface>
</node>`;
const ControlProxy = Gio.DBusProxy.makeProxyWrapper(ControlIface);

// A brightness slider row inside the toggle's menu.
const BrightnessItem = GObject.registerClass(
class BrightnessItem extends PopupMenu.PopupBaseMenuItem {
    _init(ext) {
        super._init({activate: false, can_focus: false});
        this._ext = ext;
        this._updating = false;

        this.add_child(new St.Icon({
            icon_name: 'display-brightness-symbolic',
            style_class: 'popup-menu-icon',
        }));
        this._slider = new Slider(0);
        this._slider.x_expand = true;
        this.add_child(this._slider);

        this._slider.connect('notify::value', () => {
            if (this._updating)
                return;
            this._ext.callSetBrightness(Math.round(this._slider.value * 100));
        });
    }

    setValue(percent) {
        this._updating = true;
        this._slider.value = Math.max(0, Math.min(1, percent / 100));
        this._updating = false;
    }
});

const VerandaToggle = GObject.registerClass(
class VerandaToggle extends QuickSettings.QuickMenuToggle {
    _init(ext) {
        super._init({title: 'Veranda', iconName: ICON, toggleMode: true});
        this._ext = ext;
        this.menu.setHeader(ICON, 'Veranda', null);

        this._brightness = new BrightnessItem(ext);
        this.menu.addMenuItem(this._brightness);
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        this._profiles = new PopupMenu.PopupMenuSection();
        this.menu.addMenuItem(this._profiles);
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        this.menu.addAction('Show Window', () => this._ext.call('Show'));
        this.menu.addAction('Quit Veranda', () => this._ext.call('Quit'));

        this.connect('clicked', () => {
            // toggleMode flips `checked` before this handler runs.
            this._ext.call(this.checked ? 'Show' : 'Hide');
        });
    }

    sync(state) {
        const running = state !== null;
        const connected = running && state.connected;
        this.checked = running && state.visible;
        this.subtitle = !running
            ? 'Not running'
            : connected ? state.device_name : 'No device';

        this.menu.setHeader(
            ICON,
            connected ? state.device_name : 'Veranda',
            running ? (connected ? null : 'No device connected') : 'App not running');

        this._brightness.visible = connected;
        if (connected)
            this._brightness.setValue(state.brightness);

        this._profiles.removeAll();
        if (!running)
            return;
        state.profiles.forEach((name, i) => {
            const item = new PopupMenu.PopupMenuItem(name);
            if (i === state.active_profile)
                item.setOrnament(PopupMenu.Ornament.CHECK);
            item.connect('activate', () => this._ext.callSetProfile(i));
            this._profiles.addMenuItem(item);
        });
    }
});

const VerandaIndicator = GObject.registerClass(
class VerandaIndicator extends QuickSettings.SystemIndicator {
    _init(ext) {
        super._init();
        this._icon = this._addIndicator();
        this._icon.iconName = ICON;
        this._toggle = new VerandaToggle(ext);
        this.quickSettingsItems.push(this._toggle);
    }

    sync(state) {
        // Top-bar icon appears only when a Stream Deck is actually connected.
        this._icon.visible = state !== null && state.connected;
        this._toggle.sync(state);
    }
});

export default class VerandaExtension extends Extension {
    enable() {
        this._proxy = null;
        this._signalId = 0;
        this._showOnConnect = false;
        this._indicator = new VerandaIndicator(this);
        Main.panel.statusArea.quickSettings.addExternalIndicator(this._indicator);

        this._watchId = Gio.bus_watch_name(
            Gio.BusType.SESSION, BUS_NAME, Gio.BusNameWatcherFlags.NONE,
            () => this._connect(),
            () => this._disconnectProxy());

        // Report the focused app so Veranda can auto-switch profiles.
        this._focusTimeout = 0;
        this._focusId = global.display.connect(
            'notify::focus-window', () => this._scheduleFocusPush());

        // Place / keep-above Veranda's virtual deck windows (the app can't do
        // this itself on Wayland).
        this._tracked = new Map();        // Meta.Window -> [signalIds…]
        this._virtualSyncTimeout = 0;
        this._windowCreatedId = global.display.connect(
            'window-created', () => this._scheduleVirtualSync());
        // Report the final position immediately when the user finishes dragging
        // a tracked virtual deck (more reliable than the debounced move signal).
        this._grabEndId = global.display.connect(
            'grab-op-end', (_d, win, _op) => this._reportPosition(win));
    }

    _reportPosition(win) {
        if (!win || !this._proxy || !this._tracked.has(win))
            return;
        const r = win.get_frame_rect();
        this._proxy.ReportVirtualWindowMovedRemote(win.get_title(), r.x, r.y);
    }

    _scheduleVirtualSync() {
        if (this._virtualSyncTimeout)
            return;
        this._virtualSyncTimeout = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 200, () => {
            this._virtualSyncTimeout = 0;
            this._syncVirtualWindows();
            return GLib.SOURCE_REMOVE;
        });
    }

    _syncVirtualWindows() {
        if (!this._proxy)
            return;
        this._proxy.GetVirtualWindowsRemote((result, error) => {
            if (error || !result)
                return;
            const wanted = new Map();  // title -> {x, y, onTop}
            for (const [title, x, y, onTop] of result[0])
                wanted.set(title, {x, y, onTop});
            for (const actor of global.get_window_actors()) {
                const win = actor.meta_window;
                const title = win.get_title?.();
                if (!title || !wanted.has(title))
                    continue;
                const {x, y, onTop} = wanted.get(title);
                try {
                    if (onTop)
                        win.make_above();
                    else
                        win.unmake_above();
                    win.stick();  // show on all workspaces
                    if (!this._tracked.has(win)) {
                        win.move_frame(true, x, y);  // initial placement only
                        this._trackWindow(win, title);
                    }
                } catch (e) {
                    logError(e, 'Veranda: placing virtual window');
                }
            }
        });
    }

    _trackWindow(win, title) {
        let saveTimeout = 0;
        const posId = win.connect('position-changed', () => {
            if (saveTimeout)
                GLib.source_remove(saveTimeout);
            saveTimeout = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 350, () => {
                saveTimeout = 0;
                const r = win.get_frame_rect();
                this._proxy?.ReportVirtualWindowMovedRemote(title, r.x, r.y);
                return GLib.SOURCE_REMOVE;
            });
        });
        const goneId = win.connect('unmanaging', () => {
            if (saveTimeout)
                GLib.source_remove(saveTimeout);
            this._untrackWindow(win);
        });
        this._tracked.set(win, [posId, goneId]);
    }

    _untrackWindow(win) {
        const ids = this._tracked.get(win);
        if (!ids)
            return;
        for (const id of ids) {
            try {
                win.disconnect(id);
            } catch (e) {
                // window already gone
            }
        }
        this._tracked.delete(win);
    }

    _scheduleFocusPush() {
        if (this._focusTimeout)
            GLib.source_remove(this._focusTimeout);
        this._focusTimeout = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 150, () => {
            this._focusTimeout = 0;
            this._pushFocus();
            return GLib.SOURCE_REMOVE;
        });
    }

    _pushFocus() {
        if (!this._proxy)
            return;
        const win = global.display.get_focus_window();
        if (!win)
            return;
        const app = Shell.WindowTracker.get_default().get_window_app(win);
        const id = app ? app.get_id() : null;
        if (id) {
            try {
                this._proxy.SetFocusedAppRemote(id);
            } catch (e) {
                logError(e, 'Veranda: SetFocusedApp failed');
            }
        }
    }

    _connect() {
        try {
            this._proxy = ControlProxy(Gio.DBus.session, BUS_NAME, OBJ_PATH);
            this._signalId = this._proxy.connectSignal('StateChanged', () => this._refresh());
            this._refresh();
            this._pushFocus();  // send current focus as soon as the app appears
            if (this._showOnConnect) {
                this._showOnConnect = false;
                this._proxy.ShowRemote();
            }
        } catch (e) {
            logError(e, 'Veranda: failed to connect to app');
            this._proxy = null;
        }
    }

    _disconnectProxy() {
        if (this._proxy && this._signalId)
            this._proxy.disconnectSignal(this._signalId);
        this._signalId = 0;
        this._proxy = null;
        this._indicator?.sync(null);
    }

    _refresh() {
        if (!this._proxy) {
            this._indicator?.sync(null);
            return;
        }
        this._proxy.GetStateRemote((result, error) => {
            if (error) {
                logError(error, 'Veranda: GetState failed');
                return;
            }
            this._indicator?.sync(this._unpack(result?.[0] ?? {}));
        });
        this._scheduleVirtualSync();
    }

    _unpack(dict) {
        const v = (k, fallback) => (k in dict ? dict[k].deepUnpack() : fallback);
        return {
            connected: v('connected', false),
            device_name: v('device_name', ''),
            brightness: v('brightness', 0),
            profiles: v('profiles', []),
            active_profile: v('active_profile', 0),
            visible: v('visible', false),
        };
    }

    _launchApp(showAfter) {
        if (showAfter)
            this._showOnConnect = true;
        const app = GioUnix.DesktopAppInfo.new(APP_DESKTOP);
        if (!app) {
            logError(new Error(`Veranda: ${APP_DESKTOP} not found`));
            return;
        }
        try {
            app.launch([], null);
        } catch (e) {
            logError(e, 'Veranda: launch failed');
        }
    }

    call(method) {
        if (!this._proxy) {
            if (method === 'Show')
                this._launchApp(true);  // start the app, then show it once connected
            return;
        }
        this._proxy[`${method}Remote`]();
    }

    callSetProfile(index) {
        this._proxy?.SetActiveProfileRemote(index);
    }

    callSetBrightness(percent) {
        this._proxy?.SetBrightnessRemote(percent);
    }

    disable() {
        if (this._focusId)
            global.display.disconnect(this._focusId);
        this._focusId = 0;
        if (this._windowCreatedId)
            global.display.disconnect(this._windowCreatedId);
        this._windowCreatedId = 0;
        if (this._grabEndId)
            global.display.disconnect(this._grabEndId);
        this._grabEndId = 0;
        if (this._virtualSyncTimeout) {
            GLib.source_remove(this._virtualSyncTimeout);
            this._virtualSyncTimeout = 0;
        }
        for (const win of [...(this._tracked?.keys() ?? [])])
            this._untrackWindow(win);
        if (this._focusTimeout) {
            GLib.source_remove(this._focusTimeout);
            this._focusTimeout = 0;
        }
        if (this._watchId)
            Gio.bus_unwatch_name(this._watchId);
        this._watchId = 0;
        this._disconnectProxy();
        this._indicator?.quickSettingsItems.forEach(i => i.destroy());
        this._indicator?.destroy();
        this._indicator = null;
    }
}
