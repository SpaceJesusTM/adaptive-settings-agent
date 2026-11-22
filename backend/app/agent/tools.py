"""Read-only tools available to the model.

None of these functions can change setting values, locks, preferences, files or SQL: they only read a
snapshot. "Action" outputs (proposals, navigation, explanations, preference suggestions) are returned as
data in the model's final structured answer and validated server-side; staging/applying them always
requires an explicit user action.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field

from ..catalog.schema import DIMENSION_LABELS, Setting
from ..domain.profile import ProfileService
from ..domain.store import Store
from ..domain.values import availability_problem, display_value
from .intent import detect_dimensions

MAX_TOOL_RESULT_CHARS = 6000


@dataclass
class ToolContext:
    store: Store
    profile: ProfileService
    game: str
    ui_state: dict[str, Any] = field(default_factory=dict)


def _snapshot(ctx: ToolContext) -> tuple[dict[str, Any], set[str], set[str], dict[str, Any]]:
    conn = ctx.store.connect()
    try:
        values = ctx.store.flat_values(conn, ctx.game)
        locks = set(ctx.store.locks(conn, ctx.game))
        pins = set(ctx.store.pins(conn, ctx.game))
        hw = ctx.store.hardware(conn)
        return values, locks, pins, hw
    finally:
        conn.close()


def options_text(s: Setting) -> str:
    if s.controlType in ("dropdown", "segmented", "preset"):
        return " | ".join(o.label for o in (s.validOptions or []))
    if s.controlType == "slider":
        if s.display == "percent":
            return f"number {s.min:g}-{s.max:g} (shown as %), step {s.step:g}"
        unit = f" {s.unit}" if s.unit else ""
        return f"number {s.min:g}-{s.max:g}{unit}, step {s.step:g}"
    if s.controlType == "color":
        return "hex color #RRGGBB"
    return "key name"


def compact_record(ctx: ToolContext, s: Setting, values: dict[str, Any], locks: set[str], hw: dict[str, Any]) -> dict[str, Any]:
    cur = values.get(s.id)
    rec: dict[str, Any] = {
        "id": s.id, "path": s.canonicalPath, "current": display_value(s, cur), "allowed": options_text(s),
    }
    if s.id in locks:
        rec["locked"] = True
    problem = availability_problem(ctx.store.registry, s, values, hw)
    if problem:
        rec["unavailable"] = problem
    if not s.aiProposable:
        rec["proposable"] = False
    return rec


def detail_record(ctx: ToolContext, s: Setting, values: dict[str, Any], locks: set[str], hw: dict[str, Any]) -> dict[str, Any]:
    rec = compact_record(ctx, s, values, locks, hw)
    rec.update({
        "what_it_does": s.description,
        "tradeoffs": s.riskOrTradeoffs,
        "goal_hints": [{"goal": DIMENSION_LABELS[h.dimension], "suggested": [display_value(s, v) for v in h.prefer],
                        "reason": h.why, "basis": h.basis} for h in s.goalHints],
        "verification": s.verificationStatus,
        "source_date": s.sourceDate,
    })
    if s.verificationNotes:
        rec["verification_notes"] = s.verificationNotes
    return rec


# ---------------------------------------------------------------------------- tool implementations

def get_current_ui_state(ctx: ToolContext) -> dict[str, Any]:
    values, locks, pins, hw = _snapshot(ctx)
    reg = ctx.store.registry
    return {
        "game": ctx.game,
        "viewing": ctx.ui_state.get("path") or ctx.ui_state.get("tabId"),
        "focused_setting": ctx.ui_state.get("focusedSettingId"),
        "simulated_pc": {k: v for k, v in hw.items() if k != "label"},
        "locked_settings": [reg.setting(ctx.game, i).exactLabel for i in locks if reg.setting(ctx.game, i)],
        "pinned_settings": [reg.setting(ctx.game, i).exactLabel for i in pins if reg.setting(ctx.game, i)],
    }


def list_settings(ctx: ToolContext, tab: Optional[str] = None) -> dict[str, Any]:
    values, locks, _pins, hw = _snapshot(ctx)
    out = []
    for s in ctx.store.registry.settings(ctx.game):
        if s.controlType in ("keybind", "preset"):
            continue
        if tab and tab.lower() not in (s.tabId, s.category.lower()):
            continue
        out.append(compact_record(ctx, s, values, locks, hw))
    return {"settings": out}


def get_setting_details(ctx: ToolContext, setting_ids: list[str]) -> dict[str, Any]:
    values, locks, _pins, hw = _snapshot(ctx)
    found, missing = [], []
    for sid in setting_ids[:6]:
        s = ctx.store.registry.setting(ctx.game, sid)
        if s is None:
            missing.append(sid)
        else:
            found.append(detail_record(ctx, s, values, locks, hw))
    return {"settings": found, "unknown_ids": missing}


_SEARCH_STOPWORDS = frozenset({
    "the", "for", "and", "with", "what", "does", "should", "can", "could", "would", "how", "why",
    "where", "when", "which", "who", "this", "that", "these", "those", "turn", "set", "use", "keep",
    "change", "enable", "disable", "lower", "raise", "make", "need", "want", "find", "show", "menu",
    "setting", "settings", "game", "valorant", "cs2", "on", "off", "in", "to", "is", "are", "do",
    "my", "me", "it", "be", "or", "an", "of", "at", "by", "from", "into", "over", "under", "about",
})


def _tokens_for(text: str) -> set[str]:
    lower = (text or "").lower()
    raw = re.findall(r"[a-z0-9\-+]+", lower)
    return set(raw) | {t.replace("-", "") for t in raw}


def search_settings(ctx: ToolContext, query: str, limit: int = 6) -> dict[str, Any]:
    values, locks, _pins, hw = _snapshot(ctx)
    raw_words = [w for w in re.findall(r"[a-z0-9\-+]+", (query or "").lower()) if len(w) > 1]
    words = [w for w in raw_words if w not in _SEARCH_STOPWORDS] or raw_words
    dims = set(detect_dimensions(query or ""))
    q_norm = re.sub(r"[^a-z0-9]+", "", (query or "").lower())
    scored = []
    for s in ctx.store.registry.settings(ctx.game):
        if s.controlType == "preset":
            continue
        label, path, desc = s.exactLabel.lower(), s.canonicalPath.lower(), s.description.lower()
        label_toks = _tokens_for(label)
        path_toks = _tokens_for(path)
        desc_toks = _tokens_for(desc)
        score = 0.0
        if query and (query.lower().strip() in label or (q_norm and len(q_norm) > 2 and q_norm in re.sub(r"[^a-z0-9]+", "", label))):
            score += 6
        for w in words:
            wn = w.replace("-", "")
            if w in label_toks or wn in label_toks:
                score += 6.0
            elif w in label:
                score += 2.5
            elif w in path_toks or wn in path_toks:
                score += 3.0
            elif w in path:
                score += 1.5
            elif w in desc_toks or wn in desc_toks:
                score += 1.5
            elif w in desc:
                score += 0.5
        score += 2 * len(dims & set(s.goalTags))
        if score > 0 and s.aiProposable:
            score += 0.25
        if score > 0:
            scored.append((score, s.order, s))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return {"results": [compact_record(ctx, s, values, locks, hw) for _, _, s in scored[: max(1, min(limit, 10))]]}


def get_user_preferences(ctx: ToolContext) -> dict[str, Any]:
    conn = ctx.store.connect()
    try:
        prefs = ctx.profile.preferences(conn)
        goals = ctx.profile.session_goals(conn, ctx.game)
        context = ctx.profile.active_context(conn, ctx.game)
        return {
            "saved_preferences": [{"goal": p["dimensionLabel"], "direction": p["direction"], "scope": p["scope"],
                                   "from_game": p.get("originGame"),
                                   "evidence": [e["detail"] for e in p["evidence"][:3] if e.get("detail")]} for p in prefs],
            "session_goals": [{"text": g["text"], "goals": [DIMENSION_LABELS.get(d, d) for d in g["dimensions"]]} for g in goals],
            "simulated_context_event": context["label"] if context else None,
        }
    finally:
        conn.close()


def get_change_history(ctx: ToolContext, limit: int = 8) -> dict[str, Any]:
    batches = ctx.store.history(ctx.game, limit=max(1, min(limit, 15)))
    return {"recent_changes": [{"when": b["createdAt"], "source": b["sourceLabel"], "undone": bool(b["undoneByBatchId"]),
                                "changes": [f"{e['label']}: {e['oldDisplay']} -> {e['newDisplay']}" for e in b["events"]]}
                               for b in batches]}


# ---------------------------------------------------------------------------- schemas for native tool calling

class _NoArgs(BaseModel):
    pass


class _ListArgs(BaseModel):
    tab: Optional[str] = Field(default=None, description="Optional tab id or name to restrict the list, e.g. 'video'.")


class _DetailArgs(BaseModel):
    setting_ids: list[str] = Field(description="Up to 6 exact setting ids from the SETTINGS list.")


class _SearchArgs(BaseModel):
    query: str = Field(description="Words describing the setting or goal, e.g. 'anti-aliasing' or 'hear footsteps'.")
    limit: int = Field(default=6, description="Maximum results (1-10).")


class _HistoryArgs(BaseModel):
    limit: int = Field(default=8, description="Number of recent change batches (1-15).")


TOOL_SPECS: dict[str, dict[str, Any]] = {
    "get_current_ui_state": {"fn": get_current_ui_state, "args": _NoArgs,
                             "description": "Read the current game, the menu location the user is viewing, locks, pins and the simulated PC."},
    "list_settings": {"fn": list_settings, "args": _ListArgs,
                      "description": "List settings (id, path, current value, allowed values), optionally for one tab."},
    "get_setting_details": {"fn": get_setting_details, "args": _DetailArgs,
                            "description": "Read catalogue details for specific setting ids: what it does, trade-offs, goal hints, verification."},
    "search_settings": {"fn": search_settings, "args": _SearchArgs,
                        "description": "Search this game's settings catalogue by words or goal."},
    "get_user_preferences": {"fn": get_user_preferences, "args": _NoArgs,
                             "description": "Read saved preferences (with evidence), session goals and any simulated context event."},
    "get_change_history": {"fn": get_change_history, "args": _HistoryArgs,
                           "description": "Read recent setting changes and whether they were undone."},
}


def run_tool(ctx: ToolContext, name: str, args: dict[str, Any]) -> tuple[dict[str, Any], Optional[str]]:
    """Execute a read-only tool by name with validated args. Returns (result, error)."""
    spec = TOOL_SPECS.get(name)
    if spec is None:
        return {}, f"Unknown tool '{name}'"
    try:
        parsed = spec["args"].model_validate(args or {})
    except Exception as exc:  # noqa: BLE001 - report validation problems back to the model
        return {}, f"Invalid arguments for {name}: {exc}"
    fn: Callable[..., dict[str, Any]] = spec["fn"]
    result = fn(ctx, **parsed.model_dump())
    return result, None


def langchain_tools() -> list[Any]:
    """Tool schemas for `bind_tools` (execution happens in run_tool, never inside LangChain)."""
    from langchain_core.tools import StructuredTool

    tools = []
    for name, spec in TOOL_SPECS.items():
        def _unused(**_kwargs: Any) -> str:  # pragma: no cover - never executed by LangChain
            raise RuntimeError("tools are executed by the bounded workflow, not by LangChain")
        tools.append(StructuredTool.from_function(func=_unused, name=name, description=spec["description"],
                                                  args_schema=spec["args"]))
    return tools
