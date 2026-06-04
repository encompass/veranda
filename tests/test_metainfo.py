"""AppStream metainfo: install location and well-formedness."""

import xml.etree.ElementTree as ET

from veranda import APP_ID, autostart


def test_metainfo_installs_under_xdg_data(isolate_config):
    autostart.ensure_metainfo()
    path = autostart.metainfo_file()
    assert path.exists()
    assert path.name == f"{APP_ID}.metainfo.xml"
    assert path.parent.name == "metainfo"


def test_metainfo_is_well_formed_and_identifies_app(isolate_config):
    autostart.ensure_metainfo()
    root = ET.fromstring(autostart.metainfo_file().read_text())
    assert root.tag == "component"
    assert root.get("type") == "desktop-application"
    assert root.findtext("id") == APP_ID
    assert root.findtext("project_license") == "GPL-3.0-or-later"
    launchable = root.find("launchable")
    assert launchable is not None
    assert launchable.text == f"{APP_ID}.desktop"


def test_metainfo_install_is_idempotent(isolate_config):
    autostart.ensure_metainfo()
    first = autostart.metainfo_file().read_bytes()
    autostart.ensure_metainfo()  # second run must not change anything
    assert autostart.metainfo_file().read_bytes() == first
