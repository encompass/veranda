// Veranda GNOME Shell extension — a native Quick Settings entry + top-bar
// indicator that drives the running Veranda app over D-Bus.

import GObject from 'gi://GObject';
import Gio from 'gi://Gio';
import GioUnix from 'gi://GioUnix';
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
    }

    _connect() {
        try {
            this._proxy = ControlProxy(Gio.DBus.session, BUS_NAME, OBJ_PATH);
            this._signalId = this._proxy.connectSignal('StateChanged', () => this._refresh());
            this._refresh();
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
        if (this._watchId)
            Gio.bus_unwatch_name(this._watchId);
        this._watchId = 0;
        this._disconnectProxy();
        this._indicator?.quickSettingsItems.forEach(i => i.destroy());
        this._indicator?.destroy();
        this._indicator = null;
    }
}
