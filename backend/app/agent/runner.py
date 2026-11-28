"""Run manager for assistant turns: single-flight per game, deadline, cancellation, persisted traces.

Each turn produces a concise trace row (agent_runs): run id, condition, game, a short goal excerpt, model id,
tool names, validation problems, latency and outcome. Full user text is kept only in the chat thread
(which can be disabled with STORE_CHAT_HISTORY=false); traces store at most a 120-character excerpt.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import httpx
from ollama import ResponseError

from .exact import exact_draft
from .explain import comparison_draft, pending_status_draft
from .objective import interpret_objective, preference_removal, protected_setting_ids, quoted_as_example
from .schemas import AssistantDraft
from .scope import ScopePlan
from ..catalog.schema import DIMENSION_LABELS
from ..config import Settings
from ..domain.db import dumps, loads, new_id, now_iso, write_tx
from ..domain.errors import Conflict, Invalid, NotFound
from ..domain.observations import FACT_SETTING_MAP
from ..domain.profile import PERSONAL_FACT_TYPES, ProfileService
from ..domain.proposals import ProposalService
from ..domain.recommender import RelevantNowService
from ..domain.store import Store
from .fallback import fallback_turn
from .graph import InvalidModelToolCall, build_turn_graph, make_chat_models
from .health import describe_status, model_label, probe_ollama
from .intent import is_speculative
from .validate import validate_draft
from .telemetry import TurnTelemetry

ModelFactory = Callable[[Settings], tuple[Any, Any]]


@dataclass
class RunHandle:
    run_id: str
    game: str
    status: str = "running"
    steps: list[dict[str, Any]] = field(default_factory=list)
    task: Optional[asyncio.Task] = None
    started: float = field(default_factory=time.perf_counter)
    telemetry: TurnTelemetry = field(default_factory=TurnTelemetry)
    starting_revisions: dict[str, int] | None = None
    starting_context: dict[str, Any] | None = None

    def step(self, label: str) -> None:
        self.steps.append({"label": label, "at": now_iso()})


class AgentRunner:
    def __init__(
        self,
        store: Store,
        profile: ProfileService,
        settings: Settings,
        model_factory: ModelFactory = make_chat_models,
        proposals: Optional[ProposalService] = None,
        relevant_now: Optional[RelevantNowService] = None,
    ):
        self.store = store
        self.profile = profile
        self.settings = settings
        self.model_factory = model_factory
        self.proposals = proposals or ProposalService(store, profile)
        self.relevant_now = relevant_now or RelevantNowService(store, profile, policy=settings.agent_discovery_policy)
        self._active: dict[str, RunHandle] = {}
        self._game_run: dict[str, str] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ public API
    async def start(
        self,
        game: str,
        message: str,
        ui_state: dict[str, Any],
        *,
        scope_override: Optional[str] = None,
    ) -> dict[str, Any]:
        self.store.require_game(game)
        text = (message or "").strip()
        if not text:
            raise Invalid("Message is empty")
        if len(text) > 1000:
            raise Invalid("Message is too long (1000 characters max)")
        async with self._lock:
            if game in self._game_run:
                raise Conflict(
                    "The assistant is still answering your previous message. Wait or cancel it first.",
                    code="run_in_progress",
                    details={"runId": self._game_run[game]},
                )
            conn = self.store.connect()
            try:
                session = self.store.session(conn)
                if session.get("condition") != "adaptive":
                    raise Invalid("The assistant is only available in the adaptive condition.", code="baseline_condition")
                run_id = new_id("run")
                with write_tx(conn):
                    conn.execute(
                        "INSERT INTO agent_runs(id, game, condition, session_id, status, mode, model, goal_excerpt, started_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?)",
                        (
                            run_id,
                            game,
                            session.get("condition"),
                            session.get("sessionId"),
                            "running",
                            session.get("aiMode", "local"),
                            self.settings.ollama_model or None,
                            text[:120],
                            now_iso(),
                        ),
                    )
                    if self.settings.store_chat_history:
                        conn.execute(
                            "INSERT INTO chat_messages(id, game, session_id, role, content_json, run_id, created_at) "
                            "VALUES (?,?,?,?,?,?,?)",
                            (
                                new_id("msg"),
                                game,
                                session.get("sessionId"),
                                "user",
                                dumps({"text": text}),
                                run_id,
                                now_iso(),
                            ),
                        )
            finally:
                conn.close()
            handle = RunHandle(run_id=run_id, game=game)
            handle.step("Request received")
            self._active[run_id] = handle
            self._game_run[game] = run_id
            handle.task = asyncio.create_task(self._execute(handle, text, ui_state or {}, scope_override))
        return self.status(run_id)

    async def cancel(self, run_id: str) -> dict[str, Any]:
        handle = self._active.get(run_id)
        if handle is None:
            return self.status(run_id)
        if handle.task and not handle.task.done():
            handle.task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(handle.task), timeout=5)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):  # noqa: BLE001
                pass
        return self.status(run_id)

    def status(self, run_id: str) -> dict[str, Any]:
        handle = self._active.get(run_id)
        conn = self.store.connect()
        try:
            row = conn.execute("SELECT * FROM agent_runs WHERE id = ?", (run_id,)).fetchone()
        finally:
            conn.close()
        if row is None:
            raise NotFound("Unknown run")
        if handle is not None and handle.status == "running":
            return {
                "runId": run_id,
                "game": row["game"],
                "status": "running",
                "steps": handle.steps,
                "elapsedMs": round((time.perf_counter() - handle.started) * 1000),
            }
        return self._row_view(row)

    def thread(self, game: str) -> list[dict[str, Any]]:
        conn = self.store.connect()
        try:
            sess = self.store.session(conn)
            rows = conn.execute(
                "SELECT * FROM chat_messages WHERE game = ? AND session_id = ? ORDER BY created_at, rowid",
                (game, sess["sessionId"]),
            ).fetchall()
            return [
                {"id": r["id"], "role": r["role"], "runId": r["run_id"], "createdAt": r["created_at"], **loads(r["content_json"], {})}
                for r in rows
            ]
        finally:
            conn.close()

    def clear_thread(self, game: str) -> None:
        conn = self.store.connect()
        try:
            with write_tx(conn):
                sess = self.store.session(conn)
                conn.execute("DELETE FROM chat_messages WHERE game = ? AND session_id = ?", (game, sess["sessionId"]))
        finally:
            conn.close()

    def traces(self, limit: int = 30, game: Optional[str] = None) -> list[dict[str, Any]]:
        conn = self.store.connect()
        try:
            q, args = "SELECT * FROM agent_runs", []
            if game:
                q += " WHERE game = ?"
                args.append(game)
            q += " ORDER BY started_at DESC LIMIT ?"
            args.append(limit)
            return [self._row_view(r, include_result=False) for r in conn.execute(q, args).fetchall()]
        finally:
            conn.close()

    # ------------------------------------------------------------------ internals
    @staticmethod
    def _row_view(row: Any, include_result: bool = True) -> dict[str, Any]:
        out = {
            "runId": row["id"],
            "game": row["game"],
            "condition": row["condition"],
            "status": row["status"],
            "mode": row["mode"],
            "model": row["model"],
            "goalExcerpt": row["goal_excerpt"],
            "steps": loads(row["steps_json"], []),
            "toolCalls": loads(row["tool_calls_json"], []),
            "validation": loads(row["validation_json"], {}),
            "proposalIds": loads(row["proposal_ids_json"], []),
            "error": row["error"],
            "latencyMs": row["latency_ms"],
            "startedAt": row["started_at"],
            "finishedAt": row["finished_at"],
        }
        if include_result:
            out["result"] = loads(row["result_json"], None)
        return out

    async def _execute(
        self,
        handle: RunHandle,
        message: str,
        ui_state: dict[str, Any],
        scope_override: Optional[str] = None,
    ) -> None:
        game = handle.game
        trace = handle.telemetry.tools
        model_calls = handle.telemetry.calls
        provenance: dict[str, Any]
        validated: Optional[dict[str, Any]] = None
        fallback_reason: Optional[str] = None
        status = "succeeded"
        try:
            conn = self.store.connect()
            try:
                ai_mode = self.store.session(conn).get("aiMode", "local")
            finally:
                conn.close()
            objective = interpret_objective(message)
            if quoted_as_example(message):
                direct_draft = AssistantDraft(intent="other", reply="This reads as a quoted example. Tell me which settings goal you want to try.")
            elif objective.clear:
                direct_draft = AssistantDraft(intent="other", reply="I cleared the current goal. Your saved preferences still apply.")
            elif preference_removal(message):
                direct_draft = AssistantDraft(intent="preference", reply="I checked System Understanding for that preference.")
            else:
                direct_draft = (
                    exact_draft(self.store, game, message)
                    or pending_status_draft(self.store, game, message)
                    or comparison_draft(self.store, game, message)
                )
                if direct_draft is None and protected_setting_ids(self.store, game, message) and not objective.text:
                    if not objective.explanation:
                        direct_draft = AssistantDraft(intent="other", reply="I'll keep those settings unchanged for this objective.")
            if direct_draft is not None:
                handle.step("Checking the requested settings")
                scope = ScopePlan(
                    scope="focused" if direct_draft.recommendations else "explain_only",
                    max_recs=len(direct_draft.recommendations),
                    auto_stage=bool(direct_draft.recommendations),
                    include_minor=False,
                    is_supplement=False,
                    reason="Grounded request handled with catalogue, history or profile rules.",
                    inferred_dimensions=[],
                )
                validated = validate_draft(self.store, game, direct_draft, source="rules",
                                           max_recommendations=scope.max_recs, scope_plan=scope, message=message,
                                           inherit_objective=True)
                # Exact setting commands and history recovery do not establish an optimization objective.
                validated.update(goalDimensions=[], goalChanged=False, plan={**scope.to_meta(), "autoStage": scope.auto_stage})
                self._finish(handle, status=status, result=validated,
                             provenance={"source": "rules", "model": None, "indicator": "Catalogue and history"},
                             trace=trace, model_calls=model_calls, error=None, message=message)
                return
            probe = await probe_ollama(self.settings) if ai_mode != "fallback" else {"state": "not_configured"}
            indicator = describe_status(probe, ai_mode)
            if ai_mode == "fallback":
                fallback_reason = "Fallback mode is selected in the research controls."
            elif probe["state"] != "connected":
                fallback_reason = probe.get("message") or "Local model unavailable."
            else:
                handle.step(f"Asking local model {model_label(probe)}")
                try:
                    conn = self.store.connect()
                    try:
                        handle.starting_revisions = {
                            sid: value["revision"] for sid, value in self.store.values(conn, game).items()
                        }
                        handle.starting_context = self.profile.snapshot_context(conn, game)
                    finally:
                        conn.close()
                    plan_model, compose_model = self.model_factory(self.settings)
                    graph = build_turn_graph(
                        store=self.store,
                        profile=self.profile,
                        plan_model=plan_model,
                        compose_model=compose_model,
                        max_tool_rounds=self.settings.agent_max_tool_rounds,
                        progress=handle.step,
                        deadline_s=self.settings.agent_deadline_s,
                        fast_path=self.settings.agent_fast_path,
                        telemetry=handle.telemetry,
                        reasoning_mode=self.settings.agent_reasoning_mode,
                    )
                    final = await asyncio.wait_for(
                        graph.ainvoke(
                            {
                                "game": game,
                                "message": message,
                                "ui_state": ui_state,
                                "scope_override": scope_override,
                            },
                            config={"recursion_limit": 25},
                        ),
                        timeout=self.settings.agent_deadline_s,
                    )
                    trace = final.get("trace", [])
                    model_calls = final.get("model_calls", [])
                    validated = final.get("validated")
                    if validated is None:
                        fallback_reason = "The local model's output could not be parsed or validated against the required JSON schema after one repair attempt."
                    elif any(call["by"] == "model" and not call["ok"] for call in trace):
                        validated["validationNotes"].append("A model-requested lookup failed. Suggestions use the available catalogue information.")
                except asyncio.TimeoutError:
                    fallback_reason = f"The local model did not finish within {self.settings.agent_deadline_s:.0f} s."
                except httpx.TimeoutException:
                    fallback_reason = f"An Ollama request timed out (OLLAMA_TIMEOUT={self.settings.ollama_timeout_s:g} s)."
                except (httpx.ConnectError, ConnectionError):
                    fallback_reason = "Lost the connection to Ollama. Check that Ollama is still running."
                except InvalidModelToolCall:
                    fallback_reason = "The local model returned a malformed tool call."
                except ResponseError as exc:
                    if exc.status_code == 404:
                        fallback_reason = "Ollama could not find the configured model. Check the exact tag with `ollama list`."
                    elif exc.status_code == 400 and "tool" in str(exc.error).lower():
                        fallback_reason = "Ollama rejected tool calling for this model. Check the model's tool support."
                    else:
                        fallback_reason = f"Ollama could not load the model or complete inference (HTTP {exc.status_code}). Check the Ollama logs."
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001 - any model/runtime failure falls back, never corrupts state
                    fallback_reason = f"Local model error ({exc.__class__.__name__}). Check the Ollama service and model configuration."
            if validated is not None:
                provenance = {
                    "source": "ai",
                    "model": model_label(probe),
                    "modelTag": self.settings.ollama_model,
                    "indicator": indicator["indicator"],
                }
            else:
                handle.step("Using basic offline suggestions (not AI-generated)")
                draft, scope_plan, audit = fallback_turn(
                    self.store,
                    self.profile,
                    game,
                    message,
                    ui_state,
                    scope_override=scope_override,
                )
                validated = validate_draft(
                    self.store,
                    game,
                    draft,
                    source="fallback",
                    max_recommendations=scope_plan.max_recs,
                    scope_plan=scope_plan,
                    message=message,
                    focused_setting_id=ui_state.get("focusedSettingId"),
                )
                validated["plan"] = {
                    **scope_plan.to_meta(),
                    "autoStage": scope_plan.auto_stage,
                    "partialCoverage": False,
                    "batchesCompleted": 1,
                    "batchesTotal": 1,
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
                if audit.get("crossGameComparisons"):
                    validated["crossGameComparisons"] = audit["crossGameComparisons"]
                provenance = {
                    "source": "fallback",
                    "model": None,
                    "fallbackReason": fallback_reason,
                    "indicator": indicator["indicator"],
                }
                status = "fallback"
            handle.step("Done")
        except asyncio.CancelledError:
            handle.status = "cancelled"
            self._finish(
                handle,
                status="cancelled",
                result=None,
                provenance=None,
                trace=trace,
                model_calls=model_calls,
                error="Cancelled by user",
            )
            raise
        except Exception as exc:  # noqa: BLE001
            handle.status = "failed"
            self._finish(
                handle,
                status="failed",
                result=None,
                provenance=None,
                trace=trace,
                model_calls=model_calls,
                error=f"{exc.__class__.__name__}: {str(exc)[:200]}",
            )
            return
        handle.status = status
        self._finish(
            handle,
            status=status,
            result=validated,
            provenance=provenance,
            trace=trace,
            model_calls=model_calls,
            error=fallback_reason,
            message=message,
        )

    def _finish(
        self,
        handle: RunHandle,
        *,
        status: str,
        result: Optional[dict[str, Any]],
        provenance: Optional[dict[str, Any]],
        trace: list[dict[str, Any]],
        model_calls: list[dict[str, Any]],
        error: Optional[str],
        message: Optional[str] = None,
    ) -> None:
        latency = round((time.perf_counter() - handle.started) * 1000)
        proposal_ids: list[str] = []
        sync_trigger: Optional[str] = None
        is_adaptive = False
        conn = self.store.connect()
        try:
            with write_tx(conn):
                sess = self.store.session(conn)
                is_adaptive = sess.get("condition") == "adaptive" and bool(sess.get("adaptationEnabled", True))
                if result is not None:
                    result = {**result, "provenance": {**(provenance or {}), "latencyMs": latency}}
                    if provenance and provenance.get("source") == "ai" and handle.starting_context is not None:
                        now_context = self.profile.snapshot_context(conn, handle.game)
                        if handle.starting_context != now_context:
                            result.update(recommendations=[], preferenceSuggestions=[], explicitMemoryActions=[],
                                          goalChanged=False, goalDimensions=[], navigateTo=None,
                                          reply="Your goal or priorities changed while I was working. Ask again to review suggestions against the new context.")
                            result["validationNotes"].append("Discarded advice calculated against an earlier objective.")
                            message = None
                        elif handle.starting_revisions is not None:
                            values = self.store.values(conn, handle.game)
                            recs = result.get("recommendations", [])
                            current = [r for r in recs if handle.starting_revisions.get(r["settingId"]) ==
                                       values.get(r["settingId"], {}).get("revision")]
                            if len(current) != len(recs):
                                result["recommendations"] = current
                                result["reply"] = "Some settings changed while I was working. Review the remaining suggestions against their current values."
                                result["validationNotes"].append("Discarded advice for settings edited during inference.")
                                if result.get("plan", {}).get("coverage"):
                                    result["plan"]["coverage"]["proposedCount"] = len(current)
                    msg_text = (message or "").strip()
                    speculative = bool(msg_text and is_speculative(msg_text))
                    objective = interpret_objective(msg_text)
                    removal = preference_removal(msg_text)
                    if removal:
                        dimension, scope_game = removal
                        matches = [p for p in self.profile.applicable_preferences(conn, scope_game or handle.game)
                                   if p["dimension"] == dimension and p["appliesToGame"] == scope_game]
                        if len(matches) == 1:
                            self.profile.remove_preference_tx(conn, matches[0]["id"])
                            result["reply"] = f"Removed your saved {DIMENSION_LABELS[dimension]} preference."
                            sync_trigger = "memory_update"
                        elif matches:
                            result["reply"] = "I found multiple matching preferences. Choose which one to remove in System Understanding."
                        else:
                            result["reply"] = "I couldn't find a saved preference matching that wording and game scope."
                    elif objective.clear:
                        self.profile.clear_session_goals_tx(conn, handle.game)
                        sync_trigger = "goal_change"
                    elif result.get("goalChanged") and result.get("goalDimensions"):
                        goal_id = self.profile.set_session_goal(
                            conn, handle.game, result.get("objectiveText") or objective.text, result["goalDimensions"], "chat",
                            set(result.get("protectedSettingIds") or ()),
                        )
                        if goal_id:
                            result["sessionGoalId"] = goal_id
                            sync_trigger = "goal_change"
                    elif new_protections := protected_setting_ids(self.store, handle.game, msg_text):
                        current = self.profile.session_goals(conn, handle.game)
                        if current:
                            goal = current[0]
                            goal_id = self.profile.set_session_goal(
                                conn, handle.game, goal["text"], goal["dimensions"], goal["source"],
                                new_protections | set(goal["protectedSettingIds"]),
                            )
                            if goal_id:
                                result["sessionGoalId"] = goal_id
                                sync_trigger = "goal_change"

                    applied_updates: list[dict[str, Any]] = []
                    if msg_text and not speculative:
                        for mem in result.get("explicitMemoryActions", []):
                            if mem.get("kind") == "preference" and mem.get("dimension") in DIMENSION_LABELS:
                                dim = mem["dimension"]
                                direction = mem.get("direction", "prioritize")
                                scope = mem.get("scope", "durable")
                                target_g = mem.get("game") or handle.game
                                pid = self.profile.add_preference_tx(
                                    conn,
                                    dimension=dim,
                                    direction=direction,
                                    scope=scope,
                                    source="chat_explicit",
                                    game=target_g,
                                    origin_game=target_g,
                                    note=mem.get("quote"),
                                    applies_to_game=mem.get("appliesToGame"),
                                )
                                applied_updates.append({
                                    "kind": "preference",
                                    "id": pid,
                                    "dimension": dim,
                                    "dimensionLabel": DIMENSION_LABELS[dim],
                                    "direction": direction,
                                    "scope": scope,
                                    "game": target_g,
                                    "appliesToGame": mem.get("appliesToGame"),
                                    "label": f"{'Prioritize' if direction == 'prioritize' else 'De-prioritize'} {DIMENSION_LABELS[dim]} ({scope})",
                                })
                                sync_trigger = sync_trigger or "memory_update"
                            elif mem.get("kind") == "fact" and mem.get("factKey") in PERSONAL_FACT_TYPES and mem.get("valueText"):
                                fk = mem["factKey"]
                                target_g = mem.get("game") or handle.game
                                src_sid = FACT_SETTING_MAP.get(fk, {}).get(target_g) if fk != "crosshair_style" else None
                                fid = self.profile.add_personal_fact_tx(
                                    conn,
                                    fact_key=fk,
                                    value_text=mem["valueText"],
                                    origin_game=target_g,
                                    source_setting_id=src_sid,
                                    source="chat_explicit",
                                    note=mem.get("quote"),
                                )
                                applied_updates.append({
                                    "kind": "fact",
                                    "id": fid,
                                    "factKey": fk,
                                    "valueText": mem["valueText"],
                                    "originGame": target_g,
                                    "label": f"{PERSONAL_FACT_TYPES[fk]['label']} ({target_g.upper()}): {mem['valueText']}",
                                })
                                sync_trigger = sync_trigger or "memory_update"
                    if applied_updates:
                        result["appliedMemoryUpdates"] = applied_updates

                    plan_meta = result.get("plan") or {}
                    recs = result.get("recommendations") or []
                    should_auto_stage = (
                        status in ("succeeded", "fallback")
                        and plan_meta.get("scope") != "explain_only"
                        and len(recs) > 0
                        and bool(plan_meta.get("autoStage", True))
                    )
                    if should_auto_stage:
                        staged_items = [
                            {
                                "settingId": r["settingId"],
                                "proposedValue": r["proposedValue"],
                                "why": r.get("whyForGoal"),
                                "tradeoff": r.get("tradeoff"),
                                "confidence": r.get("confidence"),
                                "dimensions": [r["dimension"]] if r.get("dimension") else result.get("goalDimensions", []),
                                "basedOn": r.get("basedOn"),
                            }
                            for r in recs
                        ]
                        scope_name = plan_meta.get("scope")
                        title = (
                            f"Comprehensive setup ({len(staged_items)} changes)"
                            if scope_name in ("full_game_setup", "broad_optimization") and len(staged_items) > 3
                            else f"Suggested changes ({len(staged_items)})"
                        )
                        staged = self.proposals.auto_stage_for_run(
                            conn,
                            handle.game,
                            source=(provenance or {}).get("source", "fallback"),
                            run_id=handle.run_id,
                            title=title,
                            items=staged_items,
                            plan=plan_meta,
                        )
                        result["stagedProposalId"] = staged["proposalId"]
                        result["stagedCount"] = staged["stagedCount"]
                        result["alreadyPendingCount"] = staged["alreadyPendingCount"]
                        if staged["proposalId"]:
                            proposal_ids = [staged["proposalId"]]

                    if self.settings.store_chat_history:
                        conn.execute(
                            "INSERT INTO chat_messages(id, game, session_id, role, content_json, run_id, created_at) VALUES (?,?,?,?,?,?,?)",
                            (
                                new_id("msg"),
                                handle.game,
                                sess.get("sessionId"),
                                "assistant",
                                dumps({"response": result}),
                                handle.run_id,
                                now_iso(),
                            ),
                        )
                elif status == "cancelled" and self.settings.store_chat_history:
                    conn.execute(
                        "INSERT INTO chat_messages(id, game, session_id, role, content_json, run_id, created_at) VALUES (?,?,?,?,?,?,?)",
                        (
                            new_id("msg"),
                            handle.game,
                            sess.get("sessionId"),
                            "system",
                            dumps({"text": "Request cancelled. Nothing was changed."}),
                            handle.run_id,
                            now_iso(),
                        ),
                    )
                validation = {
                    "filtered": (result or {}).get("filtered", []),
                    "notes": (result or {}).get("validationNotes", []),
                    "modelCalls": model_calls,
                    "phaseTimingsMs": handle.telemetry.phases,
                }
                conn.execute(
                    "UPDATE agent_runs SET status = ?, steps_json = ?, tool_calls_json = ?, validation_json = ?, result_json = ?, "
                    "proposal_ids_json = ?, error = ?, latency_ms = ?, finished_at = ?, mode = ? WHERE id = ?",
                    (
                        status,
                        dumps(handle.steps),
                        dumps(trace),
                        dumps(validation),
                        dumps(result) if result is not None else None,
                        dumps(proposal_ids),
                        error,
                        latency,
                        now_iso(),
                        (provenance or {}).get("source", "none") if provenance else "none",
                        handle.run_id,
                    ),
                )
        finally:
            conn.close()
            self._game_run.pop(handle.game, None)
            self._active.pop(handle.run_id, None)
        if sync_trigger and is_adaptive:
            self.relevant_now.sync_on_event(handle.game, sync_trigger)
