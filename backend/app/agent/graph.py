"""Bounded LangGraph workflow for one assistant turn.

    prepare -> plan <-> tools (<= AGENT_MAX_TOOL_ROUNDS rounds, <= 4 calls each) -> compose -> validate
                                                                       ^                  |
                                                                       +---- repair (<=1)-+

* `prepare` reads current state, classifies scope, and runs a full-catalogue coverage audit.
* `plan` receives a compact state + candidate summary and may call read-only lookup tools.
* `compose` asks for structured JSON (`AssistantDraft`), using bounded per-category batches when a
  broad or full-game setup has more than 10 eligible candidates.
* `validate` enforces allowlists, domains, locks, scope limits, and attaches factual plan metadata.
The model never receives a write tool; the graph has no node that mutates settings.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Callable, Optional, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph

from ..domain.cross_game import compare_cross_game, parse_cross_game_direction
from ..domain.planner import build_coverage_audit
from ..domain.profile import ProfileService
from ..domain.store import Store
from .intent import (
    extract_sensitivity_number,
    is_cross_game_query,
)
from .prompts import (
    compose_batch_messages,
    compose_messages,
    plan_messages,
    recent_conversation,
    render_context,
    render_plan_context,
    scope_instruction_for,
)
from .schemas import AssistantDraft, BatchDraft, DraftRecommendation
from .scope import ScopePlan
from .objective import Objective, objective_takes_precedence, prepare_objective, quoted_as_example
from .decisions import apply_interpretation, interpret, numbered_clauses, select_candidates, should_interpret
from .tools import MAX_TOOL_RESULT_CHARS, ToolContext, langchain_tools, run_tool, search_settings
from .telemetry import TurnTelemetry
from .validate import needs_repair, validate_draft

MAX_CALLS_PER_ROUND = 4
BATCH_SIZE = 12
ProgressFn = Callable[[str], None]
_HISTORY_QUERY_RE = re.compile(
    r"\b(history|previous change|last change|what did i change|changed earlier|undid|already changed|recent change)\b",
    re.I,
)


class InvalidModelToolCall(ValueError):
    """The model returned a native tool call that could not be decoded."""


class TurnState(TypedDict, total=False):
    game: str
    message: str
    ui_state: dict[str, Any]
    scope_override: Optional[str]
    scope_plan: ScopePlan
    objective: Objective
    protected: set[str]
    clarified: AssistantDraft | None
    weights: dict[str, Any]
    audit: dict[str, Any]
    context: str
    candidates: list[str]
    plan_history: list[BaseMessage]
    pending_calls: list[dict[str, Any]]
    tool_rounds: int
    observations: list[dict[str, Any]]
    trace: list[dict[str, Any]]
    model_calls: list[dict[str, Any]]
    draft: Optional[AssistantDraft]
    raw_output: Optional[str]
    validated: Optional[dict[str, Any]]
    repair_feedback: Optional[str]
    repairs: int
    batch_partial: bool
    candidate_window: tuple[int, int]
    batches_completed: int
    batches_total: int
    cross_game_data: Optional[dict[str, Any]]
    needs_plan: bool
    started_mono: float


def _to_lc(messages: list[tuple[str, str]]) -> list[BaseMessage]:
    out: list[BaseMessage] = []
    for role, text in messages:
        out.append(SystemMessage(text) if role == "system" else HumanMessage(text))
    return out


def _category_batches(cands: list[dict[str, Any]], max_recs: int) -> list[tuple[str, list[str]]]:
    groups: dict[str, list[str]] = {}
    for c in cands[:max_recs]:
        groups.setdefault(c["category"], []).append(c["settingId"])
    raw_chunks: list[tuple[str, list[str]]] = []
    for cat, sids in groups.items():
        for i in range(0, len(sids), BATCH_SIZE):
            raw_chunks.append((cat, sids[i: i + BATCH_SIZE]))
    # Pack smaller adjacent category slices up to BATCH_SIZE to reduce sequential LLM calls on full setups.
    packed: list[tuple[str, list[str]]] = []
    for cat, sids in raw_chunks:
        if packed and len(packed[-1][1]) + len(sids) <= BATCH_SIZE:
            prev_cat, prev_ids = packed[-1]
            label = prev_cat if prev_cat == cat else f"{prev_cat} & {cat}"
            packed[-1] = (label, prev_ids + sids)
        else:
            packed.append((cat, list(sids)))
    return packed


def build_turn_graph(
    *,
    store: Store,
    profile: ProfileService,
    plan_model: Any,
    compose_model: Any,
    max_tool_rounds: int,
    progress: ProgressFn,
    deadline_s: float = 240.0,
    fast_path: bool = True,
    telemetry: TurnTelemetry | None = None,
    reasoning_mode: str = "legacy",
):
    """`plan_model` must support `.bind_tools`; `compose_model` must support `.with_structured_output`."""

    measured = telemetry or TurnTelemetry()

    def ctx_for(state: TurnState) -> ToolContext:
        return ToolContext(store=store, profile=profile, game=state["game"], ui_state=state.get("ui_state") or {})

    async def prepare(state: TurnState) -> dict[str, Any]:
        started_mono = time.perf_counter()
        progress("Reading your current settings and preferences")
        ctx = ctx_for(state)
        trace = measured.tools

        conn = store.connect()
        try:
            objective, scope_plan, weights, protected = prepare_objective(
                store, profile, conn, state["game"], state["message"], state.get("scope_override"),
            )
        finally:
            conn.close()
        clarified = None
        if quoted_as_example(state["message"]):
            clarified = AssistantDraft(intent="other", reply="This reads as a quoted example. Tell me which settings goal you want to try.")
        elif reasoning_mode == "semantic" and should_interpret(store, state["game"], state["message"], objective, scope_plan):
            progress("Interpreting your goal and constraints")
            semantic_started = time.perf_counter()
            clauses = numbered_clauses(state["message"])
            try:
                query = re.split(r"\b(?:without\s+(?:changing|touching|adjusting)|leave|keep)\b",
                                 objective.text or state["message"], maxsplit=1, flags=re.I)[0]
                menu_entries = []
                for hit in search_settings(ctx, query, limit=8)["results"]:
                    if hit["id"] in protected:
                        continue
                    setting = store.registry.setting(state["game"], hit["id"])
                    menu_entries.append({"name": setting.exactLabel, "function": setting.description[:140]})
                    if len(menu_entries) == 4:
                        break
                parsed = await interpret(compose_model, measured, state["game"], state["message"],
                                         recent_conversation(store, state["game"], exchanges=1), menu_entries, clauses,
                                         min(45.0, deadline_s * 0.36))
            except Exception:
                parsed = None
            if parsed is not None:
                before = objective
                objective, scope_plan, protected, clarified = apply_interpretation(
                    store, state["game"], state["message"], objective, scope_plan, protected, parsed, clauses,
                )
                measured.calls[-1]["decision"] = {
                    "action": parsed.action, "dimensions": parsed.dimensions,
                    "objectiveGrounded": parsed.objective_clause in clauses,
                    "requestGrounded": parsed.request_clause in clauses,
                    "objectiveChanged": before.text != objective.text or before.dimensions != objective.dimensions,
                }
                if objective != before and objective.explicit:
                    conn = store.connect()
                    try:
                        weights = profile.dimension_weights(conn, state["game"], include_objective=False)
                        profile.prioritize_objective(weights, scope_plan.inferred_dimensions, objective.text,
                                                     takes_precedence=objective_takes_precedence(objective.text))
                        protected.update(profile.objective_protections(conn, state["game"]))
                    finally:
                        conn.close()
            measured.phase("interpretation", semantic_started)
        conn = store.connect()
        try:
            audit = build_coverage_audit(
                store,
                profile,
                conn,
                state["game"],
                weights=weights,
                scope_plan=scope_plan,
                exclude_staged=True,
                exclude_dismissed=False,
                protected=protected,
            )
        finally:
            conn.close()

        t0 = time.perf_counter()
        searched = search_settings(ctx, state["message"], limit=6)["results"]
        trace.append({
            "tool": "search_settings",
            "by": "workflow",
            "args": {"query": state["message"][:80]},
            "ok": True,
            "ms": round((time.perf_counter() - t0) * 1000),
        })

        cross_game_data = None
        if is_cross_game_query(state["message"]):
            src_g, tgt_g, _ = parse_cross_game_direction(state["message"], state["game"])
            conn_cg = store.connect()
            try:
                cross_game_data = compare_cross_game(
                    store,
                    profile,
                    conn_cg,
                    query=state["message"],
                    current_game=state["game"],
                    source_sensitivity=extract_sensitivity_number(state["message"]),
                    source_game=src_g,
                    target_game=tgt_g,
                )
            finally:
                conn_cg.close()
            trace.append({
                "tool": "compare_cross_game_settings",
                "by": "workflow",
                "args": {"query": state["message"][:80]},
                "ok": True,
                "ms": 1,
            })

        audit_ids = [c["settingId"] for c in audit["candidates"][: max(1, scope_plan.max_recs)]]
        if scope_plan.scope == "explain_only":
            candidates = [h["id"] for h in searched][:6]
        elif scope_plan.single_setting_hint and searched:
            candidates = list(dict.fromkeys([h["id"] for h in searched[:3]] + audit_ids[:1]))
        else:
            candidates = list(dict.fromkeys(audit_ids + [h["id"] for h in searched]))[: max(10, scope_plan.max_recs + 4)]

        needs_plan = False
        if max_tool_rounds > 0 and clarified is None:
            if not fast_path:
                needs_plan = True
            elif _HISTORY_QUERY_RE.search(state["message"]):
                needs_plan = True
            elif (
                scope_plan.scope == "explain_only"
                and not searched
                and cross_game_data is None
                and not recent_conversation(store, state["game"], exchanges=1)
            ):
                needs_plan = True

        plan_hist = (
            _to_lc(plan_messages(state["game"], render_plan_context(ctx, scope_plan=scope_plan, audit=audit, searched=searched), state["message"]))
            if needs_plan
            else []
        )
        context = render_context(
            ctx,
            candidates=candidates,
            weights=weights,
            scope_plan=scope_plan,
            audit=audit,
            cross_game_data=cross_game_data,
        )
        if protected:
            labels = [s.exactLabel for s in store.registry.settings(state["game"]) if s.id in protected and s.aiProposable]
            context += "\nKEEP UNCHANGED (explicit user constraint): " + ", ".join(labels)
        if objective.explanation:
            context += "\nAlso address this explanation independently: " + objective.explanation[:200]
        if reasoning_mode == "semantic" and objective.explicit:
            context += "\nCurrent objective grounded in the current request: " + objective.text[:250]
        measured.phase("prepare", started_mono)
        return {
            "scope_plan": scope_plan,
            "objective": objective,
            "protected": protected,
            "clarified": clarified,
            "weights": weights,
            "audit": audit,
            "context": context,
            "candidates": candidates,
            "cross_game_data": cross_game_data,
            "trace": trace,
            "tool_rounds": 0,
            "observations": [],
            "model_calls": measured.calls,
            "repairs": 0,
            "batch_partial": False,
            "batches_completed": 0,
            "batches_total": 1,
            "needs_plan": needs_plan,
            "started_mono": started_mono,
            "plan_history": plan_hist,
        }

    async def plan(state: TurnState) -> dict[str, Any]:
        progress("Checking whether more setting details are needed")
        bound = plan_model.bind_tools(langchain_tools())
        ai: AIMessage = await measured.invoke("plan", bound, state["plan_history"])
        if ai.invalid_tool_calls:
            raise InvalidModelToolCall()
        calls = list(getattr(ai, "tool_calls", []) or [])[:MAX_CALLS_PER_ROUND]
        measured.calls[-1]["toolCalls"] = [c.get("name") for c in calls]
        return {"plan_history": state["plan_history"] + [ai], "pending_calls": calls, "model_calls": measured.calls}

    def after_plan(state: TurnState) -> str:
        if state.get("pending_calls") and state.get("tool_rounds", 0) < max_tool_rounds:
            return "tools"
        return "compose"

    async def tools(state: TurnState) -> dict[str, Any]:
        ctx = ctx_for(state)
        history = list(state["plan_history"])
        observations = list(state.get("observations", []))
        trace = measured.tools
        for call in state.get("pending_calls", []):
            name, args = call.get("name", ""), call.get("args", {}) or {}
            progress(f"Looking up: {name}")
            t0 = time.perf_counter()
            result, err = run_tool(ctx, name, args)
            payload = {"error": err} if err else result
            text = json.dumps(payload, ensure_ascii=False)[:MAX_TOOL_RESULT_CHARS]
            history.append(ToolMessage(content=text, tool_call_id=call.get("id") or name, name=name))
            observations.append({"tool": name, "args": args, "result": payload})
            trace.append({
                "tool": name,
                "by": "model",
                "args": args,
                "ok": err is None,
                "error": err,
                "ms": round((time.perf_counter() - t0) * 1000),
            })
        return {
            "plan_history": history,
            "observations": observations,
            "trace": trace,
            "pending_calls": [],
            "tool_rounds": state.get("tool_rounds", 0) + 1,
        }

    async def compose(state: TurnState) -> dict[str, Any]:
        progress("Writing suggestions" if not state.get("repair_feedback") else "Refining suggestions")
        structured = compose_model.with_structured_output(AssistantDraft, method="json_schema", include_raw=True)
        structured_batch = compose_model.with_structured_output(BatchDraft, method="json_schema", include_raw=True)
        scope_plan: ScopePlan = state["scope_plan"]
        audit = state["audit"]
        mc = measured.calls
        if state.get("clarified") is not None:
            return {"draft": state["clarified"], "model_calls": mc, "batches_completed": 0, "batches_total": 0}
        if (reasoning_mode in {"compact", "semantic"} and scope_plan.scope != "explain_only"
                and len(audit["candidates"]) >= 5 and not scope_plan.single_setting_hint and not state.get("repair_feedback")):
            rows = audit["candidates"][: min(scope_plan.max_recs, 22)]
            decision = await select_candidates(
                compose_model, measured, game=state["game"], message=state["message"],
                objective=state["objective"].text, candidates=rows, maximum=scope_plan.max_recs,
            )
            if decision is not None:
                eligible = min(scope_plan.max_recs, len(audit["candidates"]))
                window = {"candidate_window": (len(rows), eligible)} if len(rows) < eligible else {}
                return {"draft": decision, "model_calls": mc, "batches_completed": 1, "batches_total": 1, **window}

        # Use bounded category-packed passes when a broad/full setup has more than BATCH_SIZE candidates so local Gemma 4
        # stays accurate and well within timeout limits.
        use_batches = (
            scope_plan.scope in ("broad_optimization", "full_game_setup")
            and len(audit["candidates"]) > BATCH_SIZE
            and not state.get("repair_feedback")
        )
        if use_batches:
            batches = _category_batches(audit["candidates"], scope_plan.max_recs)
            merged_recs: list[DraftRecommendation] = []
            seen_sids: set[str] = set()
            first_draft: Optional[AssistantDraft] = None
            raw_samples: list[str] = []
            partial = False
            completed = 0
            ctx = ctx_for(state)
            started_mono = state.get("started_mono") or time.perf_counter()

            for idx, (cat_label, chunk_ids) in enumerate(batches):
                reserve = min(1.0, deadline_s * 0.1)
                remaining = deadline_s - (time.perf_counter() - started_mono) - reserve
                if remaining <= 0:
                    partial = True
                    break
                progress(f"Reviewing {cat_label} settings ({idx + 1}/{len(batches)})")
                bctx = render_context(
                    ctx,
                    candidates=chunk_ids,
                    weights=state["weights"],
                    scope_plan=scope_plan,
                    audit=audit,
                    batch_candidates=chunk_ids,
                    batch_label=cat_label,
                    compact_state=idx > 0,
                )
                inst = scope_instruction_for(scope_plan, batch_label=cat_label, batch_idx=idx, batch_total=len(batches))
                if idx == 0:
                    msgs = _to_lc(compose_messages(
                        state["game"],
                        bctx,
                        state["message"],
                        state.get("observations", []),
                        scope_instruction=inst,
                    ))
                    invoker = structured
                else:
                    msgs = _to_lc(compose_batch_messages(
                        state["game"],
                        bctx,
                        state["message"],
                        scope_instruction=inst,
                    ))
                    invoker = structured_batch
                try:
                    out = await measured.invoke(f"compose:{cat_label}", invoker, msgs, timeout=remaining)
                except Exception:
                    if idx == 0:
                        raise
                    partial = True
                    break
                raw = out.get("raw") if isinstance(out, dict) else None
                parsed = out.get("parsed") if isinstance(out, dict) else out
                raw_text = getattr(raw, "content", None) if raw is not None else None
                if isinstance(raw_text, str):
                    raw_samples.append(raw_text[:800])
                if not isinstance(parsed, (AssistantDraft, BatchDraft)):
                    if idx == 0:
                        return {
                            "draft": None,
                            "raw_output": "\n".join(raw_samples)[:4000] or None,
                            "model_calls": mc,
                            "batch_partial": False,
                            "batches_completed": 0,
                            "batches_total": len(batches),
                        }
                    partial = True
                    break
                if first_draft is None:
                    if isinstance(parsed, AssistantDraft):
                        first_draft = parsed
                    else:
                        first_draft = AssistantDraft(
                            intent="recommend",
                            reply=f"Prepared {cat_label} suggestions for review.",
                            goal_dimensions=scope_plan.inferred_dimensions[:4],
                            recommendations=list(parsed.recommendations),
                        )
                for r in parsed.recommendations:
                    if r.setting_id not in seen_sids:
                        seen_sids.add(r.setting_id)
                        merged_recs.append(r)
                completed += 1

            combined = AssistantDraft(
                intent="recommend" if merged_recs else (first_draft.intent if first_draft else "recommend"),
                reply=first_draft.reply if first_draft else "Prepared recommendations across categories for review.",
                goal_dimensions=(first_draft.goal_dimensions if first_draft else []) or scope_plan.inferred_dimensions[:4],
                knowns_and_unknowns=first_draft.knowns_and_unknowns if first_draft else None,
                recommendations=merged_recs,
                explanations=first_draft.explanations if first_draft else [],
                navigate_to=first_draft.navigate_to if first_draft else None,
                preference_suggestions=first_draft.preference_suggestions if first_draft else [],
                clarifying_question=first_draft.clarifying_question if first_draft else None,
            ) if first_draft is not None else None
            return {
                "draft": combined,
                "raw_output": "\n".join(raw_samples)[:4000] or None,
                "model_calls": mc,
                "batch_partial": partial,
                "batches_completed": completed,
                "batches_total": len(batches),
            }

        inst = scope_instruction_for(scope_plan)
        msgs = _to_lc(compose_messages(
            state["game"],
            state["context"],
            state["message"],
            state.get("observations", []),
            state.get("repair_feedback"),
            scope_instruction=inst,
        ))
        out = await measured.invoke("repair" if state.get("repair_feedback") else "compose", structured, msgs)
        raw = out.get("raw") if isinstance(out, dict) else None
        parsed = out.get("parsed") if isinstance(out, dict) else out
        raw_text = getattr(raw, "content", None) if raw is not None else None
        return {
            "draft": parsed if isinstance(parsed, AssistantDraft) else None,
            "raw_output": raw_text[:4000] if isinstance(raw_text, str) else None,
            "model_calls": mc,
            "batch_partial": False,
            "batches_completed": 1 if parsed is not None else 0,
            "batches_total": 1,
        }

    async def validate(state: TurnState) -> dict[str, Any]:
        started = time.perf_counter()
        progress("Checking suggestions against the catalogue, locks and allowed values")
        draft = state.get("draft")
        scope_plan: ScopePlan = state["scope_plan"]
        audit = state["audit"]
        validated = (
            validate_draft(
                store,
                state["game"],
                draft,
                source="ai",
                max_recommendations=scope_plan.max_recs,
                scope_plan=scope_plan,
                message=state["message"],
                focused_setting_id=(state.get("ui_state") or {}).get("focusedSettingId"),
                objective_override=state.get("objective"),
                extra_protected=state.get("protected"),
            )
            if draft is not None
            else None
        )
        feedback = needs_repair(draft, validated, state["message"], scope_plan=scope_plan, audit=audit)
        if state.get("clarified") is not None:
            feedback = None
        if validated is not None:
            partial = bool(state.get("batch_partial", False))
            completed = int(state.get("batches_completed", 1))
            total = int(state.get("batches_total", 1))
            if state.get("candidate_window") and not state.get("repair_feedback"):
                reviewed, eligible = state["candidate_window"]
                notice = f"Partial review. Considered {reviewed} of {eligible} eligible options."
                validated["reply"] = f"{notice} {validated['reply']}"[:1800]
                validated["validationNotes"].append(notice)
            if partial:
                feedback = None
                validated["reply"] = (
                    f"Partial review. Covered {completed} of {total} settings groups. "
                    + validated["reply"]
                )[:1800]
                validated["validationNotes"].append(
                    f"Partial coverage: finished {completed} of {total} category batches within the turn deadline."
                )
            elif total > 1 and completed > 1 and validated["recommendations"]:
                cats_covered = list(dict.fromkeys(
                    (store.registry.setting(state["game"], r["settingId"]).category if store.registry.setting(state["game"], r["settingId"]) else r.get("tabId", ""))
                    for r in validated["recommendations"]
                ))
                cats_covered = [c for c in cats_covered if c]
                if len(cats_covered) > 1:
                    cats_str = ", ".join(cats_covered)
                    summary_line = f"Prepared {len(validated['recommendations'])} validated suggestions across {cats_str} for your review in Changes."
                    if summary_line not in validated["reply"]:
                        validated["reply"] = (validated["reply"].rstrip() + " " + summary_line)[:1800]
            validated["plan"] = {
                **scope_plan.to_meta(),
                "autoStage": scope_plan.auto_stage,
                "partialCoverage": partial or bool(state.get("candidate_window") and not state.get("repair_feedback")),
                "batchesCompleted": completed,
                "batchesTotal": total,
                "coverage": {
                    "evaluatedCount": audit["evaluatedCount"],
                    "eligibleCount": audit["eligibleCount"],
                    "proposedCount": len(validated["recommendations"]),
                    "alreadyAlignedCount": audit["alreadyAlignedCount"],
                    "tradeoffRetainedCount": audit.get("tradeoffRetainedCount", 0),
                    "alreadyStagedCount": audit["alreadyStagedCount"],
                    "lockedCount": audit["lockedCount"],
                    "unavailableCount": audit["unavailableCount"],
                    "manualCount": audit["manualCount"],
                    "byCategory": audit["byCategory"],
                },
                "alreadyAlignedItems": audit.get("alreadyAlignedItems", []),
                "tradeoffRetainedItems": audit.get("tradeoffRetainedItems", []),
                "lockedItems": audit.get("lockedItems", []),
                "unavailableItems": audit.get("unavailableItems", []),
                "manualConsiderations": audit["manualConsiderations"][:10],
            }
            if state.get("cross_game_data") and state["cross_game_data"].get("comparisons"):
                validated["crossGameComparisons"] = state["cross_game_data"]["comparisons"]
        measured.phase("validate", started)
        return {"validated": validated, "repair_feedback": feedback}

    def after_prepare(state: TurnState) -> str:
        return "plan" if state.get("needs_plan") else "compose"

    def after_tools(state: TurnState) -> str:
        return "compose" if state.get("tool_rounds", 0) >= max_tool_rounds else "plan"

    def after_validate(state: TurnState) -> str:
        if state.get("repair_feedback") and state.get("repairs", 0) < 1:
            return "repair"
        return END

    async def repair(state: TurnState) -> dict[str, Any]:
        return {"repairs": state.get("repairs", 0) + 1}

    g = StateGraph(TurnState)
    g.add_node("prepare", prepare)
    g.add_node("plan", plan)
    g.add_node("tools", tools)
    g.add_node("compose", compose)
    g.add_node("validate", validate)
    g.add_node("repair", repair)
    g.add_edge(START, "prepare")
    g.add_conditional_edges("prepare", after_prepare, {"plan": "plan", "compose": "compose"})
    g.add_conditional_edges("plan", after_plan, {"tools": "tools", "compose": "compose"})
    g.add_conditional_edges("tools", after_tools, {"plan": "plan", "compose": "compose"})
    g.add_edge("compose", "validate")
    g.add_conditional_edges("validate", after_validate, {"repair": "repair", END: END})
    g.add_edge("repair", "compose")
    return g.compile()


def make_chat_models(settings) -> tuple[Any, Any]:
    """Real models for the configured exact Ollama tag (plan: short outputs; compose: JSON answer)."""
    from langchain_ollama import ChatOllama

    common = dict(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        temperature=settings.ollama_temperature,
        num_ctx=settings.ollama_num_ctx,
        reasoning=settings.ollama_think,
        keep_alive="15m",
        client_kwargs={"timeout": settings.ollama_timeout_s},
        async_client_kwargs={"timeout": settings.ollama_timeout_s},
    )
    # Tool calls are short; a tight cap stops the planning call from drafting a full answer that is discarded anyway.
    plan_model = ChatOllama(num_predict=2048 if settings.ollama_think else 160, **common)
    compose_model = ChatOllama(num_predict=6000 if settings.ollama_think else 2200, **common)
    return plan_model, compose_model
