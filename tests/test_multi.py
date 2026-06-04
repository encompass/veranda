"""Multi-Action sequencing."""

from gi.repository import GLib

from veranda.actions.multi import MultiAction, DelayAction
from veranda.actions.registry import action_from_dict, get_action_class
from veranda.actions.run_command import RunCommandAction
from veranda.actions.extras import CopyTextAction


def test_delay_registered_but_not_in_palette():
    from veranda.actions.registry import ACTION_CATALOG
    assert get_action_class("delay") is DelayAction
    assert DelayAction not in ACTION_CATALOG
    assert action_from_dict({"type": "delay", "ms": 500}).ms == 500


def test_multi_roundtrip():
    m = MultiAction({"steps": [
        CopyTextAction({"text": "x"}).to_dict(),
        RunCommandAction({"command": "true"}).to_dict(),
    ]})
    m2 = action_from_dict(m.to_dict())
    assert m2.TYPE_ID == "multi" and len(m2.params["steps"]) == 2
    assert m2.summary() == "2 steps"
    assert MultiAction().summary() == "No steps yet"


def test_multi_runs_steps_in_order(fake_ctx, tmp_path):
    marker = tmp_path / "m"
    m = MultiAction({"steps": [
        CopyTextAction({"text": "x"}).to_dict(),
        RunCommandAction({"command": f"touch {marker}"}).to_dict(),
    ]})
    m.execute(fake_ctx)
    import time
    time.sleep(0.3)
    assert marker.exists()  # run_command step executed
    assert any("clip" in n.lower() or "copied" in n.lower() for n in fake_ctx.notes)


def test_multi_delay_defers_next(fake_ctx, tmp_path):
    marker = tmp_path / "d"
    m = MultiAction({"steps": [
        DelayAction({"ms": 80}).to_dict(),
        RunCommandAction({"command": f"touch {marker}"}).to_dict(),
    ]})
    m.execute(fake_ctx)
    assert not marker.exists()  # deferred behind the delay
    loop = GLib.MainLoop()
    GLib.timeout_add(300, loop.quit)
    loop.run()
    import time
    time.sleep(0.2)
    assert marker.exists()  # ran after the delay
