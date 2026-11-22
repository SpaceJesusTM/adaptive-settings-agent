"""HTTP API. All mutations go through the domain services; AI endpoints never write setting values."""
from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from .. import __version__
from ..agent.health import describe_status, probe_ollama, reset_cache
from ..catalog.schema import DIMENSION_LABELS
from ..domain.db import write_tx
from ..domain.errors import Conflict, Invalid
from ..domain.profile import CONTEXT_EVENTS
from ..domain.scenarios import export_state, import_state, list_scenarios, reset, write_backup
from ..domain.store import Change
from ..services import Services

router = APIRouter(prefix="/api")


def svc(request: Request) -> Services:
    return request.app.state.services


def require_adaptive(s: Services) -> None:
    conn = s.store.connect()
    try:
        if s.store.session(conn).get("condition") != "adaptive":
            raise Conflict("This feature is only available in the adaptive condition.", code="baseline_condition")
    finally:
        conn.close()


# ----------------------------------------------------------------------------------- models

class SessionUpdate(BaseModel):
    condition: Optional[Literal["baseline", "adaptive"]] = None
    selectedGame: Optional[Literal["valorant", "cs2"]] = None
    adaptationEnabled: Optional[bool] = None
    aiMode: Optional[Literal["local", "fallback"]] = None


class SettingChangeIn(BaseModel):
    value: Any
    expectedRevision: Optional[int] = None
    clientRequestId: Optional[str] = Field(default=None, max_length=80)


class BatchItem(BaseModel):
    settingId: str
    value: Any
    expectedRevision: Optional[int] = None


class BatchIn(BaseModel):
    changes: list[BatchItem] = Field(min_length=1, max_length=40)
    clientRequestId: Optional[str] = Field(default=None, max_length=80)
    label: Optional[str] = Field(default=None, max_length=120)


class UndoIn(BaseModel):
    clientRequestId: Optional[str] = Field(default=None, max_length=80)


class FlagIn(BaseModel):
    on: bool


class ProposalItemIn(BaseModel):
    settingId: str
    proposedValue: Any
    why: Optional[str] = Field(default=None, max_length=1200)
    tradeoff: Optional[str] = Field(default=None, max_length=1200)
    confidence: Optional[Literal["low", "medium", "high"]] = None
    dimensions: list[str] = Field(default_factory=list)
    basedOn: Optional[str] = Field(default=None, max_length=400)


class ProposalIn(BaseModel):
    game: Literal["valorant", "cs2"]
    source: Literal["ai", "fallback", "rules"]
    runId: Optional[str] = None
    title: Optional[str] = Field(default=None, max_length=120)
    items: list[ProposalItemIn] = Field(min_length=1, max_length=8)


class ItemEditIn(BaseModel):
    value: Any


class ApplyIn(BaseModel):
    itemIds: list[str] = Field(min_length=1, max_length=8)
    idempotencyKey: Optional[str] = Field(default=None, max_length=80)


class RejectIn(BaseModel):
    itemIds: Optional[list[str]] = None
    reason: Optional[str] = Field(default=None, max_length=200)


class ChatIn(BaseModel):
    game: Literal["valorant", "cs2"]
    message: str = Field(min_length=1, max_length=1000)
    uiState: dict[str, Any] = Field(default_factory=dict)


class ContextEventIn(BaseModel):
    game: Literal["valorant", "cs2"]
    eventType: Optional[str] = None


class DismissIn(BaseModel):
    settingId: str
    reason: Optional[str] = Field(default=None, max_length=120)


class PreferenceIn(BaseModel):
    dimension: str
    direction: Literal["prioritize", "deprioritize"] = "prioritize"
    scope: Literal["durable", "session"] = "durable"
    source: Literal["user_explicit", "chat_confirmed"] = "user_explicit"
    game: Optional[Literal["valorant", "cs2"]] = None
    originGame: Optional[Literal["valorant", "cs2"]] = None
    note: Optional[str] = Field(default=None, max_length=200)


class ResetIn(BaseModel):
    scenario: str = "default"
    mode: Literal["full", "ai_only"] = "full"


# ----------------------------------------------------------------------------------- meta

@router.get("/health")
def health(request: Request) -> dict[str, Any]:
    s = svc(request)
    return {"ok": True, "version": __version__, "games": s.registry.games, "db": s.settings.db_path.name}


@router.get("/model/status")
async def model_status(request: Request, force: bool = False) -> dict[str, Any]:
    s = svc(request)
    if force:
        reset_cache()
    probe = await probe_ollama(s.settings, force=force)
    conn = s.store.connect()
    try:
        ai_mode = s.store.session(conn).get("aiMode", "local")
    finally:
        conn.close()
    return describe_status(probe, ai_mode)


@router.get("/session")
def get_session(request: Request) -> dict[str, Any]:
    s = svc(request)
    conn = s.store.connect()
    try:
        return s.store.session(conn)
    finally:
        conn.close()


@router.put("/session")
def put_session(body: SessionUpdate, request: Request) -> dict[str, Any]:
    s = svc(request)
    conn = s.store.connect()
    try:
        return s.store.update_session(conn, **body.model_dump(exclude_none=True))
    finally:
        conn.close()


@router.get("/games")
def games(request: Request) -> list[dict[str, Any]]:
    s = svc(request)
    out = []
    for g in s.registry.games:
        c = s.registry.catalog(g)
        out.append({"game": g, "displayName": c.displayName, "shortName": c.shortName, "catalogVersion": c.catalogVersion,
                    "settingCount": len(c.settings), "lastReviewed": c.lastReviewed})
    return out


@router.get("/games/{game}/catalog")
def catalog(game: str, request: Request) -> dict[str, Any]:
    s = svc(request)
    s.store.require_game(game)
    return s.registry.catalog(game).model_dump()


@router.get("/games/{game}/state")
def game_state(game: str, request: Request) -> dict[str, Any]:
    s = svc(request)
    s.store.require_game(game)
    conn = s.store.connect()
    try:
        pending = [r["id"] for r in conn.execute("SELECT id FROM proposals WHERE game = ? AND status = 'pending' ORDER BY created_at",
                                                  (game,))]
        return {"game": game, "gameRevision": s.store.game_revision(conn, game), "values": s.store.values(conn, game),
                "pins": s.store.pins(conn, game), "locks": s.store.locks(conn, game), "pendingProposalIds": pending,
                "hardware": s.store.hardware(conn)}
    finally:
        conn.close()


@router.get("/games/{game}/search")
def search(game: str, request: Request, q: str = Query(min_length=1, max_length=80)) -> list[dict[str, Any]]:
    s = svc(request)
    s.store.require_game(game)
    words = [w for w in q.lower().split() if w]
    results = []
    for st in s.registry.settings(game):
        hay_label, hay_path, hay_desc = st.exactLabel.lower(), st.canonicalPath.lower(), st.description.lower()
        score = 0.0
        if q.lower() in hay_label:
            score += 10
        for w in words:
            score += 4 if w in hay_label else (2 if w in hay_path else (1 if w in hay_desc else 0))
        if words and all(w in hay_label + " " + hay_path for w in words):
            score += 3
        if score > 0:
            results.append((score, st.order, {"settingId": st.id, "label": st.exactLabel, "path": st.canonicalPath,
                                              "tabId": st.tabId, "subtabId": st.subtabId, "sectionId": st.sectionId}))
    results.sort(key=lambda t: (-t[0], t[1]))
    return [r for _, _, r in results[:12]]


# ----------------------------------------------------------------------------------- manual changes, history

@router.put("/games/{game}/settings/{setting_id}")
def change_setting(game: str, setting_id: str, body: SettingChangeIn, request: Request) -> dict[str, Any]:
    return svc(request).store.manual_change(game, [Change(setting_id, body.value, body.expectedRevision)],
                                            client_request_id=body.clientRequestId)


@router.post("/games/{game}/batch")
def change_batch(game: str, body: BatchIn, request: Request) -> dict[str, Any]:
    return svc(request).store.manual_change(game, [Change(c.settingId, c.value, c.expectedRevision) for c in body.changes],
                                            client_request_id=body.clientRequestId, label=body.label)


@router.get("/games/{game}/history")
def history(game: str, request: Request, limit: int = Query(default=100, ge=1, le=500)) -> list[dict[str, Any]]:
    return svc(request).store.history(game, limit)


@router.post("/history/{batch_id}/undo")
def undo(batch_id: str, body: UndoIn, request: Request) -> dict[str, Any]:
    return svc(request).store.undo_batch(batch_id, client_request_id=body.clientRequestId)


@router.put("/games/{game}/pins/{setting_id}")
def pin(game: str, setting_id: str, body: FlagIn, request: Request) -> dict[str, Any]:
    s = svc(request)
    require_adaptive(s)
    return {"pins": s.store.set_flag("pins", game, setting_id, body.on)}


@router.put("/games/{game}/locks/{setting_id}")
def lock(game: str, setting_id: str, body: FlagIn, request: Request) -> dict[str, Any]:
    s = svc(request)
    require_adaptive(s)
    return {"locks": s.store.set_flag("locks", game, setting_id, body.on)}


# ----------------------------------------------------------------------------------- proposals

@router.get("/games/{game}/proposals")
def list_proposals(game: str, request: Request, status: Optional[str] = None) -> list[dict[str, Any]]:
    return svc(request).proposals.list(game, status)


@router.post("/proposals")
def create_proposal(body: ProposalIn, request: Request) -> dict[str, Any]:
    s = svc(request)
    require_adaptive(s)
    return s.proposals.create(body.game, source=body.source, run_id=body.runId, title=body.title,
                              items=[i.model_dump() for i in body.items])


@router.get("/proposals/{proposal_id}")
def get_proposal(proposal_id: str, request: Request) -> dict[str, Any]:
    return svc(request).proposals.get(proposal_id)


@router.patch("/proposals/{proposal_id}/items/{item_id}")
def edit_item(proposal_id: str, item_id: str, body: ItemEditIn, request: Request) -> dict[str, Any]:
    s = svc(request)
    require_adaptive(s)
    return s.proposals.edit_item(proposal_id, item_id, body.value)


@router.post("/proposals/{proposal_id}/items/{item_id}/rebase")
def rebase_item(proposal_id: str, item_id: str, request: Request) -> dict[str, Any]:
    s = svc(request)
    require_adaptive(s)
    return s.proposals.rebase_item(proposal_id, item_id)


@router.post("/proposals/{proposal_id}/apply")
def apply_proposal(proposal_id: str, body: ApplyIn, request: Request) -> dict[str, Any]:
    s = svc(request)
    require_adaptive(s)
    return s.proposals.apply(proposal_id, body.itemIds, body.idempotencyKey)


@router.post("/proposals/{proposal_id}/reject")
def reject_proposal(proposal_id: str, body: RejectIn, request: Request) -> dict[str, Any]:
    return svc(request).proposals.reject(proposal_id, body.itemIds, body.reason)


# ----------------------------------------------------------------------------------- assistant

@router.post("/chat", status_code=202)
async def chat(body: ChatIn, request: Request) -> dict[str, Any]:
    return await svc(request).runner.start(body.game, body.message, body.uiState)


@router.get("/chat/runs/{run_id}")
def run_status(run_id: str, request: Request) -> dict[str, Any]:
    return svc(request).runner.status(run_id)


@router.post("/chat/runs/{run_id}/cancel")
async def run_cancel(run_id: str, request: Request) -> dict[str, Any]:
    return await svc(request).runner.cancel(run_id)


@router.get("/games/{game}/chat")
def chat_thread(game: str, request: Request) -> list[dict[str, Any]]:
    s = svc(request)
    s.store.require_game(game)
    return s.runner.thread(game)


@router.delete("/games/{game}/chat")
def clear_chat(game: str, request: Request) -> dict[str, Any]:
    s = svc(request)
    s.store.require_game(game)
    s.runner.clear_thread(game)
    return {"ok": True}


@router.get("/traces")
def traces(request: Request, game: Optional[str] = None, limit: int = Query(default=30, ge=1, le=200)) -> list[dict[str, Any]]:
    return svc(request).runner.traces(limit, game)


# ----------------------------------------------------------------------------------- relevant now & context

@router.get("/games/{game}/relevant-now")
def relevant_now(game: str, request: Request) -> dict[str, Any]:
    s = svc(request)
    s.store.require_game(game)
    require_adaptive(s)
    conn = s.store.connect()
    try:
        enabled = s.store.session(conn).get("adaptationEnabled", True)
    finally:
        conn.close()
    if not enabled:
        return {"game": game, "items": [], "disabled": True, "updateAvailable": False}
    return s.relevant_now.ensure_first_visit(game)


@router.post("/games/{game}/relevant-now/refresh")
def relevant_now_refresh(game: str, request: Request) -> dict[str, Any]:
    s = svc(request)
    s.store.require_game(game)
    require_adaptive(s)
    return s.relevant_now.refresh(game, "user_refresh")


@router.post("/games/{game}/relevant-now/dismiss")
def relevant_now_dismiss(game: str, body: DismissIn, request: Request) -> dict[str, Any]:
    s = svc(request)
    require_adaptive(s)
    return s.relevant_now.dismiss(game, body.settingId, body.reason)


@router.get("/context-events")
def context_event_types() -> list[dict[str, Any]]:
    return [{"eventType": k, "label": v["label"], "dimensions": v["dimensions"], "simulated": True} for k, v in CONTEXT_EVENTS.items()]


@router.post("/context-events")
def set_context_event(body: ContextEventIn, request: Request) -> dict[str, Any]:
    s = svc(request)
    require_adaptive(s)
    conn = s.store.connect()
    try:
        with write_tx(conn):
            s.profile.set_context(conn, body.game, body.eventType)
    finally:
        conn.close()
    return s.relevant_now.refresh(body.game, "context_event")


# ----------------------------------------------------------------------------------- profile

@router.get("/profile")
def profile(request: Request) -> dict[str, Any]:
    s = svc(request)
    conn = s.store.connect()
    try:
        return {
            "preferences": s.profile.preferences(conn),
            "sessionGoals": {g: s.profile.session_goals(conn, g) for g in s.registry.games},
            "context": {g: s.profile.active_context(conn, g) for g in s.registry.games},
            "evidence": s.profile.evidence(conn, 40),
            "dimensions": [{"id": k, "label": v} for k, v in DIMENSION_LABELS.items()],
        }
    finally:
        conn.close()


@router.post("/profile/preferences")
def add_preference(body: PreferenceIn, request: Request) -> dict[str, Any]:
    s = svc(request)
    require_adaptive(s)
    return s.profile.add_preference(dimension=body.dimension, direction=body.direction, scope=body.scope, source=body.source,
                                    game=body.game, origin_game=body.originGame or body.game, note=body.note)


@router.delete("/profile/preferences/{pref_id}")
def remove_preference(pref_id: str, request: Request) -> dict[str, Any]:
    svc(request).profile.remove_preference(pref_id)
    return {"ok": True}


@router.delete("/games/{game}/session-goals")
def clear_goals(game: str, request: Request) -> dict[str, Any]:
    s = svc(request)
    s.store.require_game(game)
    s.profile.clear_session_goals(game)
    return {"ok": True}


# ----------------------------------------------------------------------------------- admin / study controls

@router.get("/admin/scenarios")
def scenarios(request: Request) -> list[dict[str, Any]]:
    return list_scenarios(svc(request).settings.scenario_dir)


@router.post("/admin/reset")
def admin_reset(body: ResetIn, request: Request) -> dict[str, Any]:
    s = svc(request)
    if any(True for _ in s.runner._game_run):  # noqa: SLF001 - refuse to reset under an active AI run
        raise Conflict("Wait for (or cancel) the running assistant request before resetting.", code="run_in_progress")
    return reset(s.store, s.settings.scenario_dir, s.settings.backup_dir, body.scenario, body.mode)


@router.get("/admin/export")
def admin_export(request: Request) -> dict[str, Any]:
    return export_state(svc(request).store)


@router.post("/admin/import")
async def admin_import(request: Request) -> dict[str, Any]:
    s = svc(request)
    data = await request.json()
    if not isinstance(data, dict):
        raise Invalid("Expected a JSON object")
    backup = write_backup(s.store, s.settings.backup_dir, "before_import")
    import_state(s.store, data)
    return {"ok": True, "backup": str(backup)}
