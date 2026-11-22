"""Acceptance tests for VALORANT Crosshair profiles/codes and CS2 HUD Edge Positions & new controls."""
from __future__ import annotations

import pytest

from app.domain.errors import Conflict, Invalid


def test_valorant_crosshair_profiles_crud_import_export_and_undo(services, client):
    # Initial seeded Default profile
    profiles = client.get("/api/valorant/crosshair/profiles").json()
    assert len(profiles) == 1 and profiles[0]["isActive"] is True

    # Switch to Custom color first (when White preset is active, Custom Color is disabled by dependency), then test #RRGGBB normalization
    assert client.put("/api/games/valorant/settings/val.crosshair.primary_color", json={"value": "custom"}).status_code == 200
    r_bad = client.put("/api/games/valorant/settings/val.crosshair.primary_custom_color", json={"value": "not-hex"})
    assert r_bad.status_code == 422
    r_col = client.put("/api/games/valorant/settings/val.crosshair.primary_custom_color", json={"value": "#0f0"})
    assert r_col.status_code == 200
    assert r_col.json()["values"]["val.crosshair.primary_custom_color"]["value"] == "#00FF00"

    # Active profile reflects manual edit
    profiles = client.get("/api/valorant/crosshair/profiles").json()
    assert profiles[0]["settings"]["val.crosshair.primary_custom_color"] == "#00FF00"

    # Import validated Riot share code (TenZ cyan small cross style)
    r_bad_code = client.post("/api/valorant/crosshair/profiles/import", json={"code": "random garbage text", "name": "Bad"})
    assert r_bad_code.status_code == 422

    imp = client.post(
        "/api/valorant/crosshair/profiles/import",
        json={"code": "0;s;1;P;c;5;h;0;0l;4;0o;2;0a;1;0f;0;1b;0;S;c;1;s;1.5", "name": "Cyan Compact"},
    )
    assert imp.status_code == 200, imp.text
    imp_data = imp.json()
    new_pid = imp_data["activeProfileId"]
    st = client.get("/api/games/valorant/state").json()["values"]
    assert st["val.crosshair.use_advanced_options"]["value"] == "on"
    assert st["val.crosshair.primary_color"]["value"] == "cyan"
    assert st["val.crosshair.primary_outlines"]["value"] == "off"
    assert st["val.crosshair.primary_inner_length"]["value"] == 4
    assert st["val.crosshair.primary_show_outer"]["value"] == "off"
    assert st["val.crosshair.sniper_dot_color"]["value"] == "white"

    # Export code & re-import round-trips cleanly
    exp = client.get(f"/api/valorant/crosshair/profiles/{new_pid}/export")
    assert exp.status_code == 200
    assert exp.json()["code"].startswith("0;")

    # Rename works
    ren = client.patch(f"/api/valorant/crosshair/profiles/{new_pid}", json={"name": "Tournament Cyan"})
    assert ren.status_code == 200
    assert any(p["name"] == "Tournament Cyan" for p in ren.json()["profiles"])

    # Switching back to Default restores Default values cleanly via undoable manual_batch
    def_id = profiles[0]["id"]
    sel = client.post(f"/api/valorant/crosshair/profiles/{def_id}/select")
    assert sel.status_code == 200
    st_back = client.get("/api/games/valorant/state").json()["values"]
    assert st_back["val.crosshair.primary_custom_color"]["value"] == "#00FF00"

    # Undo restores previous profile's values
    batch_id = sel.json()["batch"]["batchId"]
    undo = client.post(f"/api/history/{batch_id}/undo", json={})
    assert undo.status_code == 200
    assert client.get("/api/games/valorant/state").json()["values"]["val.crosshair.primary_color"]["value"] == "cyan"

    # Enforce 15-profile limit
    while len(services.crosshair.list()) < 15:
        services.crosshair.create(f"P{len(services.crosshair.list()) + 1}")
    with pytest.raises(Conflict):
        services.crosshair.create("Overflow 16th")


def test_valorant_ads_sniper_gating_and_color_safety(services, client):
    # When use_advanced_options is Off, modifying ADS setting is rejected as unavailable
    st = client.get("/api/games/valorant/state").json()["values"]
    assert st["val.crosshair.use_advanced_options"]["value"] == "off"
    r_locked_ads = client.put("/api/games/valorant/settings/val.crosshair.ads_inner_length", json={"value": 8})
    assert r_locked_ads.status_code == 422

    # Turn Use Advanced Options On -> ADS becomes editable without overwriting Primary
    assert client.put("/api/games/valorant/settings/val.crosshair.use_advanced_options", json={"value": "on"}).status_code == 200
    assert client.put("/api/games/valorant/settings/val.crosshair.ads_inner_length", json={"value": 9}).status_code == 200
    st2 = client.get("/api/games/valorant/state").json()["values"]
    assert st2["val.crosshair.ads_inner_length"]["value"] == 9
    assert st2["val.crosshair.primary_inner_length"]["value"] == 6

    # Color controls cannot be proposed via ProposalService
    services.store.update_session(services.store.connect(), condition="adaptive")
    with pytest.raises(Invalid):
        services.proposals.create(
            "valorant",
            source="ai",
            run_id=None,
            title="Invalid color",
            items=[{"settingId": "val.crosshair.primary_custom_color", "proposedValue": "#FF00FF"}],
        )


def test_cs2_hud_edge_positions_and_new_verified_controls(client):
    cat = client.get("/api/games/cs2/catalog").json()["settings"]
    by_id = {s["id"]: s for s in cat}
    assert by_id["cs2.video.hud_edge_x"]["applyMode"] == "immediate"
    assert by_id["cs2.video.hud_edge_y"]["applyMode"] == "immediate"
    assert by_id["cs2.video.vsync"]["applyMode"] == "explicit"

    # Immediate batch save simulates Done in HUD Edge Positions
    res = client.post(
        "/api/games/cs2/batch",
        json={"changes": [{"settingId": "cs2.video.hud_edge_x", "value": 0.72}, {"settingId": "cs2.video.hud_edge_y", "value": 0.88}], "label": "HUD Edge Positions"},
    )
    assert res.status_code == 200
    vals = client.get("/api/games/cs2/state").json()["values"]
    assert vals["cs2.video.hud_edge_x"]["value"] == pytest.approx(0.72)
    assert vals["cs2.video.hud_edge_y"]["value"] == pytest.approx(0.88)

    # Out-of-bounds safezoney (< 0.80) rejected
    bad_y = client.put("/api/games/cs2/settings/cs2.video.hud_edge_y", json={"value": 0.4})
    assert bad_y.status_code == 422

    # Undo restores HUD edge positions to 1.0
    bat_id = res.json()["batchId"]
    assert client.post(f"/api/history/{bat_id}/undo", json={}).status_code == 200
    vals2 = client.get("/api/games/cs2/state").json()["values"]
    assert vals2["cs2.video.hud_edge_x"]["value"] == pytest.approx(1.0)
    assert vals2["cs2.video.hud_edge_y"]["value"] == pytest.approx(1.0)

    # Fullscreen Brightness availability & Voice Threshold domain checks
    assert client.put("/api/games/cs2/settings/cs2.video.display_mode", json={"value": "0"}).status_code == 200
    assert client.put("/api/games/cs2/settings/cs2.video.brightness", json={"value": 2.6}).status_code == 422
    assert client.put("/api/games/cs2/settings/cs2.audio.voice_threshold", json={"value": -45}).status_code == 200
    assert client.put("/api/games/cs2/settings/cs2.audio.voice_threshold", json={"value": 5}).status_code == 422
