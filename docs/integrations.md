# GNOME App Integrations — Roadmap

Tracking deeper integrations between Veranda and the GNOME apps, beyond plain
"Open App". These land in a **new action category, "App Control"** (it appears
in the action library once the first action below is implemented).

Legend: `[ ]` todo · `[~]` in progress · `[x]` done

## New action category: "App Control"

Cross-app actions that *do something* with an app, not just launch it.

- [x] **Media Control** — play/pause · play · pause · next · previous · stop,
      targeting the active MPRIS player (prefers one that is Playing). One key
      per command; the tile icon tracks the command. Pairs with the **Now
      Playing** Special Button. Works with `gnome-music`, `gnome-podcasts`,
      `shortwave`, `totem`, `showtime` (any MPRIS player).
- [ ] **Open Settings Panel** — open `gnome-control-center` to a specific panel
      (wifi · bluetooth · power · sound · display · network · keyboard · …) with
      a dropdown in the editor. (`gnome-control-center <panel>`.)
- [ ] **Player picker** — when more than one MPRIS player is active, let a Media
      Control key target a specific app rather than "whatever is active".

## Per-app integrations

| App | Desktop ID | Integration idea | Status |
| --- | --- | --- | --- |
| Music | `org.gnome.Music` | MPRIS transport + Now Playing | [ ] |
| Podcasts | `org.gnome.Podcasts` | MPRIS transport + Now Playing | [ ] |
| Shortwave | `de.haeckerfelix.Shortwave` | MPRIS play/pause; maybe station presets | [ ] |
| Videos (Showtime) | `org.gnome.Showtime` | MPRIS transport | [ ] |
| Videos (Totem) | `org.gnome.Totem` | MPRIS transport | [ ] |
| Clocks | `org.gnome.clocks` | start/stop a timer or stopwatch | [ ] |
| Settings | `org.gnome.Settings` | Open Settings Panel action | [ ] |
| Builder | `org.gnome.Builder` | focus → "Coding" profile (auto-switch preset) | [ ] |
| Apostrophe | `org.gnome.gitlab.somas.Apostrophe` | focus → "Writing" profile | [ ] |
| Text Editor | `org.gnome.TextEditor` | focus → an editing profile | [ ] |
| Boxes | `org.gnome.Boxes` | focus → a "VM" profile | [ ] |
| Document Scanner | `simple-scan` | quick-scan key (CLI/D-Bus) | [ ] |
| Warp | `app.drey.Warp` | send-file key | [ ] |
| Dialect | `app.drey.Dialect` | translate-clipboard key | [ ] |
| System Monitor | `org.gnome.SystemMonitor` | already openable; pair with sysmon widget | [ ] |
| Disk Usage (Baobab) | `org.gnome.baobab` | quick-launch | [ ] |

## Supporting work

- [ ] Helper to enumerate active MPRIS players (`org.mpris.MediaPlayer2.*`) and
      send transport commands — reuse/extend what the Now Playing widget does.
- [ ] A small "preset profiles" helper so auto-switch mappings (Builder→Coding,
      Apostrophe→Writing) can be created in one click.
- [ ] Verify each desktop ID against `Gio.AppInfo` on the target system (IDs
      differ between apt and Flatpak builds, e.g. `org.gnome.Totem` vs the snap).

## Notes

- Veranda already covers a lot via existing actions: **Open App** (any of these),
  **Now Playing** (any MPRIS player), **Run Command** (`gnome-control-center
  <panel>`, `gnome-clocks`, …), **GNOME Shortcut**, and **auto-switch profiles**
  (Settings → Automation). The work above is about making the common cases
  first-class, discoverable actions instead of manual configuration.
- Suggested first build: **Media Control**, then **Open Settings Panel** — both
  are high-value, reuse existing plumbing, and immediately exercise the installed
  apps.
