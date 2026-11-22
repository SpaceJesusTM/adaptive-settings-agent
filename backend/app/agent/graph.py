"""Bounded LangGraph workflow for one assistant turn.

    prepare -> plan <-> tools (<= AGENT_MAX_TOOL_ROUNDS rounds, <= 4 calls each) -> compose -> validate
                                                                       ^                  |
                                                                       +---- repair (<=1)-+

* `prepare` is deterministic: it reads state through the same read-only tools and pre-selects candidate
  settings (goal tags + keyword search) so the model always sees grounded catalogue facts.
* `plan` lets the model request further read-only lookups via native tool calls (Gemma 4 supports them in
  Ollama); tools are executed here, never by LangChain, and every call is traced.
* `compose` asks for one schema-constrained JSON object (Ollama `format` = JSON schema).
* `validate` is the deterministic authority boundary (see validate.py). One repair round is allowed.
The model never receives a write tool; the graph has no node that mutates settings.
"""
from __future__ import annotations

import json
import time
from typing import Any, Callable, Optional, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph

from ..domain.profile import ProfileService
from ..domain.recommender import rank_candidates
from ..domain.store import Store
from .intent import detect_dimensions
from .prompts import compose_messages, plan_messages, render_context
from .schemas import AssistantDraft
from .tools import MAX_TOOL_RESULT_CHARS, ToolContext, get_current_ui_state, get_user_preferences, langchain_tools, run_tool, search_settings
from .validate import needs_repair, validate_draft

MAX_CALLS_PER_ROUND = 4
ProgressFn = Callable[[str], None]


class InvalidModelToolCall(ValueError):
    """The model returned a native tool call that could not be decoded."""


class TurnState(TypedDict, total=False):
    game: str
    message: str
    ui_state: dict[str, Any]
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


def _to_lc(messages: list[tuple[str, str]]) -> list[BaseMessage]:
    out: list[BaseMessage] = []
    for role, text in messages:
        out.append(SystemMessage(text) if role == "system" else HumanMessage(text))
    return out


def _usage(msg: Any) -> dict[str, Any]:
    meta = getattr(msg, "response_metadata", {}) or {}
    usage = getattr(msg, "usage_metadata", None) or {}
    return {"inputTokens": usage.get("input_tokens"), "outputTokens": usage.get("output_tokens"),
            "evalMs": round(meta.get("eval_duration", 0) / 1e6) if meta.get("eval_duration") else None,
            "loadMs": round(meta.get("load_duration", 0) / 1e6) if meta.get("load_duration") else None}


def build_turn_graph(*, store: Store, profile: ProfileService, plan_model: Any, compose_model: Any,
                     max_tool_rounds: int, progress: ProgressFn):
    """`plan_model` must support `.bind_tools`; `compose_model` must support `.with_structured_output`."""

    def ctx_for(state: TurnState) -> ToolContext:
        return ToolContext(store=store, profile=profile, game=state["game"], ui_state=state.get("ui_state") or {})

    async def prepare(state: TurnState) -> dict[str, Any]:
        progress("Reading your current settings and preferences")
        ctx = ctx_for(state)
        trace = []
        t0 = time.perf_counter()
        get_current_ui_state(ctx)
        trace.append({"tool": "get_current_ui_state", "by": "workflow", "ok": True, "ms": round((time.perf_counter() - t0) * 1000)})
        t0 = time.perf_counter()
        get_user_preferences(ctx)
        trace.append({"tool": "get_user_preferences", "by": "workflow", "ok": True, "ms": round((time.perf_counter() - t0) * 1000)})
        conn = store.connect()
        try:
            weights = profile.dimension_weights(conn, state["game"])
            for d in detect_dimensions(state["message"]):
                entry = weights.setdefault(d, {"weight": 0.0, "reasons": []})
                entry["weight"] = round(entry["weight"] + 1.0, 3)
            ranked = rank_candidates(store, profile, conn, state["game"], weights=weights, limit=8, exclude_dismissed=False)
        finally:
            conn.close()
        t0 = time.perf_counter()
        searched = search_settings(ctx, state["message"], limit=5)["results"]
        trace.append({"tool": "search_settings", "by": "workflow", "args": {"query": state["message"][:80]}, "ok": True,
                      "ms": round((time.perf_counter() - t0) * 1000)})
        candidates = list(dict.fromkeys([c["settingId"] for c in ranked] + [h["id"] for h in searched]))[:10]
        context = render_context(ctx, candidates=candidates, weights=weights)
        return {"context": context, "candidates": candidates, "trace": trace, "tool_rounds": 0, "observations": [],
                "model_calls": [], "repairs": 0,
                "plan_history": _to_lc(plan_messages(state["game"], context, state["message"]))}

    async def plan(state: TurnState) -> dict[str, Any]:
        progress("Local model is checking whether it needs more details")
        bound = plan_model.bind_tools(langchain_tools())
        t0 = time.perf_counter()
        ai: AIMessage = await bound.ainvoke(state["plan_history"])
        if ai.invalid_tool_calls:
            raise InvalidModelToolCall()
        calls = list(getattr(ai, "tool_calls", []) or [])[:MAX_CALLS_PER_ROUND]
        mc = state.get("model_calls", []) + [{"step": "plan", "ms": round((time.perf_counter() - t0) * 1000),
                                               "toolCalls": [c.get("name") for c in calls], **_usage(ai)}]
        return {"plan_history": state["plan_history"] + [ai], "pending_calls": calls, "model_calls": mc}

    def after_plan(state: TurnState) -> str:
        if state.get("pending_calls") and state.get("tool_rounds", 0) < max_tool_rounds:
            return "tools"
        return "compose"

    async def tools(state: TurnState) -> dict[str, Any]:
        ctx = ctx_for(state)
        history = list(state["plan_history"])
        observations = list(state.get("observations", []))
        trace = list(state.get("trace", []))
        for call in state.get("pending_calls", []):
            name, args = call.get("name", ""), call.get("args", {}) or {}
            progress(f"Looking up: {name}")
            t0 = time.perf_counter()
            result, err = run_tool(ctx, name, args)
            payload = {"error": err} if err else result
            text = json.dumps(payload, ensure_ascii=False)[:MAX_TOOL_RESULT_CHARS]
            history.append(ToolMessage(content=text, tool_call_id=call.get("id") or name, name=name))
            observations.append({"tool": name, "args": args, "result": payload})
            trace.append({"tool": name, "by": "model", "args": args, "ok": err is None, "error": err,
                          "ms": round((time.perf_counter() - t0) * 1000)})
        return {"plan_history": history, "observations": observations, "trace": trace, "pending_calls": [],
                "tool_rounds": state.get("tool_rounds", 0) + 1}

    async def compose(state: TurnState) -> dict[str, Any]:
        progress("Local model is writing suggestions" if not state.get("repair_feedback") else "Asking the model to fix invalid output")
        structured = compose_model.with_structured_output(AssistantDraft, method="json_schema", include_raw=True)
        msgs = _to_lc(compose_messages(state["game"], state["context"], state["message"], state.get("observations", []),
                                       state.get("repair_feedback")))
        t0 = time.perf_counter()
        out = await structured.ainvoke(msgs)
        raw = out.get("raw") if isinstance(out, dict) else None
        parsed = out.get("parsed") if isinstance(out, dict) else out
        err = out.get("parsing_error") if isinstance(out, dict) else None
        mc = state.get("model_calls", []) + [{"step": "compose" if not state.get("repair_feedback") else "repair",
                                               "ms": round((time.perf_counter() - t0) * 1000), "parsed": parsed is not None,
                                               "parseError": str(err)[:300] if err else None, **(_usage(raw) if raw is not None else {})}]
        raw_text = getattr(raw, "content", None) if raw is not None else None
        return {"draft": parsed if isinstance(parsed, AssistantDraft) else None,
                "raw_output": raw_text[:4000] if isinstance(raw_text, str) else None, "model_calls": mc}

    async def validate(state: TurnState) -> dict[str, Any]:
        progress("Checking suggestions against the catalogue, your locks and allowed values")
        draft = state.get("draft")
        validated = validate_draft(store, state["game"], draft, source="ai") if draft is not None else None
        feedback = needs_repair(draft, validated, state["message"])
        return {"validated": validated, "repair_feedback": feedback}

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
    g.add_edge("prepare", "plan")
    g.add_conditional_edges("plan", after_plan, {"tools": "tools", "compose": "compose"})
    g.add_edge("tools", "plan")
    g.add_edge("compose", "validate")
    g.add_conditional_edges("validate", after_validate, {"repair": "repair", END: END})
    g.add_edge("repair", "compose")
    return g.compile()


def make_chat_models(settings) -> tuple[Any, Any]:
    """Real models for the configured exact Ollama tag (plan: short outputs; compose: JSON answer)."""
    from langchain_ollama import ChatOllama

    common = dict(model=settings.ollama_model, base_url=settings.ollama_base_url, temperature=settings.ollama_temperature,
                  num_ctx=settings.ollama_num_ctx, reasoning=settings.ollama_think, keep_alive="15m",
                  client_kwargs={"timeout": settings.ollama_timeout_s},
                  async_client_kwargs={"timeout": settings.ollama_timeout_s})
    # Tool calls are short; a tight cap stops the planning call from drafting a full answer that is discarded anyway.
    plan_model = ChatOllama(num_predict=2048 if settings.ollama_think else 160, **common)
    compose_model = ChatOllama(num_predict=6000 if settings.ollama_think else 1800, **common)
    return plan_model, compose_model
