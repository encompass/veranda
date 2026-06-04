"""Command-line control of a running Veranda instance.

Built on ``GApplication``'s command-line forwarding: when Veranda is already
running (it normally lives in the background), a second ``veranda <options>``
invocation is routed over the session bus to the primary instance, which acts
on its live window and prints results back to the caller's terminal. Without a
running instance, control options report that and exit non-zero.

    veranda --status
    veranda --list-profiles
    veranda --switch-profile Gaming      # by name (case-insensitive) or index
    veranda --brightness 60
    veranda --toggle | --show | --hide | --quit
"""

from __future__ import annotations

from typing import Callable

from gi.repository import GLib

# (long name, short char code or 0, arg type, help, placeholder)
_OPTIONS = [
    ("list-profiles", ord("l"), GLib.OptionArg.NONE,
     "List profiles for the connected device", None),
    ("switch-profile", ord("p"), GLib.OptionArg.STRING,
     "Switch to a profile by name or index", "NAME"),
    ("brightness", ord("b"), GLib.OptionArg.INT,
     "Set deck brightness (0-100)", "PCT"),
    ("status", ord("s"), GLib.OptionArg.NONE,
     "Print the current device status", None),
    ("toggle", ord("t"), GLib.OptionArg.NONE,
     "Toggle the Veranda window", None),
    ("show", 0, GLib.OptionArg.NONE, "Show the Veranda window", None),
    ("hide", 0, GLib.OptionArg.NONE, "Hide the Veranda window", None),
    ("quit", ord("q"), GLib.OptionArg.NONE,
     "Quit the running Veranda instance", None),
]

CONTROL_OPTION_NAMES = frozenset(opt[0] for opt in _OPTIONS)


def register_options(app) -> None:
    """Declare the control options on the application (call before run())."""
    for long_name, short, arg, helptext, placeholder in _OPTIONS:
        app.add_main_option(
            long_name, short, GLib.OptionFlags.NONE, arg, helptext, placeholder
        )


def has_control_options(opts: GLib.VariantDict) -> bool:
    """True if the parsed options request acting on a running instance."""
    return any(opts.contains(name) for name in CONTROL_OPTION_NAMES)


def handle(
    window,
    opts: GLib.VariantDict,
    out: Callable[[str], None],
    err: Callable[[str], None],
) -> int:
    """Run the requested control options against ``window``.

    ``out``/``err`` write to the invoking terminal. Returns a process exit
    status (0 on success, 1 if something could not be satisfied).
    """
    status = 0

    if opts.contains("list-profiles"):
        names = window.profile_names()
        if names:
            out("\n".join(f"{i}: {n}" for i, n in enumerate(names)) + "\n")
        else:
            err("No Stream Deck connected.\n")
            status = 1

    if opts.contains("switch-profile"):
        target = opts.lookup_value(
            "switch-profile", GLib.VariantType.new("s")
        ).get_string()
        idx = _resolve_profile(window, target)
        if idx is None:
            err(f"No such profile: {target}\n")
            status = 1
        else:
            window.switch_profile(idx)
            out(f"Switched to profile {idx}: {window.profile_names()[idx]}\n")

    if opts.contains("brightness"):
        pct = opts.lookup_value("brightness", GLib.VariantType.new("i")).get_int32()
        pct = max(0, min(100, pct))
        window.set_brightness(pct)
        out(f"Brightness set to {pct}%\n")

    if opts.contains("status"):
        out(_status_text(window))

    if opts.contains("toggle"):
        window.toggle_window()

    if opts.contains("show"):
        window.present()

    if opts.contains("hide"):
        window.set_visible(False)

    if opts.contains("quit"):
        out("Quitting Veranda.\n")
        window.real_quit()

    return status


def _resolve_profile(window, target: str) -> int | None:
    names = window.profile_names()
    if not names:
        return None
    folded = target.strip().casefold()
    if folded in ("next", "previous", "prev"):
        state = window.current_state()
        active = int(state.active_profile) if state is not None else 0
        delta = 1 if folded == "next" else -1
        return (active + delta) % len(names)
    if target.isdigit():
        idx = int(target)
        return idx if 0 <= idx < len(names) else None
    for idx, name in enumerate(names):
        if name == target:
            return idx
    low = target.lower()
    for idx, name in enumerate(names):
        if name.lower() == low:
            return idx
    return None


def _status_text(window) -> str:
    state = window.current_state()
    if state is None:
        return "No Stream Deck connected.\n"
    active = state.profiles[state.active_profile].name if state.profiles else "-"
    lines = [
        f"Device:     {state.display_name}",
        f"Connected:  {'yes' if window.deck_info() is not None else 'no'}",
        f"Brightness: {state.brightness}%",
        f"Profile:    {state.active_profile}: {active}",
        f"Profiles:   {len(state.profiles)}",
    ]
    return "\n".join(lines) + "\n"
