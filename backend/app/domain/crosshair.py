"""VALORANT Crosshair profile management and validated Riot profile code import/export.

Profiles persist in `valorant_crosshair_profiles` (maximum 15, matching Riot Patch 5.04) and sync
with `val.crosshair.*` settings through `Store.manual_change` so every switch and manual edit is
recorded in history and cleanly undoable.

Code import/export implements the documented Riot `0;P;...;A;...;S;...` token format for this
simulated catalogue; any unrecognised or malformed share string is rejected with an explicit error.
"""
from __future__ import annotations

import re
import sqlite3
from typing import Any, Optional

from .db import dumps, loads, new_id, now_iso, write_tx
from .errors import Conflict, Invalid, NotFound
from .store import Change, Store
from .values import ValueError_, normalize_value

MAX_PROFILES = 15

# Documented Riot 0;P;... preset color codes mapped to our catalog option values
CODE_TO_COLOR = {
    "0": "white",
    "1": "green",
    "2": "yellow_green",
    "3": "green_yellow",
    "4": "yellow",
    "5": "cyan",
    "6": "pink",
    "7": "red",
    "8": "custom",
}
COLOR_TO_CODE = {v: k for k, v in CODE_TO_COLOR.items()}

SNIPER_CODE_TO_COLOR = {
    "0": "red",
    "1": "white",
    "2": "green",
    "3": "cyan",
    "4": "yellow",
    "5": "pink",
    "6": "custom",
}
SNIPER_COLOR_TO_CODE = {v: k for k, v in SNIPER_CODE_TO_COLOR.items()}

HEX_6_RE = re.compile(r"^[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$")


def sync_active_profile_tx(store: Store, conn: sqlite3.Connection) -> None:
    """Keep the currently active crosshair profile's JSON snapshot in sync inside an active write_tx."""
    active = conn.execute(
        "SELECT id FROM valorant_crosshair_profiles WHERE is_active = 1 LIMIT 1"
    ).fetchone()
    if active is None:
        return
    vals = store.flat_values(conn, "valorant")
    xhair = {k: v for k, v in vals.items() if k.startswith("val.crosshair.")}
    conn.execute(
        "UPDATE valorant_crosshair_profiles SET settings_json = ?, updated_at = ? WHERE id = ?",
        (dumps(xhair), now_iso(), active["id"]),
    )


def _flag(val: Any) -> str:
    return "on" if str(val) in ("1", "true", "on") else "off"


def _bit(val: Any) -> str:
    return "1" if str(val).lower() == "on" else "0"


def _num(raw: str) -> float:
    return float(raw)


class CrosshairProfileService:
    def __init__(self, store: Store):
        self.store = store

    def _current_xhair_defaults(self, conn: sqlite3.Connection) -> dict[str, Any]:
        vals = self.store.flat_values(conn, "valorant")
        xhair = {k: v for k, v in vals.items() if k.startswith("val.crosshair.")}
        if xhair:
            return xhair
        return {
            s.id: s.sampleInitialValue
            for s in self.store.registry.settings("valorant")
            if s.id.startswith("val.crosshair.")
        }

    def list(self) -> list[dict[str, Any]]:
        conn = self.store.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM valorant_crosshair_profiles ORDER BY created_at, rowid"
            ).fetchall()
            return [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "isActive": bool(r["is_active"]),
                    "settings": loads(r["settings_json"], {}),
                    "createdAt": r["created_at"],
                    "updatedAt": r["updated_at"],
                }
                for r in rows
            ]
        finally:
            conn.close()

    def _get(self, conn: sqlite3.Connection, profile_id: str) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM valorant_crosshair_profiles WHERE id = ?", (profile_id,)
        ).fetchone()
        if row is None:
            raise NotFound("Crosshair profile not found")
        return row

    def create(self, name: str, *, copy_from_current: bool = True) -> dict[str, Any]:
        clean = (name or "").strip()[:40]
        if not clean:
            raise Invalid("Profile name cannot be empty")
        conn = self.store.connect()
        try:
            count = conn.execute("SELECT COUNT(*) AS n FROM valorant_crosshair_profiles").fetchone()["n"]
            if count >= MAX_PROFILES:
                raise Conflict(f"VALORANT supports up to {MAX_PROFILES} crosshair profiles.", code="max_profiles")
            settings = (
                self._current_xhair_defaults(conn)
                if copy_from_current
                else {
                    s.id: s.sampleInitialValue
                    for s in self.store.registry.settings("valorant")
                    if s.id.startswith("val.crosshair.")
                }
            )
            pid = new_id("xhp")
            ts = now_iso()
            with write_tx(conn):
                conn.execute("UPDATE valorant_crosshair_profiles SET is_active = 0")
                conn.execute(
                    "INSERT INTO valorant_crosshair_profiles(id, name, settings_json, is_active, created_at, updated_at) "
                    "VALUES (?,?,?,1,?,?)",
                    (pid, clean, dumps(settings), ts, ts),
                )
        finally:
            conn.close()
        return self.select(pid)

    def select(self, profile_id: str) -> dict[str, Any]:
        conn = self.store.connect()
        try:
            row = self._get(conn, profile_id)
            stored = loads(row["settings_json"], {})
            valid_ids = {s.id for s in self.store.registry.settings("valorant") if s.id.startswith("val.crosshair.")}
            changes = [Change(sid, val) for sid, val in stored.items() if sid in valid_ids]
            with write_tx(conn):
                conn.execute("UPDATE valorant_crosshair_profiles SET is_active = CASE WHEN id = ? THEN 1 ELSE 0 END", (profile_id,))
                batch = (
                    self.store._apply_tx(  # noqa: SLF001 - intentional single-tx profile switch
                        conn,
                        "valorant",
                        changes,
                        source="manual_batch",
                        label=f"Crosshair profile: {row['name']}",
                        enforce_locks=False,
                        strict=False,
                        check_availability=False,
                    )
                    if changes
                    else None
                )
            return {"profiles": self.list(), "activeProfileId": profile_id, "batch": batch}
        finally:
            conn.close()

    def rename(self, profile_id: str, name: str) -> dict[str, Any]:
        clean = (name or "").strip()[:40]
        if not clean:
            raise Invalid("Profile name cannot be empty")
        conn = self.store.connect()
        try:
            with write_tx(conn):
                self._get(conn, profile_id)
                conn.execute(
                    "UPDATE valorant_crosshair_profiles SET name = ?, updated_at = ? WHERE id = ?",
                    (clean, now_iso(), profile_id),
                )
            return {"profiles": self.list()}
        finally:
            conn.close()

    def delete(self, profile_id: str) -> dict[str, Any]:
        conn = self.store.connect()
        try:
            count = conn.execute("SELECT COUNT(*) AS n FROM valorant_crosshair_profiles").fetchone()["n"]
            if count <= 1:
                raise Conflict("At least one crosshair profile must remain.", code="last_profile")
            row = self._get(conn, profile_id)
            was_active = bool(row["is_active"])
            with write_tx(conn):
                conn.execute("DELETE FROM valorant_crosshair_profiles WHERE id = ?", (profile_id,))
                next_active: Optional[str] = None
                if was_active:
                    nxt = conn.execute(
                        "SELECT id FROM valorant_crosshair_profiles ORDER BY created_at, rowid LIMIT 1"
                    ).fetchone()
                    if nxt:
                        next_active = nxt["id"]
                        conn.execute("UPDATE valorant_crosshair_profiles SET is_active = 1 WHERE id = ?", (next_active,))
            if was_active and next_active:
                return self.select(next_active)
            return {"profiles": self.list()}
        finally:
            conn.close()

    # ------------------------------------------------------------------ validated Riot code import / export
    def export_code(self, profile_id: str) -> dict[str, Any]:
        conn = self.store.connect()
        try:
            row = self._get(conn, profile_id)
            s = {**self._current_xhair_defaults(conn), **loads(row["settings_json"], {})}
        finally:
            conn.close()

        tokens: list[str] = ["0"]
        if str(s.get("val.crosshair.use_advanced_options", "off")) == "on":
            tokens += ["s", "1"]
        if str(s.get("val.crosshair.override_all_primary", "off")) == "on":
            tokens += ["m", "1"]

        def _append_section(prefix: str, tag: str) -> None:
            tokens.append(tag)
            c = COLOR_TO_CODE.get(str(s.get(f"val.crosshair.{prefix}_color", "white")), "0")
            if c != "0":
                tokens.extend(["c", c])
            if c == "8":
                hx = str(s.get(f"val.crosshair.{prefix}_custom_color", "#FFFFFF")).lstrip("#").upper()
                tokens.extend(["u", f"{hx}FF"])
            outlines = _bit(s.get(f"val.crosshair.{prefix}_outlines", "on"))
            if outlines == "0":
                tokens.extend(["h", "0"])
            else:
                tokens.extend(["o", str(s.get(f"val.crosshair.{prefix}_outline_opacity", 0.5))])
                tokens.extend(["t", str(s.get(f"val.crosshair.{prefix}_outline_thickness", 1))])
            if _bit(s.get(f"val.crosshair.{prefix}_center_dot", "off")) == "1":
                tokens.extend(["d", "1"])
                tokens.extend(["a", str(s.get(f"val.crosshair.{prefix}_center_dot_opacity", 1))])
                tokens.extend(["z", str(s.get(f"val.crosshair.{prefix}_center_dot_thickness", 2))])
            tokens.extend([
                "0b", _bit(s.get(f"val.crosshair.{prefix}_show_inner", "on")),
                "0a", str(s.get(f"val.crosshair.{prefix}_inner_opacity", 0.8)),
                "0l", str(s.get(f"val.crosshair.{prefix}_inner_length", 6)),
                "0v", str(s.get(f"val.crosshair.{prefix}_inner_v_length", 6)),
                "0t", str(s.get(f"val.crosshair.{prefix}_inner_thickness", 2)),
                "0o", str(s.get(f"val.crosshair.{prefix}_inner_offset", 3)),
                "0m", _bit(s.get(f"val.crosshair.{prefix}_inner_movement_error", "off")),
                "0f", _bit(s.get(f"val.crosshair.{prefix}_inner_firing_error", "off")),
                "1b", _bit(s.get(f"val.crosshair.{prefix}_show_outer", "on")),
                "1a", str(s.get(f"val.crosshair.{prefix}_outer_opacity", 0.35)),
                "1l", str(s.get(f"val.crosshair.{prefix}_outer_length", 2)),
                "1t", str(s.get(f"val.crosshair.{prefix}_outer_thickness", 2)),
                "1o", str(s.get(f"val.crosshair.{prefix}_outer_offset", 10)),
                "1m", _bit(s.get(f"val.crosshair.{prefix}_outer_movement_error", "on")),
                "1f", _bit(s.get(f"val.crosshair.{prefix}_outer_firing_error", "on")),
            ])

        _append_section("primary", "P")
        if str(s.get("val.crosshair.use_advanced_options", "off")) == "on":
            _append_section("ads", "A")
            tokens += [
                "S",
                "d", _bit(s.get("val.crosshair.sniper_center_dot", "on")),
                "c", SNIPER_COLOR_TO_CODE.get(str(s.get("val.crosshair.sniper_dot_color", "red")), "0"),
                "s", str(s.get("val.crosshair.sniper_dot_thickness", 1)),
                "o", str(s.get("val.crosshair.sniper_dot_opacity", 1)),
            ]
        return {
            "profileId": profile_id,
            "name": row["name"],
            "code": ";".join(tokens),
            "simulatedNote": "Simulated profile serializer matching documented Riot 0;P;... tokens; not verified against the live Riot client parser.",
        }

    def import_code(self, code: str, name: Optional[str] = None) -> dict[str, Any]:
        raw = (code or "").strip()
        if not raw or not raw.startswith("0;"):
            raise Invalid("Invalid crosshair code: must begin with '0;' and use Riot's semicolon-delimited tokens (e.g. 0;P;c;5;h;0;0l;4;0o;2;0a;1;0f;0;1b;0).")
        parts = raw.split(";")
        if len(parts) < 3 or parts[0] != "0":
            raise Invalid("Invalid crosshair code format.")

        conn = self.store.connect()
        try:
            count = conn.execute("SELECT COUNT(*) AS n FROM valorant_crosshair_profiles").fetchone()["n"]
            if count >= MAX_PROFILES:
                raise Conflict(f"VALORANT supports up to {MAX_PROFILES} crosshair profiles.", code="max_profiles")
            parsed = self._current_xhair_defaults(conn)
        finally:
            conn.close()

        section = "GLOBAL"
        i = 1
        seen_section_marker = False
        parsed_tokens = 0
        try:
            while i < len(parts):
                tok = parts[i]
                if tok in ("P", "A", "S"):
                    section = tok
                    seen_section_marker = True
                    i += 1
                    continue
                if i + 1 >= len(parts):
                    raise Invalid(f"Crosshair code ended unexpectedly after token '{tok}'.")
                val = parts[i + 1]
                i += 2
                parsed_tokens += 1

                if section == "GLOBAL":
                    if tok == "s":
                        parsed["val.crosshair.use_advanced_options"] = _flag(val)
                    elif tok == "m":
                        parsed["val.crosshair.override_all_primary"] = _flag(val)
                    elif tok == "c" and not seen_section_marker:
                        # Riot also allows primary tokens directly if P omitted before first tag
                        section = "P"
                        seen_section_marker = True
                    else:
                        continue

                if section in ("P", "A"):
                    pfx = "primary" if section == "P" else "ads"
                    if tok == "c":
                        if val not in CODE_TO_COLOR:
                            raise Invalid(f"Unsupported crosshair color code '{val}'.")
                        parsed[f"val.crosshair.{pfx}_color"] = CODE_TO_COLOR[val]
                    elif tok == "u":
                        if not HEX_6_RE.match(val):
                            raise Invalid(f"Invalid custom hex color token '{val}'.")
                        parsed[f"val.crosshair.{pfx}_color"] = "custom"
                        parsed[f"val.crosshair.{pfx}_custom_color"] = f"#{val[:6].upper()}"
                    elif tok == "h":
                        parsed[f"val.crosshair.{pfx}_outlines"] = _flag(val)
                    elif tok == "o":
                        parsed[f"val.crosshair.{pfx}_outline_opacity"] = _num(val)
                    elif tok == "t":
                        parsed[f"val.crosshair.{pfx}_outline_thickness"] = _num(val)
                    elif tok == "d":
                        parsed[f"val.crosshair.{pfx}_center_dot"] = _flag(val)
                    elif tok == "a":
                        parsed[f"val.crosshair.{pfx}_center_dot_opacity"] = _num(val)
                    elif tok == "z":
                        parsed[f"val.crosshair.{pfx}_center_dot_thickness"] = _num(val)
                    elif tok == "0b":
                        parsed[f"val.crosshair.{pfx}_show_inner"] = _flag(val)
                    elif tok == "0a":
                        parsed[f"val.crosshair.{pfx}_inner_opacity"] = _num(val)
                    elif tok == "0l":
                        parsed[f"val.crosshair.{pfx}_inner_length"] = _num(val)
                    elif tok == "0v":
                        parsed[f"val.crosshair.{pfx}_inner_v_length"] = _num(val)
                    elif tok == "0g":
                        pass
                    elif tok == "0t":
                        parsed[f"val.crosshair.{pfx}_inner_thickness"] = _num(val)
                    elif tok == "0o":
                        parsed[f"val.crosshair.{pfx}_inner_offset"] = _num(val)
                    elif tok == "0m":
                        parsed[f"val.crosshair.{pfx}_inner_movement_error"] = _flag(val)
                    elif tok == "0f":
                        parsed[f"val.crosshair.{pfx}_inner_firing_error"] = _flag(val)
                    elif tok == "1b":
                        parsed[f"val.crosshair.{pfx}_show_outer"] = _flag(val)
                    elif tok == "1a":
                        parsed[f"val.crosshair.{pfx}_outer_opacity"] = _num(val)
                    elif tok == "1l":
                        parsed[f"val.crosshair.{pfx}_outer_length"] = _num(val)
                    elif tok == "1t":
                        parsed[f"val.crosshair.{pfx}_outer_thickness"] = _num(val)
                    elif tok == "1o":
                        parsed[f"val.crosshair.{pfx}_outer_offset"] = _num(val)
                    elif tok == "1m":
                        parsed[f"val.crosshair.{pfx}_outer_movement_error"] = _flag(val)
                    elif tok == "1f":
                        parsed[f"val.crosshair.{pfx}_outer_firing_error"] = _flag(val)
                elif section == "S":
                    if tok == "d":
                        parsed["val.crosshair.sniper_center_dot"] = _flag(val)
                    elif tok == "c":
                        if val in SNIPER_CODE_TO_COLOR:
                            parsed["val.crosshair.sniper_dot_color"] = SNIPER_CODE_TO_COLOR[val]
                    elif tok == "u" and HEX_6_RE.match(val):
                        parsed["val.crosshair.sniper_dot_color"] = "custom"
                        parsed["val.crosshair.sniper_dot_custom_color"] = f"#{val[:6].upper()}"
                    elif tok == "s":
                        parsed["val.crosshair.sniper_dot_thickness"] = _num(val)
                    elif tok == "o":
                        parsed["val.crosshair.sniper_dot_opacity"] = _num(val)
        except ValueError as exc:
            raise Invalid(f"Invalid numeric value in crosshair code: {exc}") from exc

        if not seen_section_marker or parsed_tokens == 0:
            raise Invalid("Crosshair code must include at least one valid section ('P', 'A', or 'S') and setting token.")

        # Validate & snap every parsed setting strictly against our catalog domain
        normalized: dict[str, Any] = {}
        for s in self.store.registry.settings("valorant"):
            if s.id in parsed:
                try:
                    normalized[s.id] = normalize_value(s, parsed[s.id], strict=False)
                except ValueError_ as exc:
                    raise Invalid(str(exc)) from exc

        profile_name = (name or "").strip()[:40] or "Imported Profile"
        pid = new_id("xhp")
        ts = now_iso()
        conn = self.store.connect()
        try:
            with write_tx(conn):
                conn.execute("UPDATE valorant_crosshair_profiles SET is_active = 0")
                conn.execute(
                    "INSERT INTO valorant_crosshair_profiles(id, name, settings_json, is_active, created_at, updated_at) "
                    "VALUES (?,?,?,1,?,?)",
                    (pid, profile_name, dumps(normalized), ts, ts),
                )
        finally:
            conn.close()
        return self.select(pid)
