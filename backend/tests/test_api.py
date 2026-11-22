"""End-to-end API flows over HTTP (FastAPI TestClient)."""
from __future__ import annotations

import time

from .conftest import set_condition


def test_health_games_catalog_state(client):
    assert client.get("/api/health").json()["ok"]
    games = {g["game"]: g for g in client.get("/api/games").json()}
    assert set(games) == {"valorant", "cs2"}
    cat = client.get("/api/games/cs2/catalog").json()
    assert cat["menu"][0]["label"] == "Video" and len(cat["settings"]) == games["cs2"]["settingCount"]
    state = client.get("/api/games/valorant/state").json()
    assert state["values"]["val.video.vsync"] == {"value": "on", "revision": 0}
    assert client.get("/api/games/nope/state").status_code == 404


def test_search_returns_canonical_locations(client):
    hits = client.get("/api/games/valorant/search", params={"q": "anti-aliasing"}).json()
    assert hits[0]["settingId"] == "val.video.anti_aliasing" and hits[0]["path"] == "Video > Graphics Quality > Anti-Aliasing"
    hits = client.get("/api/games/cs2/search", params={"q": "reflex"}).json()
    assert hits[0]["settingId"] == "cs2.video.nvidia_reflex"


def test_manual_change_history_undo_over_http(client):
    r = client.put("/api/games/valorant/settings/val.video.bloom", json={"value": "off", "expectedRevision": 0})
    assert r.status_code == 200
    batch = r.json()["batchId"]
    stale = client.put("/api/games/valorant/settings/val.video.bloom", json={"value": "on", "expectedRevision": 0})
    assert stale.status_code == 409 and stale.json()["details"]["problems"][0]["kind"] == "stale_revision"
    bad = client.put("/api/games/valorant/settings/val.video.bloom", json={"value": "glowy"})
    assert bad.status_code == 422
    hist = client.get("/api/games/valorant/history").json()
    assert hist[0]["events"][0]["label"] == "Bloom"
    assert client.post(f"/api/history/{batch}/undo", json={}).status_code == 200
    assert client.get("/api/games/valorant/state").json()["values"]["val.video.bloom"]["value"] == "on"


def test_cs2_explicit_apply_batch(client):
    r = client.post("/api/games/cs2/batch", json={"changes": [{"settingId": "cs2.video.vsync", "value": "Disabled"},
                                                              {"settingId": "cs2.video.msaa", "value": "2x MSAA"}],
                                                 "label": "Video: Apply Changes"})
    assert r.status_code == 200 and len(r.json()["events"]) == 2
    vals = client.get("/api/games/cs2/state").json()["values"]
    assert vals["cs2.video.vsync"]["value"] == "0" and vals["cs2.video.msaa"]["value"] == "2"
    assert vals["cs2.video.video_preset"]["value"] == "custom"


def test_adaptive_features_are_gated(client, services):
    set_condition(services, "baseline")
    assert client.get("/api/games/valorant/relevant-now").status_code == 409
    assert client.put("/api/games/valorant/locks/val.video.vsync", json={"on": True}).status_code == 409
    assert client.post("/api/chat", json={"game": "valorant", "message": "hello"}).status_code == 422
    set_condition(services, "adaptive")
    assert client.put("/api/games/valorant/locks/val.video.vsync", json={"on": True}).json()["locks"] == ["val.video.vsync"]
    assert client.put("/api/games/valorant/pins/val.video.bloom", json={"on": True}).json()["pins"] == ["val.video.bloom"]


def test_full_chat_proposal_apply_undo_flow_in_fallback_mode(client, services):
    set_condition(services, "adaptive", aiMode="fallback")
    run = client.post("/api/chat", json={"game": "valorant", "message": "I'm getting frame drops in VALORANT and want smoother competitive play. What should I change?"})
    assert run.status_code == 202
    run_id = run.json()["runId"]
    status = {}
    for _ in range(200):
        status = client.get(f"/api/chat/runs/{run_id}").json()
        if status["status"] != "running":
            break
        time.sleep(0.02)
    result = status["result"]
    assert result["provenance"]["source"] == "fallback"
    recs = result["recommendations"]
    assert recs
    before = client.get("/api/games/valorant/state").json()["values"]
    prop = client.post("/api/proposals", json={"game": "valorant", "source": "fallback", "runId": run_id, "title": "Smoother play",
                                               "items": [{"settingId": r["settingId"], "proposedValue": r["proposedValue"],
                                                          "why": r["whyForGoal"], "dimensions": [r["dimension"]]} for r in recs]}).json()
    assert client.get("/api/games/valorant/state").json()["values"] == before  # staged only
    applied = client.post(f"/api/proposals/{prop['id']}/apply", json={"itemIds": [i["id"] for i in prop["items"]], "idempotencyKey": "abc"})
    assert applied.status_code == 200
    batch = applied.json()["batch"]
    assert batch["source"] == "fallback_applied"
    after = client.get("/api/games/valorant/state").json()["values"]
    assert all(after[r["settingId"]]["value"] == r["proposedValue"] for r in recs)
    assert client.post(f"/api/history/{batch['batchId']}/undo", json={}).status_code == 200
    restored = client.get("/api/games/valorant/state").json()["values"]
    assert all(restored[r["settingId"]]["value"] == before[r["settingId"]]["value"] for r in recs)
    thread = client.get("/api/games/valorant/chat").json()
    assert [m["role"] for m in thread] == ["user", "assistant"]
    traces = client.get("/api/traces").json()
    assert traces[0]["runId"] == run_id and traces[0]["status"] == "fallback" and len(traces[0]["goalExcerpt"]) <= 120


def test_context_event_and_preference_correction(client, services):
    set_condition(services, "adaptive")
    rn = client.post("/api/context-events", json={"game": "valorant", "eventType": "frame_drops"}).json()
    assert rn["trigger"] == "context_event" and rn["context"]["simulated"] and rn["items"]
    pref = client.post("/api/profile/preferences", json={"dimension": "visibility", "scope": "durable", "source": "chat_confirmed",
                                                          "game": "valorant", "note": "I care more about visibility than visual effects"})
    assert pref.status_code == 200
    prof = client.get("/api/profile").json()
    vis = [p for p in prof["preferences"] if p["dimension"] == "visibility"]
    assert vis and vis[0]["scope"] == "durable" and vis[0]["evidence"]
    assert client.post("/api/profile/preferences", json={"dimension": "visibility", "source": "ai_inferred"}).status_code == 422
    client.delete(f"/api/profile/preferences/{vis[0]['id']}")
    assert not [p for p in client.get("/api/profile").json()["preferences"] if p["dimension"] == "visibility"]


def test_reset_creates_backup_and_export_import_roundtrip(client, services, tmp_path):
    client.put("/api/games/valorant/settings/val.video.bloom", json={"value": "off"})
    exported = client.get("/api/admin/export").json()
    r = client.post("/api/admin/reset", json={"scenario": "default", "mode": "full"}).json()
    assert r["backup"] and services.settings.backup_dir.joinpath(r["backup"].split("\\")[-1].split("/")[-1]).exists()
    assert client.get("/api/games/valorant/state").json()["values"]["val.video.bloom"]["value"] == "on"
    assert client.post("/api/admin/import", json=exported).status_code == 200
    assert client.get("/api/games/valorant/state").json()["values"]["val.video.bloom"]["value"] == "off"
    soft = client.post("/api/admin/reset", json={"scenario": "default", "mode": "ai_only"}).json()
    assert soft["mode"] == "ai_only"
    assert client.get("/api/games/valorant/state").json()["values"]["val.video.bloom"]["value"] == "off"  # values kept
    assert client.post("/api/admin/reset", json={"scenario": "../etc/passwd"}).status_code == 404
