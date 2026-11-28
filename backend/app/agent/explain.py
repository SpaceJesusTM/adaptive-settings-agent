"""Short, catalogue-grounded answers for common comparisons."""
from __future__ import annotations

import re

from .schemas import AssistantDraft, DraftExplanation

_ASKING = re.compile(r"^\s*(?:(?:please|also)\s+)*(?:what\b|how\b|explain\b|compare\b|is\b|(?:can|could) you (?:explain|tell me))", re.I)


def _words(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def named_controls(store, game: str, text: str) -> list:
    """Match catalogue labels as whole token sequences, preferring a longer overlapping label."""
    words = " " + _words(text) + " "
    matches = [(s, _words(s.exactLabel)) for s in store.registry.settings(game)]
    found = [(s, label) for s, label in matches if len(label) >= 4 and f" {label} " in words]
    return [s for s, label in found if not any(f" {label} " in f" {other} " and other != label for _, other in found)]


def explanation_target(store, game: str, text: str, focused: str | None = None):
    if not _ASKING.search(text):
        return None
    matched = named_controls(store, game, text)
    if len(matched) == 1:
        return matched[0]
    if not matched and focused and re.search(r"\b(?:this|that) (?:setting|option|control)\b", text, re.I):
        return store.registry.setting(game, focused)
    return None


def comparison_draft(store, game: str, message: str) -> AssistantDraft | None:
    if not _ASKING.search(message) or re.search(r"\b(?:set|enable|disable|change|remember|configure|lock)\b", message, re.I):
        return None
    text = message.lower()
    if ("fps" in text or "frame rate" in text) and ("refresh rate" in text or re.search(r"\b(?:hz|hertz)\b", text)):
        return AssistantDraft(
            intent="explain",
            reply="FPS counts how many frames the game renders per second. Refresh rate, in hertz, counts how many "
                  "times the display can update per second. A 240 Hz monitor can refresh 240 times per second. "
                  "The frame rate the game produces still depends on the scene, hardware and settings.",
        )
    if game == "cs2" and "ambient occlusion" in text and ("cast shadow" in text or "dynamic shadow" in text):
        setting_ids = ["cs2.video.ambient_occlusion", "cs2.video.dynamic_shadows"]
        summary = ("Ambient occlusion adds shading near contacts and in crevices, helping surfaces look less flat. "
                   "Dynamic Shadows determines which light sources make moving objects cast shadows. "
                   "Player shadows can be a visibility cue indoors, while ambient occlusion mainly adds depth and rendering work.")
    elif "texture quality" in text and "anisotropic filtering" in text and game == "valorant":
        setting_ids = ["val.video.texture_quality", "val.video.anisotropic_filtering"]
        summary = ("Texture Quality changes the detail stored in a surface texture. Anisotropic Filtering keeps a texture "
                   "clear when you see it at a steep angle, such as looking along a floor. Filtering can preserve that detail "
                   "on screen, while a higher texture setting supplies more detail to begin with.")
    elif game == "cs2" and "global shadow" in text and "dynamic shadow" in text:
        setting_ids = ["cs2.video.global_shadow_quality", "cs2.video.dynamic_shadows"]
        summary = (
            "Global Shadow Quality adjusts how shadows look. Dynamic Shadows controls which light sources "
            "produce shadows for moving objects such as players. Sun Only can reduce graphics work, "
            "but fewer indoor player shadows can remove a useful visibility cue."
        )
    else:
        return None

    explanations = [
        DraftExplanation(setting_id=s.id, explanation=s.description)
        for sid in setting_ids if (s := store.registry.setting(game, sid))
    ]
    return AssistantDraft(intent="explain", reply=summary, explanations=explanations,
                          navigate_to=explanations[0].setting_id if explanations else None)
