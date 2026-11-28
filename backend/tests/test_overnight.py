from app.agent.schemas import AssistantDraft
from app.agent.validate import validate_draft
from app.domain.db import write_tx

from .conftest import set_condition


def test_new_protection_blocks_apply_atomically_and_allows_manual_edit(services, client):
    set_condition(services)
    p = client.post("/api/proposals", json={"source": "ai", "game": "valorant", "items": [
        {"settingId": "val.video.vsync", "proposedValue": "off"},
        {"settingId": "val.video.bloom", "proposedValue": "off"},
    ]}).json()
    conn = services.store.connect()
    try:
        with write_tx(conn):
            services.profile.set_session_goal(conn, "valorant", "Keep VSync", ["performance"], "chat", {"val.video.vsync"})
    finally:
        conn.close()
    ids = [item["id"] for item in p["items"]]
    path = f"/api/proposals/{p['id']}"
    assert client.get(path).json()["items"][0]["protectedReason"]
    response = client.post(f"{path}/apply", json={"itemIds": ids})
    assert response.status_code == 409
    assert response.json()["error"] == "protected_by_objective"
    values = client.get("/api/games/valorant/state").json()["values"]
    assert values["val.video.vsync"]["value"] == values["val.video.bloom"]["value"] == "on"
    assert client.post(f"{path}/apply", json={"itemIds": ids[1:]}).status_code == 200
    assert client.put("/api/games/valorant/settings/val.video.vsync", json={"value": "off"}).status_code == 200


def test_prose_only_explanation_resolves_canonical_setting_and_filters_unverified_history(services):
    r = validate_draft(
        services.store, "cs2",
        AssistantDraft(intent="explain", reply="You previously adjusted Ambient Occlusion. The effect adds contact shading."),
        source="ai", message="Could you explain Ambient Occlusion?",
    )
    assert r["navigateTo"]["settingId"] == "cs2.video.ambient_occlusion"
    assert r["explanations"][0]["settingId"] == "cs2.video.ambient_occlusion"
    assert r["reply"] == "The effect adds contact shading."
    assert not r["recommendations"]
