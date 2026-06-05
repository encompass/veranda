"""Weather widget location selection (GNOME Weather integration)."""

from veranda import weatherpicker
from veranda.actions.special.connectivity import WeatherWidget
from veranda.models import ButtonConfig


def test_saved_locations_is_graceful():
    # Returns a list and never raises, even when GNOME Weather / its schema
    # is not installed (in which case the list is empty).
    result = weatherpicker.saved_locations()
    assert isinstance(result, list)
    for item in result:
        name, lat, lon = item
        assert isinstance(name, str)
        assert isinstance(lat, float) and isinstance(lon, float)


def test_picker_constructs():
    picked = []
    opened = []
    dlg = weatherpicker.WeatherLocationPicker(
        lambda *a: picked.append(a), lambda: opened.append(True)
    )
    assert dlg is not None
    # The dialog builds whether or not any saved locations exist.


def test_editor_row_present():
    rows = WeatherWidget().build_editor_rows(ButtonConfig(), lambda: None)
    assert len(rows) == 1
    assert rows[0].get_title() == "Location"
    assert rows[0].get_subtitle() == "None chosen"


def test_editor_row_shows_chosen_name():
    w = WeatherWidget({"name": "Reykjavík", "lat": 64.15, "lon": -21.95})
    rows = w.build_editor_rows(ButtonConfig(), lambda: None)
    assert rows[0].get_subtitle() == "Reykjavík"
    assert w.summary() == "Reykjavík"
    assert w._has_location() is True


def test_display_without_location():
    w = WeatherWidget()
    assert w._has_location() is False
    assert w.display_text() == "Set"
    assert w.summary() == "No location set"


def test_roundtrip():
    from veranda.actions.registry import action_from_dict

    w = WeatherWidget({"name": "Oslo", "lat": 59.91, "lon": 10.75})
    w2 = action_from_dict(w.to_dict())
    assert isinstance(w2, WeatherWidget)
    assert w2.params["name"] == "Oslo"
    assert w2._has_location() is True
