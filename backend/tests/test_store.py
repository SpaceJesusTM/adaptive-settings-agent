"""Value rules, manual changes, revisions, history/undo, presets, persistence, game separation, concurrency."""
from __future__ import annotations

import threading

import pytest

from app.domain.errors import Conflict, Invalid
from app.domain.store import Change, Store
from app.domain.values import ValueError_, availability_problem, normalize_value

from .conftest import set_condition, value_of


def test_normalize_accepts_values_and_exact_labels(services):
    reg = services.registry
    reflex = reg.setting("cs2", "cs2.video.nvidia_reflex")
    assert normalize_value(reflex, "Enabled + Boost", strict=True) == "2"
    assert normalize_value(reflex, "2", strict=True) == "2"
    assert normalize_value(reflex, 2, strict=True) == "2"
    with pytest.raises(ValueError_):
        normalize_value(reflex, "Ultra", strict=True)
    fps = reg.setting("cs2", "cs2.video.fps_max")
    assert normalize_value(fps, "300", strict=True) == 300
    with pytest.raises(ValueError_):
        normalize_value(fps, 10, strict=True)  # below 64
    with pytest.raises(ValueError_):
        normalize_value(fps, 300.5, strict=True)  # off-grid in strict mode
    assert normalize_value(fps, 300.4, strict=False) == 300  # manual input snaps
    vol = reg.setting("cs2", "cs2.audio.master_volume")
    assert normalize_value(vol, "50%", strict=False) == 0.5
    key = reg.setting("cs2", "cs2.kbmouse.key_jump")
    assert normalize_value(key, "SPACE", strict=False) == "SPACE"
    with pytest.raises(ValueError_):
        normalize_value(key, "Space Bar", strict=False)  # VALORANT key name is not a CS2 key name


def test_availability_rules(services):
    reg = services.registry
    conn = services.store.connect()
    try:
        values = services.store.flat_values(conn, "valorant")
    finally:
        conn.close()
    fixed = reg.setting("valorant", "val.general.fixed_orientation")
    assert "Disabled until Rotate is set to Fixed" in availability_problem(reg, fixed, values, {"gpuVendor": "NVIDIA"})
    assert availability_problem(reg, fixed, {**values, "val.general.rotate": "fixed"}, {"gpuVendor": "NVIDIA"}) is None
    anti_lag = reg.setting("valorant", "val.video.amd_anti_lag_2")
    assert "AMD" in availability_problem(reg, anti_lag, values, {"gpuVendor": "NVIDIA"})
    assert availability_problem(reg, anti_lag, values, {"gpuVendor": "AMD"}) is None


def test_manual_change_persists_with_history_and_undo(services):
    store = services.store
    before = value_of(services, "valorant", "val.video.bloom")
    assert before["value"] == "on" and before["revision"] == 0
    res = store.manual_change("valorant", [Change("val.video.bloom", "Off", expected_revision=0)])
    assert res["source"] == "manual" and res["events"][0]["oldDisplay"] == "On" and res["events"][0]["newDisplay"] == "Off"
    assert value_of(services, "valorant", "val.video.bloom") == {"value": "off", "revision": 1}
    hist = store.history("valorant")
    assert hist[0]["batchId"] == res["batchId"] and hist[0]["undoable"]
    undo = store.undo_batch(res["batchId"])
    assert undo["source"] == "undo"
    assert value_of(services, "valorant", "val.video.bloom")["value"] == "on"
    with pytest.raises(Conflict):
        store.undo_batch(res["batchId"])  # already undone


def test_undo_refuses_to_overwrite_later_change(services):
    store = services.store
    first = store.manual_change("valorant", [Change("val.video.bloom", "off")])
    store.manual_change("valorant", [Change("val.video.bloom", "on")])
    with pytest.raises(Conflict) as exc:
        store.undo_batch(first["batchId"])
    assert "changed since" in exc.value.message


def test_stale_expected_revision_is_rejected(services):
    store = services.store
    store.manual_change("valorant", [Change("val.video.bloom", "off", expected_revision=0)])
    with pytest.raises(Conflict):
        store.manual_change("valorant", [Change("val.video.bloom", "on", expected_revision=0)])
    assert value_of(services, "valorant", "val.video.bloom")["value"] == "off"


def test_idempotent_manual_change(services):
    store = services.store
    a = store.manual_change("cs2", [Change("cs2.video.vsync", "0")], client_request_id="req-1")
    b = store.manual_change("cs2", [Change("cs2.video.vsync", "1")], client_request_id="req-1")
    assert b["idempotentReplay"] and b["batchId"] == a["batchId"]
    assert value_of(services, "cs2", "cs2.video.vsync") == {"value": "0", "revision": 1}
    assert len(store.history("cs2")) == 1


def test_invalid_values_and_dependencies_do_not_write(services):
    store = services.store
    with pytest.raises(Invalid):
        store.manual_change("valorant", [Change("val.video.material_quality", "Ultra")])
    with pytest.raises(Invalid):
        store.manual_change("valorant", [Change("val.general.fixed_orientation", "always_same")])  # parent is Rotate
    with pytest.raises(Invalid):
        store.manual_change("valorant", [Change("val.video.amd_anti_lag_2", "on")])  # NVIDIA simulated PC
    # a bundle where one item is invalid applies nothing
    with pytest.raises(Invalid):
        store.manual_change("valorant", [Change("val.video.bloom", "off"), Change("val.video.vsync", "maybe")])
    assert value_of(services, "valorant", "val.video.bloom")["value"] == "on"
    ok = store.manual_change("valorant", [Change("val.general.rotate", "fixed"), Change("val.general.fixed_orientation", "always_same")])
    assert len(ok["events"]) == 2


def test_game_separation_and_wrong_game_ids(services):
    store = services.store
    store.manual_change("valorant", [Change("val.video.bloom", "off")])
    conn = store.connect()
    try:
        assert store.game_revision(conn, "cs2") == 0
    finally:
        conn.close()
    with pytest.raises(Invalid) as exc:
        store.manual_change("cs2", [Change("val.video.bloom", "off")])
    assert exc.value.code == "wrong_game"


def test_preset_selection_expands_into_members_and_is_derived(services):
    store = services.store
    assert value_of(services, "cs2", "cs2.video.video_preset")["value"] == "2"  # samples == High preset
    res = store.manual_change("cs2", [Change("cs2.video.video_preset", "Low")])
    assert res["source"] == "preset" and len(res["events"]) == 11
    assert value_of(services, "cs2", "cs2.video.video_preset")["value"] == "0"
    store.manual_change("cs2", [Change("cs2.video.shader_detail", "1")])
    assert value_of(services, "cs2", "cs2.video.video_preset")["value"] == "custom"
    with pytest.raises(Invalid):
        store.manual_change("cs2", [Change("cs2.video.video_preset", "custom")])


def test_state_survives_restart(services, settings):
    services.store.manual_change("cs2", [Change("cs2.audio.eq_profile", "Crisp")])
    reopened = Store(settings.db_path, services.registry)
    conn = reopened.connect()
    try:
        assert reopened.values(conn, "cs2")["cs2.audio.eq_profile"]["value"] == "1"
        assert len(reopened.history("cs2")) == 1
    finally:
        conn.close()


def test_condition_switch_does_not_change_values(services):
    conn = services.store.connect()
    try:
        before = services.store.flat_values(conn, "valorant")
    finally:
        conn.close()
    set_condition(services, "adaptive")
    set_condition(services, "baseline")
    conn = services.store.connect()
    try:
        assert services.store.flat_values(conn, "valorant") == before
    finally:
        conn.close()


def test_concurrent_writers_are_serialised(services):
    store = services.store
    errors: list[Exception] = []
    targets = ["val.video.bloom", "val.video.distortion", "val.video.vignette", "val.video.cast_shadows",
               "val.video.improve_clarity", "val.general.show_bullet_tracers"]

    def worker(sid: str) -> None:
        try:
            store.manual_change("valorant", [Change(sid, "off")])
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(t,)) for t in targets]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    conn = store.connect()
    try:
        assert store.game_revision(conn, "valorant") == len(targets)
        assert all(store.values(conn, "valorant")[t]["value"] == "off" for t in targets)
    finally:
        conn.close()
