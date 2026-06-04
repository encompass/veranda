"""Input-backend key resolution and editor validators."""

from veranda.input_backend import combo_is_valid, _resolve_key
from veranda.actions import validation
from veranda import gnome_shortcuts as gs


def test_combo_is_valid():
    assert combo_is_valid("ctrl+shift+t")[0] is True
    assert combo_is_valid("super+l")[0] is True
    assert combo_is_valid("ctrl+nope")[0] is False
    assert combo_is_valid("ctrl")[0] is False  # modifier only
    assert combo_is_valid("")[0] is None


def test_resolve_key():
    assert _resolve_key("a") is not None
    assert _resolve_key("space") is not None
    assert _resolve_key("nope-xyz") is None


def test_command_status():
    assert validation.command_status("true")[0] is True
    assert validation.command_status("ls -la")[0] is True
    assert validation.command_status("nope-xyz-123")[0] is False
    assert validation.command_status("")[0] is None


def test_path_and_folder_status(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    assert validation.path_status("https://gnome.org")[0] is True
    assert validation.path_status(str(f))[0] is True
    assert validation.path_status("/no/such/file")[0] is False
    assert validation.folder_status(str(tmp_path))[0] is True
    assert validation.folder_status(str(f))[0] is False  # not a folder


def test_gnome_shortcut_catalog_resolves():
    cat = gs.catalog()
    assert len(cat) > 10
    from veranda.input_backend import InputBackend

    b = InputBackend()
    for sc in cat:
        if sc.kind != "builtin":
            continue
        _mods, key = b._parse_accel(sc.accel)
        assert b._accel_keycode(key) is not None, sc.accel


def test_friendly_accel():
    assert gs.friendly_accel("<Super>space") == "Super+Space"
    assert gs.friendly_accel("XF86AudioMute")  # non-empty
