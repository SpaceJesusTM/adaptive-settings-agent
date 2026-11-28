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


def test_later_batch_timeout_preserves_first_validated_batch(services, fake_model_holder, connected_ollama):
    import asyncio
    from dataclasses import replace

    from app.domain.scenarios import reset

    from .conftest import FakeChatModel
    from .test_comprehensive_setup import _run_turn

    class DelayedSecondBatch(FakeChatModel):
        def with_structured_output(self, schema, **kwargs):
            invoker = super().with_structured_output(schema, **kwargs)
            if schema.__name__ == "BatchDraft":
                async def wait_for_timeout(_messages):
                    await asyncio.sleep(10)
                invoker.ainvoke = wait_for_timeout
            return invoker

    reset(services.store, services.settings.scenario_dir, services.settings.backup_dir,
          "fresh_install_comprehensive", "full", backup=False)
    set_condition(services, "adaptive", aiMode="local")
    services.runner.settings = replace(services.settings, agent_deadline_s=1.0, agent_fast_path=True)
    fake_model_holder["model"] = DelayedSecondBatch(compose_payloads=[{
        "intent": "recommend",
        "reply": "Prepared two Video changes for review.",
        "recommendations": [
            {"setting_id": "cs2.video.vsync", "proposed_value": "Disabled", "why_for_goal": "Reduce latency.",
             "confidence": "high"},
            {"setting_id": "cs2.video.msaa", "proposed_value": "2x MSAA", "why_for_goal": "Reduce graphics work.",
             "confidence": "medium"},
        ],
    }])
    run = asyncio.run(_run_turn(services, "cs2", "I just installed CS2; configure everything for competitive FPS and clarity."))
    assert run["status"] == "succeeded"
    result = run["result"]
    assert "Partial review" in result["reply"]
    assert result["plan"]["partialCoverage"] and result["plan"]["batchesCompleted"] == 1
    assert result["stagedCount"] == 2
    assert [call["status"] for call in run["validation"]["modelCalls"]] == ["completed", "timeout"]


def test_manual_update_during_inference_excludes_only_stale_setting(services, client, fake_model_holder, connected_ollama):
    import asyncio

    from .conftest import FakeChatModel, value_of

    async def play():
        awaiting_model = asyncio.Event()
        edited = asyncio.Event()

        class WaitingModel(FakeChatModel):
            def with_structured_output(self, schema, **kwargs):
                invoker = super().with_structured_output(schema, **kwargs)
                original = invoker.ainvoke

                async def after_manual_edit(messages):
                    awaiting_model.set()
                    await edited.wait()
                    return await original(messages)

                invoker.ainvoke = after_manual_edit
                return invoker

        set_condition(services, "adaptive", aiMode="local")
        fake_model_holder["model"] = WaitingModel(compose_payloads=[{
            "intent": "recommend",
            "reply": "Consider the selected graphics changes.",
            "recommendations": [
                {"setting_id": sid, "proposed_value": "Off", "why_for_goal": "Reduce graphics work.",
                 "confidence": "high"} for sid in ("val.video.vsync", "val.video.bloom")
            ],
        }])
        before = value_of(services, "valorant", "val.video.vsync")
        run = await services.runner.start("valorant", "Help me get smoother FPS with lower input lag.", {})
        await asyncio.wait_for(awaiting_model.wait(), timeout=3)
        for value in ("off", "on"):
            assert client.put("/api/games/valorant/settings/val.video.vsync", json={"value": value}).status_code == 200
        edited.set()
        await asyncio.wait_for(services.runner._active[run["runId"]].task, timeout=3)
        result = services.runner.status(run["runId"])["result"]
        assert [r["settingId"] for r in result["recommendations"]] == ["val.video.bloom"]
        assert result["stagedCount"] == 1
        assert value_of(services, "valorant", "val.video.vsync")["value"] == before["value"]
        assert value_of(services, "valorant", "val.video.bloom")["value"] == "on"

    asyncio.run(play())
