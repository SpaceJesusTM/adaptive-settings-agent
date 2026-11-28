"""Catalogue-backed path for unambiguous setting commands and targeted recovery."""
from __future__ import annotations

import re

from ..domain.db import loads
from ..domain.profile import ProfileService
from ..domain.values import ValueError_, availability_problem, display_value, normalize_value, values_equal
from .objective import protected_setting_ids
from .schemas import AssistantDraft, DraftExplanation, DraftRecommendation

_ALIASES = {
    "valorant": {
        "minimap rotation": "val.general.rotate",
        "volume": "val.audio.overall_volume",
    },
    "cs2": {
        "rotating radar": "cs2.game.radar_rotating",
        "volume": "cs2.audio.master_volume",
        "horizontal hud edge position": "cs2.video.hud_edge_x",
        "horizontal hud edge": "cs2.video.hud_edge_x",
    },
}
_COMMAND = re.compile(r"^(?:please\s+)?(?:set|change|adjust|switch|put)\s+(.+?)\s+(?:to|at)\s+(.+)$", re.I)
_TOGGLE = re.compile(r"^(?:please\s+)?(enable|disable|turn on|turn off)\s+(.+)$", re.I)
_RESTORE = re.compile(
    r"^(?:please\s+)?restore\s+(?:the |my )?(.+?)\s+to\s+(?:what it was before|its previous value)"
    r"(?:\s+(?:those|the|that|my)\s+changes?)?(?:[, ]+(?:but\s+)?keep everything else(?: unchanged)?)?$",
    re.I,
)
_TEMPORAL = r"(?:tonight|today|this (?:session|evening|match)|now|right now)"
_TEMPORAL_PREFIX = re.compile(rf"^(?:just\s+)?(?:for\s+)?{_TEMPORAL}(?:\s+only)?[,]\s*", re.I)
_TEMPORAL_SUFFIX = re.compile(rf"\s+(?:just\s+)?(?:for\s+)?{_TEMPORAL}(?:\s+only)?$", re.I)
_POLITE = re.compile(r"^(?:could|can|would) you\s+", re.I)
_RESTORE_INFORMAL = re.compile(
    r"^put\s+(.+?)\s+back\s+(?:to its previous value|where it was before(?: i touched it| those (?:edits|changes))?)"
    r"(?:[.?!, ]+keep (?:the other (?:edit|change)|everything else)(?: unchanged)?)?$", re.I,
)
_SPLIT = re.compile(r"\s*;\s*|(?:[,.]\s+|(?:,?\s+)and\s+)(?=(?:please\s+)?(?:set|change|adjust|switch|enable|disable|turn on|turn off)\b)", re.I)


def _setting(store, game: str, term: str):
    name = re.sub(r"^(?:the|my)\s+|\s+settings?$", "", term.strip().lower())
    alias = _ALIASES[game].get(name)
    if alias:
        return store.registry.setting(game, alias)
    matches = [s for s in store.registry.settings(game) if name in (s.exactLabel.lower(), s.id)]
    return matches[0] if len(matches) == 1 else None


def _previous_value(store, conn, game: str, setting, current):
    row = conn.execute(
        "SELECT e.old_value_json, e.new_value_json FROM change_events e "
        "JOIN change_batches b ON b.id = e.batch_id "
        "WHERE e.game = ? AND e.setting_id = ? AND b.session_id = ? "
        "AND b.source != 'reset' AND b.undone_by_batch_id IS NULL "
        "ORDER BY b.created_at DESC, b.rowid DESC, e.rowid DESC LIMIT 1",
        (game, setting.id, store.session(conn)["sessionId"]),
    ).fetchone()
    return loads(row["old_value_json"]) if row and values_equal(loads(row["new_value_json"]), current) else None


def exact_draft(store, game: str, message: str) -> AssistantDraft | None:
    """Only claim the turn when every clause identifies a unique setting and literal value."""
    text = _POLITE.sub("", _TEMPORAL_PREFIX.sub("", message.strip().rstrip(".!?")))
    restore = _RESTORE.fullmatch(text) or _RESTORE_INFORMAL.fullmatch(text)
    requested = {}
    if restore:
        setting = _setting(store, game, restore[1])
        if setting is None:
            return None
        requested[setting.id] = (setting, "", False)
    else:
        for clause in _SPLIT.split(text):
            command = _COMMAND.fullmatch(clause)
            toggle = _TOGGLE.fullmatch(clause)
            if not command and not toggle:
                return None
            term = command[1] if command else _TEMPORAL_SUFFIX.sub("", toggle[2])
            setting = _setting(store, game, term)
            if setting is None or setting.id in requested:
                return None
            raw = _TEMPORAL_SUFFIX.sub("", command[2]) if command else toggle[1].lower()
            raw = re.sub(r"(?<=\d)\s+percent$", "%", raw, flags=re.I)
            requested[setting.id] = (setting, raw, toggle is not None)

    recs = []
    explanations = []
    manual_steps = []
    conn = store.connect()
    try:
        values = store.flat_values(conn, game)
        hardware = store.hardware(conn)
        locked = set(store.locks(conn, game))
        protected = protected_setting_ids(store, game, message) | ProfileService(store).objective_protections(conn, game)
        for setting, raw, toggle in requested.values():
            current = values.get(setting.id)
            if restore:
                value = _previous_value(store, conn, game, setting, current)
                if value is None:
                    return AssistantDraft(intent="clarify", reply=f"I could not verify an earlier value for {setting.exactLabel}.",
                                          navigate_to=setting.id)
            else:
                if toggle:
                    labels = {"on", "enabled", "yes"} if raw in ("enable", "turn on") else {"off", "disabled", "no"}
                    opts = [o for o in (setting.validOptions or []) if o.label.lower() in labels]
                    if len(opts) != 1:
                        return None
                    raw = opts[0].value
                if raw.endswith("%") and setting.controlType == "slider" and setting.max == 1 and setting.display != "percent":
                    if setting.unit == "%":
                        return None
                    if setting.id == "cs2.audio.master_volume" and re.fullmatch(r"\d+(?:\.\d+)?%", raw):
                        raw = str(float(raw[:-1]) / 100)
                try:
                    value = normalize_value(setting, raw, strict=True)
                except ValueError_ as exc:
                    if not re.fullmatch(r"[\w+ .%/-]{1,40}", raw):
                        return None
                    return AssistantDraft(intent="clarify", reply=str(exc), navigate_to=setting.id)
            shown = display_value(setting, value)
            problem = availability_problem(store.registry, setting, {**values, setting.id: value}, hardware)
            if values_equal(current, value):
                guidance = f"{setting.exactLabel} is already {shown}."
            elif setting.id in protected:
                guidance = f"Your current goal keeps {setting.exactLabel} unchanged. To change it, edit it directly or clear the goal first."
            elif setting.id in locked:
                guidance = f"{setting.exactLabel} is locked for assistant changes."
            elif problem:
                guidance = f"{setting.exactLabel} is unavailable. {problem}"
            elif not setting.aiProposable or setting.controlType in ("keybind", "preset", "color"):
                guidance = f"Open {setting.canonicalPath} and set {setting.exactLabel} to {shown}."
                if setting.section == "HUD Edge Positions":
                    guidance += " Select Done in HUD Edge Positions."
                elif setting.applyMode == "explicit":
                    guidance += " Select Apply Changes in the Video menu."
            else:
                recs.append(DraftRecommendation(
                    setting_id=setting.id, proposed_value=str(value), confidence="high",
                    why_for_goal="This restores the value immediately before the last recorded change." if restore else
                    "You requested this exact setting value.",
                ))
                continue
            manual_steps.append(guidance)
            explanations.append(DraftExplanation(setting_id=setting.id, explanation=guidance))
    finally:
        conn.close()

    if recs:
        manual_steps.insert(0, "Check the requested values in Changes before applying.")
    return AssistantDraft(
        intent="recommend" if recs else "navigate",
        reply=" ".join(manual_steps),
        recommendations=recs,
        explanations=explanations,
        navigate_to=explanations[0].setting_id if explanations else next(iter(requested)),
    )
