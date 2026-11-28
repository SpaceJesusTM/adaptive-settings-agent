"""Optional local-model decision stages using factual, bounded inputs."""
from __future__ import annotations

import json
import re
from dataclasses import replace
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from ..catalog.schema import DIMENSION_LABELS
from .explain import explanation_target, named_controls
from .objective import Objective, explicit_memory_clauses, protected_setting_ids, quoted_as_example
from .schemas import AssistantDraft, DimensionLit, DraftRecommendation
from .scope import ScopePlan

_REQUESTS_CHANGE = re.compile(r"\b(?:fix|adjust|configure|optimi[sz]e|change|set up|help|make|recommend|suggest)\b", re.I)
_ADVICE_REQUEST = re.compile(r"\b(?:how|what) (?:can|could|should) i\b", re.I)
_CONTRAST = re.compile(r"\b(?:except|rather than|more than|care more|worth|unless|but|instead|same as)\b", re.I)
_HARD_WORDS = re.compile(r"\b(?:keep|leave|preserve|alone|unchanged|avoid|never|don't|do not|no changes|without)\b", re.I)


class Interpretation(BaseModel):
    action: Literal["recommend", "explain", "clarify", "other"] = Field(
        description="recommend for in-game options or adjustments, explain for questions about function."
    )
    objective_quote: str = Field(default="", description="Verbatim text in the current user's request expressing the active objective.")
    dimensions: list[DimensionLit] = Field(default_factory=list, description="Dimensions that express the desired benefit.")
    request_quote: str = Field(default="", description="Verbatim words asking for options or an adjustment.")
    exclusion_quotes: list[str] = Field(default_factory=list, description="Verbatim clauses that explicitly protect settings.")
    explanation_quote: str = Field(default="", description="Verbatim explanation request, if any.")
    question: str = Field(default="", description="One short clarification for unresolved consequential ambiguity.")


class Selection(BaseModel):
    choice_numbers: list[int] = Field(default_factory=list, description="Numbers of worthwhile changes in the given candidate rows.")
    reply: str = Field(description="Summarize the decision and most important trade-off in 1–3 sentences.")
    uncertainty: str = Field(default="", description="Relevant unknowns, if any.")


def should_interpret(store, game: str, message: str, objective: Objective, scope: ScopePlan) -> bool:
    if (objective.clear or quoted_as_example(message) or (not objective.text and explicit_memory_clauses(message, game))
            or explanation_target(store, game, message) or re.match(r"^\s*(?:what does|explain|where is)\b", message, re.I)):
        return False
    return bool(_CONTRAST.search(message) or (scope.scope == "explain_only" and len(message.split()) >= 5))


async def interpret(model, trace, game: str, message: str, history: list[str], controls: list[dict], timeout: float):
    system = (
        "Interpret the current turn for the active game's in-game settings menu. Stay inside this menu. "
        "Classify a request for options as recommend; a question about a control's function as explain. "
        "Use the user's desired effect to choose a dimension, even if they do not know the name of a setting. "
        "The menu entries are context, not additional intent. Clarify only ambiguities that would materially change advice. Preserve exclusions, "
        "and keep the current objective separate from accepted costs, habitual preferences and quoted examples. "
        "Copy short evidence spans from the user. Prior messages are context only. Do not propose values or save memory."
    )
    invoker = model.with_structured_output(Interpretation, method="json_schema", include_raw=True)
    out = await trace.invoke("interpret", invoker, [
        SystemMessage(system),
        HumanMessage(json.dumps({
            "game": game, "recent": history[-4:], "request": message,
            "dimensions": DIMENSION_LABELS, "nearby_menu_entries": controls,
        }, ensure_ascii=False)),
    ], timeout=timeout)
    parsed = out.get("parsed") if isinstance(out, dict) else out
    return parsed if isinstance(parsed, Interpretation) else None


def evidence_span(message: str, quote: str) -> str:
    phrase = quote.strip()
    return phrase if len(phrase) >= 5 and phrase.casefold() in message.casefold() else ""


def apply_interpretation(store, game, message, objective, scope, protected, parsed):
    """Use model semantics for relevance. Exact constraints and eligibility stay in code."""
    if parsed is None:
        return objective, scope, protected, None
    if parsed.action == "clarify" and parsed.question and not objective.explicit:
        return objective, scope, protected, AssistantDraft(intent="clarify", reply=parsed.question)
    clause = evidence_span(message, parsed.objective_quote)
    dims = list(dict.fromkeys(parsed.dimensions))[:5]
    explanation = evidence_span(message, parsed.explanation_quote) or objective.explanation
    objective = replace(objective, explanation=explanation)
    grounded_protections = set()
    unresolved = False
    for quote in parsed.exclusion_quotes[:4]:
        span = evidence_span(message, quote)
        if not span or not _HARD_WORDS.search(span):
            continue
        controls = protected_setting_ids(store, game, span) | {s.id for s in named_controls(store, game, span)}
        grounded_protections.update(controls)
        if not controls:
            unresolved = True
    protected |= grounded_protections
    if unresolved and parsed.action == "recommend":
        return objective, scope, protected, AssistantDraft(
            intent="clarify", reply="Which setting or settings should stay unchanged?",
        )
    if parsed.action == "recommend" and clause and dims:
        objective = replace(objective, text=clause, dimensions=dims, explicit=True)
        if scope.scope == "explain_only":
            request = evidence_span(message, parsed.request_quote)
            requested_options = request and (_REQUESTS_CHANGE.search(request) or _ADVICE_REQUEST.search(request))
            scope = replace(scope, scope="category_optimization", max_recs=8,
                            auto_stage=bool(requested_options),
                            reason="Objective inferred from the current request.")
        scope = replace(scope, inferred_dimensions=dims)
    return objective, scope, protected, None


async def select_candidates(model, trace, *, game, message, objective, candidates, maximum):
    rows = [
        [index, c["label"], c["currentDisplay"], c["targetDisplay"], c["dimensionLabel"], c["why"], c["tradeoff"]]
        for index, c in enumerate(candidates, 1)
    ]
    invoker = model.with_structured_output(Selection, method="json_schema", include_raw=True)
    out = await trace.invoke("select", invoker, [
        SystemMessage(
            "Review candidate adjustments in a game-settings simulator. Select every candidate that materially helps "
            "the current request, up to the cap. Skip unrelated diagnostics and changes for a priority the user is "
            "willing to trade away. Use indices only. The player will explicitly apply any chosen changes. "
            "Describe the main trade-off and keep uncertainty honest. Never claim a value was applied or benchmarked."
        ),
        HumanMessage(json.dumps({"game": game, "request": message, "objective": objective,
                                 "cap": maximum, "rows": rows}, ensure_ascii=False)),
    ])
    parsed = out.get("parsed") if isinstance(out, dict) else out
    if not isinstance(parsed, Selection):
        return None
    recs = []
    for number in dict.fromkeys(parsed.choice_numbers):
        if not 1 <= number <= len(candidates) or len(recs) >= maximum:
            continue
        row = candidates[number - 1]
        recs.append(DraftRecommendation(
            setting_id=row["settingId"], proposed_value=str(row["targetValue"]),
            why_for_goal=row["why"], tradeoff_note=row["tradeoff"], goal_dimension=row["dimension"],
            confidence="medium" if row["whyBasis"] == "official" else "low",
        ))
    return AssistantDraft(intent="recommend", reply=parsed.reply, recommendations=recs,
                          knowns_and_unknowns=parsed.uncertainty)
