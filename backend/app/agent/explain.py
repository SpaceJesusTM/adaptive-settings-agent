"""Short, catalogue-grounded answers for common comparisons."""
from __future__ import annotations

import re

from .schemas import AssistantDraft, DraftExplanation

_ASKING = re.compile(r"^\s*(?:what\b|how\b|explain\b|compare\b|is\b)", re.I)


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
    if game == "cs2" and "global shadow" in text and "dynamic shadow" in text:
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
