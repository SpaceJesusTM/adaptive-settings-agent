from app.agent.schemas import AssistantDraft, DraftMemoryAction, DraftRecommendation
from app.agent.validate import validate_draft
from app.domain.db import write_tx
from app.domain.store import Change


def test_mixed_request_filters_model_valid_value_and_keeps_secondary_intentions(services):
    draft = AssistantDraft(
        intent="recommend",
        reply="I've turned V-Sync off. Ambient occlusion adds depth.",
        recommendations=[
            DraftRecommendation(
                setting_id="cs2.video.vsync", proposed_value="Disabled",
                confidence="high", why_for_goal="May reduce input delay.",
            ),
        ],
        explicit_memory_actions=[DraftMemoryAction(kind="preference", dimension="performance")],
    )
    result = validate_draft(
        services.store, "cs2", draft, source="ai",
        message="Make CS2 run smoother, but don't change V-Sync. Also explain what ambient occlusion does, "
        "and remember that I usually prioritize visibility.",
    )
    assert result["recommendations"] == []
    assert result["filtered"][0]["kind"] == "protected_by_request"
    assert "turned" not in result["reply"]
    assert result["goalDimensions"] == ["performance"]
    assert [e["settingId"] for e in result["explanations"]] == ["cs2.video.ambient_occlusion"]
    assert [a["dimension"] for a in result["explicitMemoryActions"]] == ["visibility"]


def test_durable_scopes_override_global_only_in_their_game(services):
    conn = services.store.connect()
    try:
        with write_tx(conn):
            for scope, direction in [(None, "prioritize"), ("cs2", "deprioritize")]:
                services.profile.add_preference_tx(
                    conn, dimension="input_latency", direction=direction, scope="durable",
                    source="chat_explicit", game=scope or "valorant", origin_game=scope,
                    note=None, applies_to_game=scope,
                )
        assert services.profile.dimension_weights(conn, "cs2")["input_latency"]["weight"] < 0
        assert services.profile.dimension_weights(conn, "valorant")["input_latency"]["weight"] > 0
        assert len(services.profile.preferences(conn)) == 2
    finally:
        conn.close()


def test_cross_game_onboarding_does_not_treat_undo_as_a_new_choice(services):
    store = services.store
    change = store.manual_change("valorant", [Change("val.general.sensitivity_aim", 0.42)])
    store.undo_batch(change["batchId"])
    discover = services.relevant_now.ensure_first_visit("cs2")
    assert not any(card["crossGame"] and card["settingId"] == "cs2.kbmouse.mouse_sensitivity"
                   for card in discover["items"])
