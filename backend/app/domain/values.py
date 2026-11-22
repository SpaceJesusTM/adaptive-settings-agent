"""Value validation, normalisation and availability rules shared by every mutation path.

`normalize_value` is the single gatekeeper used by manual edits, proposal staging, proposal edits and
apply. It accepts an option *value* or its exact visible *label* (case-insensitive) so that model output
such as "Enabled + Boost" or "4x MSAA" resolves to the canonical stored value. In `strict` mode (used
for AI-originated values) slider numbers must already sit on the step grid; in non-strict mode (manual
input) they are snapped.
"""
from __future__ import annotations

import math
import re
from typing import Any, Optional

from ..catalog.loader import CatalogRegistry, coerce_number
from ..catalog.schema import Setting, Value

# Key names accepted for keybinds. The UI captures keys and maps them to these game-style names.
_CS2_NAMED = {
    "TAB", "SPACE", "SHIFT", "RSHIFT", "CTRL", "RCTRL", "ALT", "RALT", "ESCAPE", "ENTER", "BACKSPACE", "CAPSLOCK",
    "INS", "DEL", "HOME", "END", "PGUP", "PGDN", "UPARROW", "DOWNARROW", "LEFTARROW", "RIGHTARROW",
    "MOUSE1", "MOUSE2", "MOUSE3", "MOUSE4", "MOUSE5", "MWHEELUP", "MWHEELDOWN",
    "KP_0", "KP_1", "KP_2", "KP_3", "KP_4", "KP_5", "KP_6", "KP_7", "KP_8", "KP_9", "KP_ENTER",
}
_CS2_NAMED |= {f"F{i}" for i in range(1, 13)}
_CS2_SINGLE = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789`-=[]\\;',./")
_VAL_NAMED = {
    "Left Alt", "Right Alt", "Left Ctrl", "Right Ctrl", "Left Shift", "Right Shift", "Space Bar", "Tab", "Escape",
    "Enter", "Backspace", "Caps Lock", "Insert", "Delete", "Home", "End", "Page Up", "Page Down",
    "Up", "Down", "Left", "Right", "Left Mouse Button", "Right Mouse Button", "Middle Mouse Button",
    "Thumb Mouse Button", "Thumb Mouse Button 2", "Mouse Wheel Up", "Mouse Wheel Down",
}
_VAL_NAMED |= {f"F{i}" for i in range(1, 13)} | {f"Num {i}" for i in range(10)}
_VAL_SINGLE = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789`-=[]\\;',./")


class ValueError_(ValueError):
    """Domain validation error with a user-facing message."""


def allowed_key_names(game: str) -> set[str]:
    if game == "cs2":
        return _CS2_NAMED | _CS2_SINGLE
    return _VAL_NAMED | _VAL_SINGLE


def _decimals(step: float) -> int:
    s = f"{step:.10f}".rstrip("0")
    return len(s.split(".")[1]) if "." in s else 0


def normalize_value(setting: Setting, raw: Any, *, strict: bool) -> Value:
    """Return the canonical stored value or raise ValueError_ with a readable reason."""
    ct = setting.controlType
    if ct in ("dropdown", "segmented", "preset"):
        options = setting.validOptions or []
        if isinstance(raw, bool):
            raise ValueError_(f"'{raw}' is not one of the options for {setting.exactLabel}")
        text = str(raw).strip()
        if isinstance(raw, float) and raw.is_integer():
            text = str(int(raw))
        for o in options:
            if o.value == text:
                return o.value
        for o in options:
            if o.label.lower() == text.lower():
                return o.value
        allowed = ", ".join(o.label for o in options)
        raise ValueError_(f"'{text}' is not a valid option for {setting.exactLabel} (allowed: {allowed})")
    if ct == "slider":
        if isinstance(raw, str) and raw.strip().endswith("%"):
            base = coerce_number(raw.strip()[:-1])
            # "50%" means 0.5 for 0-1 sliders shown as percentages, and 50 for sliders whose unit is "%".
            num = None if base is None else (base / 100.0 if setting.display == "percent" else base)
        else:
            num = coerce_number(raw)
        if num is None or math.isnan(num) or math.isinf(num):
            raise ValueError_(f"'{raw}' is not a number for {setting.exactLabel}")
        lo, hi, step = float(setting.min), float(setting.max), float(setting.step)  # type: ignore[arg-type]
        if num < lo - 1e-9 or num > hi + 1e-9:
            raise ValueError_(f"{num:g} is outside the range {lo:g}-{hi:g} for {setting.exactLabel}")
        steps = round((num - lo) / step)
        snapped = lo + steps * step
        if strict and abs(snapped - num) > max(1e-9, step * 1e-6):
            raise ValueError_(f"{num:g} is not on the {step:g} step grid for {setting.exactLabel}")
        snapped = min(max(snapped, lo), hi)
        dec = setting.precision if setting.precision is not None else _decimals(step)
        snapped = round(snapped, max(dec, _decimals(step)))
        return int(snapped) if float(snapped).is_integer() and _decimals(step) == 0 else snapped
    if ct == "keybind":
        if not isinstance(raw, str):
            raise ValueError_(f"Key binding for {setting.exactLabel} must be a key name")
        key = raw.strip()
        if key == "":
            return ""
        if key not in allowed_key_names(setting.game):
            raise ValueError_(f"'{key}' is not a recognised key name for {setting.game.upper()}")
        return key
    raise ValueError_(f"Unsupported control type {ct}")


def values_equal(a: Any, b: Any) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
        return abs(float(a) - float(b)) < 1e-9
    return str(a) == str(b)


def display_value(setting: Setting, value: Any) -> str:
    if setting.controlType in ("dropdown", "segmented", "preset"):
        return setting.option_label(value) or str(value)
    if setting.controlType == "slider":
        num = coerce_number(value)
        if num is None:
            return str(value)
        if setting.display == "percent":
            return f"{round(num * 100)}%"
        dec = setting.precision if setting.precision is not None else 2
        text = f"{num:.{dec}f}"
        return f"{text} {setting.unit}" if setting.unit and setting.unit != "%" else (f"{text}%" if setting.unit == "%" else text)
    if setting.controlType == "keybind":
        return value or "(unbound)"
    return str(value)


def _condition_met(registry: CatalogRegistry, setting: Setting, cond, values: dict[str, Any]) -> bool:
    target = registry.by_key(setting.game, cond.setting)
    if target is None:
        return False
    current = values.get(target.id)
    return any(values_equal(current, v) for v in cond.values)


def availability_problem(registry: CatalogRegistry, setting: Setting, values: dict[str, Any],
                         hardware: dict[str, Any]) -> Optional[str]:
    """Return a reason string when the setting cannot be changed right now, else None."""
    av = setting.availability
    req = av.requires
    if req is not None:
        if req.gpuVendor is not None and hardware.get("gpuVendor") not in req.gpuVendor:
            vendors = "/".join(req.gpuVendor)
            return f"Not available on this simulated PC (requires a {vendors} GPU; simulated GPU: {hardware.get('gpuVendor', 'unknown')})."
        if req.gsyncDisplay and not hardware.get("gsyncDisplay", False):
            return "Not available on this simulated PC (requires a G-Sync compatible display)."
    if av.visibleWhen is not None and not _condition_met(registry, setting, av.visibleWhen, values):
        return "Hidden by a related setting in this menu."
    if av.enabledWhen is not None and not _condition_met(registry, setting, av.enabledWhen, values):
        parent = registry.by_key(setting.game, av.enabledWhen.setting)
        wanted = ", ".join(display_value(parent, v) for v in av.enabledWhen.values) if parent else "?"
        parent_label = parent.exactLabel if parent else av.enabledWhen.setting
        return f"Disabled until {parent_label} is set to {wanted}."
    return None


_ID_RE = re.compile(r"^(val|cs2)\.[a-z0-9_]+\.[a-z0-9_]+$")


def looks_like_setting_id(text: str) -> bool:
    return bool(_ID_RE.match(text or ""))
