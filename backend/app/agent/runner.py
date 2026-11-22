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

from ..config import Settings
from ..domain.db import dumps, loads, new_id, now_iso, write_tx
from ..domain.errors import Conflict, Invalid, NotFound
from ..domain.profile import ProfileService
from ..domain.store import Store
from .fallback import fallback_draft
from .graph import InvalidModelToolCall, build_turn_graph, make_chat_models
from .health import describe_status, model_label, probe_ollama
from .validate import validate_draft

ModelFactory = Callable[[Settings], tuple[Any, Any]]


@dataclass
class RunHandle:
    run_id: str
    game: str
    status: str = "running"
    steps: list[dict[str, Any]] = field(default_factory=list)
    task: Optional[asyncio.Task] = None
    started: float = field(default_factory=time.perf_counter)

    def step(self, label: str) -> None:
        self.steps.append({"label": label, "at": now_iso()})


class AgentRunner:
    def __init__(self, store: Store, profile: ProfileService, settings: Settings,
                 model_factory: ModelFactory = make_chat_models):
        self.store = store
        self.profile = profile
        self.settings = settings
        self.model_factory = model_factory
        self._active: dict[str, RunHandle] = {}
        self._game_run: dict[str, str] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ public API
    async def start(self, game: str, message: str, ui_state: dict[str, Any]) -> dict[str, Any]:
        self.store.require_game(game)
        text = (message or "").strip()
        if not text:
            raise Invalid("Message is empty")
        if len(text) > 1000:
            raise Invalid("Message is too long (1000 characters max)")
        async with self._lock:
            if game in self._game_run:
                raise Conflict("The assistant is still answering your previous message. Wait or cancel it first.",
                               code="run_in_progress", details={"runId": self._game_run[game]})
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
                        (run_id, game, session.get("condition"), session.get("sessionId"), "running",
                         session.get("aiMode", "local"), self.settings.ollama_model or None, text[:120], now_iso()))
                    if self.settings.store_chat_history:
                        conn.execute("INSERT INTO chat_messages(id, game, session_id, role, content_json, run_id, created_at) "
                                     "VALUES (?,?,?,?,?,?,?)",
                                     (new_id("msg"), game, session.get("sessionId"), "user", dumps({"text": text}), run_id, now_iso()))
            finally:
                conn.close()
            handle = RunHandle(run_id=run_id, game=game)
            handle.step("Request received")
            self._active[run_id] = handle
            self._game_run[game] = run_id
            handle.task = asyncio.create_task(self._execute(handle, text, ui_state or {}))
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
            return {"runId": run_id, "game": row["game"], "status": "running", "steps": handle.steps,
                    "elapsedMs": round((time.perf_counter() - handle.started) * 1000)}
        return self._row_view(row)

    def thread(self, game: str) -> list[dict[str, Any]]:
        conn = self.store.connect()
        try:
            sess = self.store.session(conn)
            rows = conn.execute("SELECT * FROM chat_messages WHERE game = ? AND session_id = ? ORDER BY created_at, rowid",
                                (game, sess["sessionId"])).fetchall()
            return [{"id": r["id"], "role": r["role"], "runId": r["run_id"], "createdAt": r["created_at"], **loads(r["content_json"], {})}
                    for r in rows]
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
        out = {"runId": row["id"], "game": row["game"], "condition": row["condition"], "status": row["status"],
               "mode": row["mode"], "model": row["model"], "goalExcerpt": row["goal_excerpt"],
               "steps": loads(row["steps_json"], []), "toolCalls": loads(row["tool_calls_json"], []),
               "validation": loads(row["validation_json"], {}), "proposalIds": loads(row["proposal_ids_json"], []),
               "error": row["error"], "latencyMs": row["latency_ms"], "startedAt": row["started_at"],
               "finishedAt": row["finished_at"]}
        if include_result:
            out["result"] = loads(row["result_json"], None)
        return out

    async def _execute(self, handle: RunHandle, message: str, ui_state: dict[str, Any]) -> None:
        game = handle.game
        trace: list[dict[str, Any]] = []
        model_calls: list[dict[str, Any]] = []
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
            probe = await probe_ollama(self.settings) if ai_mode != "fallback" else {"state": "not_configured"}
            indicator = describe_status(probe, ai_mode)
            if ai_mode == "fallback":
                fallback_reason = "Fallback mode is selected in the research controls."
            elif probe["state"] != "connected":
                fallback_reason = probe.get("message") or "Local model unavailable."
            else:
                handle.step(f"Asking local model {model_label(probe)}")
                try:
                    plan_model, compose_model = self.model_factory(self.settings)
                    graph = build_turn_graph(store=self.store, profile=self.profile, plan_model=plan_model,
                                             compose_model=compose_model, max_tool_rounds=self.settings.agent_max_tool_rounds,
                                             progress=handle.step)
                    final = await asyncio.wait_for(
                        graph.ainvoke({"game": game, "message": message, "ui_state": ui_state},
                                      config={"recursion_limit": 25}),
                        timeout=self.settings.agent_deadline_s)
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
                provenance = {"source": "ai", "model": model_label(probe), "modelTag": self.settings.ollama_model,
                              "indicator": indicator["indicator"]}
            else:
                handle.step("Using the offline rule-based fallback (not AI-generated)")
                draft = fallback_draft(self.store, self.profile, game, message, ui_state)
                validated = validate_draft(self.store, game, draft, source="fallback")
                provenance = {"source": "fallback", "model": None, "fallbackReason": fallback_reason,
                              "indicator": indicator["indicator"]}
                status = "fallback"
            handle.step("Done")
        except asyncio.CancelledError:
            handle.status = "cancelled"
            self._finish(handle, status="cancelled", result=None, provenance=None, trace=trace, model_calls=model_calls,
                         error="Cancelled by user")
            raise
        except Exception as exc:  # noqa: BLE001
            handle.status = "failed"
            self._finish(handle, status="failed", result=None, provenance=None, trace=trace, model_calls=model_calls,
                         error=f"{exc.__class__.__name__}: {str(exc)[:200]}")
            return
        handle.status = status
        self._finish(handle, status=status, result=validated, provenance=provenance, trace=trace,
                     model_calls=model_calls, error=fallback_reason, message=message)

    def _finish(self, handle: RunHandle, *, status: str, result: Optional[dict[str, Any]], provenance: Optional[dict[str, Any]],
                trace: list[dict[str, Any]], model_calls: list[dict[str, Any]], error: Optional[str],
                message: Optional[str] = None) -> None:
        latency = round((time.perf_counter() - handle.started) * 1000)
        conn = self.store.connect()
        try:
            with write_tx(conn):
                sess = self.store.session(conn)
                if result is not None:
                    result = {**result, "provenance": {**(provenance or {}), "latencyMs": latency}}
                    if result.get("intent") == "recommend" and result.get("goalDimensions") and message:
                        goal_id = self.profile.set_session_goal(conn, handle.game, message[:160], result["goalDimensions"], "chat")
                        result["sessionGoalId"] = goal_id
                    if self.settings.store_chat_history:
                        conn.execute("INSERT INTO chat_messages(id, game, session_id, role, content_json, run_id, created_at) VALUES (?,?,?,?,?,?,?)",
                                     (new_id("msg"), handle.game, sess.get("sessionId"), "assistant",
                                      dumps({"response": result}), handle.run_id, now_iso()))
                elif status == "cancelled" and self.settings.store_chat_history:
                    conn.execute("INSERT INTO chat_messages(id, game, session_id, role, content_json, run_id, created_at) VALUES (?,?,?,?,?,?,?)",
                                 (new_id("msg"), handle.game, sess.get("sessionId"), "system",
                                  dumps({"text": "Request cancelled. Nothing was changed."}), handle.run_id, now_iso()))
                validation = {"filtered": (result or {}).get("filtered", []), "notes": (result or {}).get("validationNotes", []),
                              "modelCalls": model_calls}
                conn.execute(
                    "UPDATE agent_runs SET status = ?, steps_json = ?, tool_calls_json = ?, validation_json = ?, result_json = ?, "
                    "error = ?, latency_ms = ?, finished_at = ?, mode = ? WHERE id = ?",
                    (status, dumps(handle.steps), dumps(trace), dumps(validation), dumps(result) if result is not None else None,
                     error, latency, now_iso(), (provenance or {}).get("source", "none") if provenance else "none", handle.run_id))
        finally:
            conn.close()
            self._game_run.pop(handle.game, None)
            self._active.pop(handle.run_id, None)
