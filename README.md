# Veranda

A modern **GTK4 / libadwaita** application for managing Elgato Stream Deck
devices on Linux, built to feel native to GNOME.

The interface is a two-pane editor: the physical buttons are shown on the left
as a grid that matches your device, and an action library is on the right. Drag
an action onto a button to bind it. Press the physical key to run the action.

> Veranda is a from-scratch alternative to `streamdeck-linux-gui`, with a
> libadwaita UI, XDG-compliant config, and **Wayland-compatible** key/text
> injection (via `uinput`) instead of the X11-only path.

## Features

- Native GTK4 + libadwaita two-pane editor with drag-and-drop binding.
- Live preview: on-screen tiles render the exact image shown on the key.
- Button images: pick from a searchable themed **icon library**, or upload
  any **image or SVG**. Symbolic icons render to the device in white.
- Multiple pages per deck, with add/remove and a "Switch Page" action.
- **Special Buttons**: live, self-updating keys that show info and refresh on a
  timer or D-Bus events — Clock, Date (day number → GNOME Calendar), Now Playing
  (MPRIS, press toggles), App Unread (count badge via the dock-badge API),
  Battery, System Monitor (CPU/RAM/disk), Volume (press mutes), Do Not Disturb,
  Network, Weather, and Software Updates. Values render smart-per-type (big
  number, corner badge, or icon+label).
- **Profiles**: multiple independent button sets per deck, switchable from a
  header dropdown and managed in a Settings window (add/rename/duplicate/delete).
- **Lock sync**: optionally blank a deck (brightness 0) when the GNOME session
  locks, and restore it on unlock — a per-device Settings toggle.
- **Auto-switch profiles by focused app**: via the GNOME Shell extension, the
  active profile follows the foreground app (configure in Settings → Automation).
- **Drop an image from Files** onto a key to set its icon; **per-key colors**
  follow the GNOME theme or accent color.
- **Keyboard shortcuts** (Ctrl+Q/Ctrl+,/Ctrl+?/Ctrl+Page Up·Down) with a
  Shortcuts window; remembers window size; ships an app icon + AppStream
  metainfo so it installs cleanly via GNOME Software.
- **Run in the background**: keep Veranda running when the window is closed,
  with an option to **start hidden**. It appears in GNOME's top-right via a
  StatusNotifierItem tray icon and the Background Apps menu (see below).
- **Import / export** profiles as shareable JSON files (menu or Settings).
- Action types:
  - **Run Command** — execute a shell command.
  - **Open URL / File** — open a link or path with `xdg-open`.
  - **Hotkey** — send a key combo (e.g. `ctrl+shift+t`), Wayland-safe.
  - **Type Text** — type a literal string, Wayland-safe.
  - **Switch Page** / **Brightness** — control the deck itself (brightness
    changes persist per device and stay in sync with Settings).
  - **GNOME Shortcut** — pick any GNOME keyboard shortcut (imported live from
    your system settings, grouped like the GNOME dialog). Built-in shortcuts
    replay their key combo; custom shortcuts run their command.
- Hotplug aware: connect or disconnect a deck and the UI follows.
- Config stored at `~/.config/veranda/config.json` (atomic writes).

## Requirements

- Python 3.11+
- System GTK 4 + libadwaita + PyGObject (the `gi` bindings)
- `libhidapi-libusb0` (HID backend for the device)

On Ubuntu/Debian:

```bash
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 libhidapi-libusb0
```

Python packages (`streamdeck`, `pillow`, `evdev`) install via pip below.

## Install & run (development)

Use a venv that can still see the system `gi` bindings:

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -e .
.venv/bin/veranda          # or: .venv/bin/python -m veranda
```

## Permissions

### Device access (udev)

Stream Deck HID devices aren't accessible to your user by default. Install the
bundled rule and replug the device:

```bash
sudo cp data/60-veranda-streamdeck.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
```

If Veranda can't open a connected device, it shows these steps in-app.

### Keyboard injection (uinput)

The **Hotkey** and **Type Text** actions write to `/dev/uinput`. Grant access by
adding yourself to the `input` group (or shipping a udev rule for `uinput`):

```bash
sudo usermod -aG input "$USER"   # then log out and back in
```

The other action types (command, URL, deck control) work without this.

## Running in the background (top-bar icon)

Enable **Settings → General → Run in the background** to keep Veranda alive
when you close the window, with optional **Start hidden** and **Open at login**
(an XDG autostart entry). Quit fully from the tray menu or **☰ → Quit**.

If background mode is on but no tray host is running, Veranda shows a one-time
notice (with a one-click option to enable the AppIndicator extension) so it
never silently disappears.

Two top-right surfaces are used:

- **Background Apps** (no setup): GNOME lists Veranda under the system menu's
  *Background Apps* section, with a Quit action. Reopen by clicking its app icon.
- **Dedicated tray icon** (StatusNotifierItem): a standalone icon with a
  Show/Quit menu. GNOME only renders these when an *AppIndicator host* is
  running — enable the **AppIndicator and KStatusNotifier Support** (Ubuntu:
  *Ubuntu AppIndicators*) GNOME extension, then the icon appears automatically.
  Without it, use the Background Apps entry above.

## GNOME Shell extension (Quick Settings)

For a truly native presence — a **Quick Settings** entry (like Caffeine) and a
top-bar indicator — Veranda ships an optional GNOME Shell extension in
`extension/`. It talks to the running app over D-Bus
(`com.encompass.Veranda.Control`) to show/hide the window, switch profiles, set
a **brightness slider**, and quit. It also **launches the app on demand** if it
isn't running, and the **top-bar icon only appears while a Stream Deck is
connected**.

GNOME Shell's built-in system indicators (Wi-Fi, volume, battery) are core and
can't be extended by an app — a Shell extension is the only supported way to add
a native-looking entry there.

Install:

```bash
./extension/install.sh
# then log out and back in (Wayland registers newly-added extensions on login)
gnome-extensions enable veranda@encompass.gmail.com
```

The extension's top-bar icon appears only while the Veranda app is running, so
pair it with "Run in the background" / "Open at login".

## Configuration

State lives in `~/.config/veranda/config.json`, keyed by each deck's serial
number, so multiple decks and pages are remembered independently.

## Status

Early MVP. Supported and tested on the Stream Deck Mini; geometry is read from
the device at runtime, so other models (Original, MK.2, XL, Plus, Neo) should
work. Hardware rendering currently composites a text label and optional image
file per key; rendering symbolic action icons to the hardware is planned.

## License

GPL-3.0-or-later.
