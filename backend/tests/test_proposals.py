"""Proposal lifecycle and the no-unauthorised-change invariant."""
from __future__ import annotations

import threading

import pytest

from app.domain.errors import Conflict, Invalid
from app.domain.store import Change

from .conftest import set_condition, value_of


def snapshot(services, game):
    conn = services.store.connect()
    try:
        return services.store.flat_values(conn, game)
    finally:
        conn.close()


def stage(services, items, game="valorant", source="ai"):
    return services.proposals.create(game, source=source, run_id=None, title="Test", items=items)


def test_staging_never_changes_values(services):
    before = snapshot(services, "valorant")
    p = stage(services, [{"settingId": "val.video.vsync", "proposedValue": "Off", "dimensions": ["input_latency"]},
                         {"settingId": "val.video.bloom", "proposedValue": "off"}])
    assert p["status"] == "pending"
    assert [i["status"] for i in p["items"]] == ["pending", "pending"]
    assert p["items"][0]["baselineValue"] == "on" and p["items"][0]["baselineRevision"] == 0
    assert snapshot(services, "valorant") == before  # invariant: suggestion/staging writes nothing


def test_apply_selected_items_only_and_records_history(services):
    p = stage(services, [{"settingId": "val.video.vsync", "proposedValue": "Off"},
                         {"settingId": "val.video.bloom", "proposedValue": "Off"}])
    res = services.proposals.apply(p["id"], [p["items"][0]["id"]], "key-1")
    assert res["batch"]["source"] == "ai_applied" and res["batch"]["proposalId"] == p["id"]
    assert value_of(services, "valorant", "val.video.vsync")["value"] == "off"
    assert value_of(services, "valorant", "val.video.bloom")["value"] == "on"  # unselected item untouched
    assert res["proposal"]["status"] == "pending"  # one item still pending
    hist = services.store.history("valorant")
    assert hist[0]["sourceLabel"] == "AI proposed · user applied"


def test_bundle_with_locked_item_applies_nothing(services):
    p = stage(services, [{"settingId": "val.video.vsync", "proposedValue": "off"},
                         {"settingId": "val.video.bloom", "proposedValue": "off"}])
    services.store.set_flag("locks", "valorant", "val.video.bloom", True)  # user locks after staging
    with pytest.raises(Conflict) as exc:
        services.proposals.apply(p["id"], [i["id"] for i in p["items"]], None)
    assert "locked" in exc.value.message
    assert value_of(services, "valorant", "val.video.vsync")["value"] == "on"  # all-or-nothing
    view = services.proposals.get(p["id"])
    assert view["items"][1]["statusReason"] and view["items"][1]["status"] == "pending"


def test_stale_baseline_conflict_then_rebase(services):
    p = stage(services, [{"settingId": "val.video.material_quality", "proposedValue": "Med"}])
    services.store.manual_change("valorant", [Change("val.video.material_quality", "low")])
    with pytest.raises(Conflict):
        services.proposals.apply(p["id"], [p["items"][0]["id"]], None)
    assert value_of(services, "valorant", "val.video.material_quality")["value"] == "low"
    services.proposals.rebase_item(p["id"], p["items"][0]["id"])
    services.proposals.apply(p["id"], [p["items"][0]["id"]], None)
    assert value_of(services, "valorant", "val.video.material_quality")["value"] == "med"


def test_idempotent_apply_and_double_apply(services):
    p = stage(services, [{"settingId": "cs2.video.vsync", "proposedValue": "Disabled"}], game="cs2")
    item = p["items"][0]["id"]
    a = services.proposals.apply(p["id"], [item], "same-key")
    b = services.proposals.apply(p["id"], [item], "same-key")
    assert b["idempotentReplay"] and b["batch"]["batchId"] == a["batch"]["batchId"]
    with pytest.raises(Conflict):
        services.proposals.apply(p["id"], [item], "other-key")
    assert value_of(services, "cs2", "cs2.video.vsync") == {"value": "0", "revision": 1}


def test_simultaneous_apply_requests_apply_once(services):
    p = stage(services, [{"settingId": "cs2.video.boost_player_contrast", "proposedValue": "Enabled"}], game="cs2")
    item = p["items"][0]["id"]
    results: list[str] = []

    def go(key: str) -> None:
        try:
            services.proposals.apply(p["id"], [item], key)
            results.append("ok")
        except Conflict:
            results.append("conflict")

    threads = [threading.Thread(target=go, args=(f"k{i}",)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count("ok") == 1 and results.count("conflict") == 3
    assert value_of(services, "cs2", "cs2.video.boost_player_contrast") == {"value": "1", "revision": 1}


def test_reject_changes_nothing_and_records_evidence(services):
    before = snapshot(services, "valorant")
    p = stage(services, [{"settingId": "val.video.vsync", "proposedValue": "off", "dimensions": ["input_latency"]}])
    view = services.proposals.reject(p["id"], None, "I prefer no tearing")
    assert view["status"] == "rejected"
    assert snapshot(services, "valorant") == before
    conn = services.store.connect()
    try:
        ev = services.profile.evidence(conn)
    finally:
        conn.close()
    assert any(e["kind"] == "rejected" and e["dimension"] == "input_latency" for e in ev)


def test_edit_item_then_apply_edited_value(services):
    p = stage(services, [{"settingId": "cs2.video.fps_max", "proposedValue": "240"}], game="cs2")
    view = services.proposals.edit_item(p["id"], p["items"][0]["id"], 300.3)
    assert view["items"][0]["editedValue"] == 300
    services.proposals.apply(p["id"], [p["items"][0]["id"]], None)
    assert value_of(services, "cs2", "cs2.video.fps_max")["value"] == 300


def test_proposals_reject_unsafe_items(services):
    with pytest.raises(Invalid):  # personal aim setting is never proposable
        stage(services, [{"settingId": "cs2.kbmouse.mouse_sensitivity", "proposedValue": "2.5"}], game="cs2")
    with pytest.raises(Invalid):  # keybinds are never proposable
        stage(services, [{"settingId": "cs2.kbmouse.key_jump", "proposedValue": "CTRL"}], game="cs2")
    with pytest.raises(Invalid):  # cross-game id
        stage(services, [{"settingId": "val.video.vsync", "proposedValue": "off"}], game="cs2")
    with pytest.raises(Invalid):  # invalid option
        stage(services, [{"settingId": "val.video.vsync", "proposedValue": "sometimes"}])
    services.store.set_flag("locks", "valorant", "val.video.vsync", True)
    p = stage(services, [{"settingId": "val.video.vsync", "proposedValue": "off"}])
    assert p["status"] == "closed" and p["items"][0]["status"] == "blocked"


def test_proposal_api_requires_adaptive_condition(client, services):
    set_condition(services, "baseline")
    r = client.post("/api/proposals", json={"game": "valorant", "source": "ai", "items": [{"settingId": "val.video.bloom", "proposedValue": "off"}]})
    assert r.status_code == 409 and r.json()["error"] == "baseline_condition"
    set_condition(services, "adaptive")
    r = client.post("/api/proposals", json={"game": "valorant", "source": "ai", "items": [{"settingId": "val.video.bloom", "proposedValue": "off"}]})
    assert r.status_code == 200
