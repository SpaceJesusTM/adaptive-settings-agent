"""Deterministic scenario replays (no model needed): writes JSON transcripts + a summary to docs/evidence/scenario_replays/.

  python scripts/replay_scenarios.py

Uses the labelled offline fallback and the deterministic ranker, in temporary databases, so results are
reproducible on any machine. Real-model behaviour is recorded separately by scripts/run_model_eval.py.
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

from _common import ROOT, bootstrap_backend_imports, utf8_stdout

OUT = ROOT / "docs" / "evidence" / "scenario_replays"


def summarise(res: dict) -> dict:
    return {"intent": res.get("intent"), "source": (res.get("provenance") or {}).get("source"),
            "recommendations": [f"{r['label']}: {r['currentDisplay']} -> {r['proposedDisplay']}" for r in res.get("recommendations", [])],
            "basedOn": [r.get("basedOn") for r in res.get("recommendations", [])],
            "explanations": [e["label"] for e in res.get("explanations", [])],
            "navigateTo": (res.get("navigateTo") or {}).get("path"),
            "preferenceSuggestions": [(p["dimension"], p["direction"], p["scope"]) for p in res.get("preferenceSuggestions", [])],
            "filtered": [(f.get("kind"), f.get("reason")) for f in res.get("filtered", [])], "reply": res.get("reply")}


async def ask(svc, game: str, text: str) -> dict:
    run = await svc.runner.start(game, text, {})
    while True:
        st = svc.runner.status(run["runId"])
        if st["status"] != "running":
            return st
        await asyncio.sleep(0.02)


def main() -> int:
    utf8_stdout()
    bootstrap_backend_imports()
    from app.agent.schemas import AssistantDraft, DraftRecommendation
    from app.agent.validate import validate_draft
    from app.config import get_settings
    from app.domain.errors import Conflict
    from app.domain.recommender import rank_candidates
    from app.domain.scenarios import reset
    from app.domain.store import Change
    from app.services import build_services

    OUT.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict] = {}

    def fresh(tmp: str, scenario: str, condition: str = "adaptive", game: str = "valorant", ai_mode: str = "fallback"):
        settings = replace(get_settings(), db_path=Path(tmp) / f"{scenario}.db", backup_dir=Path(tmp) / "bk")
        svc = build_services(settings)
        reset(svc.store, settings.scenario_dir, settings.backup_dir, scenario, "full", backup=False)
        conn = svc.store.connect()
        try:
            svc.store.update_session(conn, condition=condition, selectedGame=game, aiMode=ai_mode)
        finally:
            conn.close()
        return svc

    def values(svc, game):
        conn = svc.store.connect()
        try:
            return svc.store.flat_values(conn, game)
        finally:
            conn.close()

    with tempfile.TemporaryDirectory(prefix="csc2524 replay ") as tmp:
        # 1. typical performance goal + goal change
        svc = fresh(tmp, "default")
        before = values(svc, "valorant")
        t1 = asyncio.run(ask(svc, "valorant", "I'm getting frame drops in VALORANT and want smoother competitive play."))
        t2 = asyncio.run(ask(svc, "valorant", "Actually I want to hear footsteps better."))
        results["typical_goal_and_goal_change"] = {"turn1": summarise(t1["result"]), "turn2": summarise(t2["result"]),
                                                   "valuesUnchanged": values(svc, "valorant") == before}
        # 2. unclear goal
        t = asyncio.run(ask(svc, "valorant", "make it better"))
        results["unclear_goal"] = summarise(t["result"])
        # 3. noisy evidence / hold rule
        svc = fresh(tmp, "valorant_history_new_cs2", game="cs2")
        first = svc.relevant_now.ensure_first_visit("cs2")
        svc.store.manual_change("cs2", [Change("cs2.video.particle_detail", "1")])
        svc.profile.add_preference(dimension="performance", direction="prioritize", scope="session", source="user_explicit",
                                   game="cs2", origin_game="cs2", note="replay")
        held = svc.relevant_now.get("cs2")
        results["noisy_evidence_hold"] = {
            "firstVisit": [c["label"] for c in first["items"]],
            "afterNewEvidence": [c["label"] for c in held["items"]],
            "orderHeld": [c["settingId"] for c in first["items"]] == [c["settingId"] for c in held["items"]],
            "updateAvailableFlag": held["updateAvailable"],
        }
        # 4. locked setting: even a model output proposing it is filtered, and apply is refused
        svc = fresh(tmp, "locked_settings")
        draft = AssistantDraft(intent="recommend", reply="Turn VSync off.", recommendations=[
            DraftRecommendation(setting_id="val.video.vsync", proposed_value="Off", why_for_goal="latency", confidence="high")])
        v = validate_draft(svc.store, "valorant", draft, source="ai")
        p = svc.proposals.create("valorant", source="ai", run_id=None, title="replay",
                                 items=[{"settingId": "val.video.bloom", "proposedValue": "off"}])
        svc.store.set_flag("locks", "valorant", "val.video.bloom", True)
        try:
            svc.proposals.apply(p["id"], [p["items"][0]["id"]], None)
            outcome = "applied (unexpected)"
        except Conflict as exc:
            outcome = f"refused: {exc.message}"
        results["locked_setting"] = {"filteredByValidator": v["filtered"], "applyAfterLocking": outcome,
                                     "bloomValue": values(svc, "valorant")["val.video.bloom"]}
        # 5. model failure -> labelled fallback (unreachable endpoint)
        settings = replace(get_settings(), db_path=Path(tmp) / "fail.db", backup_dir=Path(tmp) / "bk2",
                           ollama_base_url="http://127.0.0.1:9", ollama_model="configured-but-unreachable")
        svc = build_services(settings)
        conn = svc.store.connect()
        try:
            svc.store.update_session(conn, condition="adaptive", aiMode="local")
        finally:
            conn.close()
        t = asyncio.run(ask(svc, "valorant", "I want smoother frame rate"))
        results["model_failure"] = {"status": t["status"], "fallbackReason": t["result"]["provenance"].get("fallbackReason"),
                                    **summarise(t["result"])}
        # 6. new CS2 user with VALORANT history
        svc = fresh(tmp, "valorant_history_new_cs2", game="cs2")
        before = values(svc, "cs2")
        conn = svc.store.connect()
        try:
            cands = rank_candidates(svc.store, svc.profile, conn, "cs2", limit=5)
        finally:
            conn.close()
        t = asyncio.run(ask(svc, "cs2", "What should I change based on what I liked in VALORANT? I want low latency and to see players clearly."))
        results["new_cs2_user_with_valorant_history"] = {
            "rankedCandidates": [{"label": c["label"], "to": c["targetDisplay"], "basedOn": c["basedOn"]} for c in cands],
            "chat": summarise(t["result"]), "cs2ValuesUnchanged": values(svc, "cs2") == before,
            "anySensitivityProposed": any("Sensitivity" in c["label"] for c in cands),
        }

    (OUT / "replays.json").write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    md = ["# Deterministic scenario replays (generated)", "",
          "Generated by `python scripts/replay_scenarios.py`. Uses the labelled offline fallback and deterministic ranker",
          "(no model), in temporary databases. Full data: `replays.json`.", ""]
    for name, data in results.items():
        md += [f"## {name}", "", "```json", json.dumps(data, indent=1, ensure_ascii=False)[:3500], "```", ""]
    (OUT / "README.md").write_text("\n".join(md), encoding="utf-8")
    print(f"Wrote {OUT / 'replays.json'} and README.md")
    for name, data in results.items():
        print(f"- {name}: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
