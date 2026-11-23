"""Curated, catalogue-grounded cross-game analogies and verified 360° sensitivity helper.

Every relationship between VALORANT and Counter-Strike 2 controls is anchored to real setting IDs
in data/catalogs/*.json and explicitly classifies semantic equivalence vs. structural differences.
Personal controls (mouse sensitivity, keybindings, custom crosshairs) are NEVER automatically copied
or proposed as silent edits across games.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Literal, Optional

from ..catalog.loader import CatalogRegistry, coerce_number
from ..catalog.schema import DIMENSION_LABELS
from .profile import ProfileService
from .store import Store
from .values import display_value

RelationshipKind = Literal[
    "direct_equivalent",
    "similar_with_differences",
    "loose_analogy",
    "not_directly_comparable",
]

VAL_YAW = 0.07
CS2_YAW = 0.022
VAL_TO_CS2_RATIO = VAL_YAW / CS2_YAW

RELATIONSHIP_LABELS: dict[str, str] = {
    "direct_equivalent": "Direct functional equivalent",
    "similar_with_differences": "Similar function with differences",
    "loose_analogy": "Loose gameplay analogy",
    "not_directly_comparable": "Not directly comparable",
}

CROSS_GAME_MAPPINGS: list[dict[str, Any]] = [
    {
        "id": "push_to_talk",
        "topic": "Team Voice & Push-to-Talk",
        "relationship": "similar_with_differences",
        "keywords": [
            "push to talk", "push-to-talk", "ptt", "mic", "microphone", "voice chat",
            "voice", "comms", "communication key", "same key", "talk",
        ],
        "valorantIds": [
            "val.controls.key_team_ptt",
            "val.controls.key_party_ptt",
            "val.audio.party_voice_activation",
        ],
        "cs2Ids": [
            "cs2.kbmouse.key_mic",
            "cs2.audio.voice_mode",
            "cs2.audio.streamlined_ptt",
        ],
        "personalFactKeys": ["push_to_talk_key", "voice_activation"],
        "summary": (
            "VALORANT separates Team Push-to-Talk and Party Push-to-Talk (with optional Automatic party voice), "
            "whereas CS2 uses a single Use Microphone key combined with Voice/Microphone Mode (Push to Use Mic vs Open Mic)."
        ),
        "differences": (
            "In CS2, if you use Push-to-Talk in external apps or saw audio hitches on key press, Steam also exposes "
            "Streamlined Push To Talk; unlike VALORANT, CS2 does not split Team vs Party voice bindings."
        ),
        "safetyNote": "Keybindings are personal controls — navigate to CS2 Use Microphone and rebind manually if desired.",
        "proposable": False,
    },
    {
        "id": "mouse_sensitivity",
        "topic": "Hipfire Mouse Sensitivity (360° Distance)",
        "relationship": "similar_with_differences",
        "keywords": [
            "sensitivity", "sens", "aim", "dpi", "edpi", "360", "mouse", "cm/360",
            "scoped", "zoom", "ads",
        ],
        "valorantIds": [
            "val.general.sensitivity_aim",
            "val.general.scoped_sensitivity",
        ],
        "cs2Ids": [
            "cs2.kbmouse.mouse_sensitivity",
            "cs2.kbmouse.zoom_sensitivity",
        ],
        "personalFactKeys": ["mouse_sensitivity"],
        "summary": (
            "Both games expose raw yaw-based hipfire sensitivity sliders. Under default yaw scaling "
            "(VALORANT 0.07 deg/count vs CS2 m_yaw 0.022 deg/count), multiplying VALORANT hipfire sensitivity by "
            "0.07 / 0.022 (≈ 3.1818) matches physical mouse distance for a 360° turn."
        ),
        "differences": (
            "Physical 360° match does NOT mean identical visual feel: default 16:9 horizontal FOV differs "
            "(103° in VALORANT vs ~106.26° in CS2), and weapon ADS vs CS2 AWP/Scout zoom multipliers scale differently."
        ),
        "safetyNote": "Mouse sensitivity is never auto-applied or AI-proposed. Enter your confirmed source sensitivity to calculate a starting point, then adjust in menu.",
        "proposable": False,
    },
    {
        "id": "utilities_and_abilities",
        "topic": "Abilities (VALORANT) vs. Grenades & Utility (CS2)",
        "relationship": "loose_analogy",
        "keywords": [
            "ability", "abilities", "grenade", "grenades", "utility", "flash", "flashbang",
            "smoke", "molotov", "molly", "incendiary", "he", "ultimate", "signature", "nade",
        ],
        "valorantIds": [
            "val.controls.key_ability_1",
            "val.controls.key_ability_2",
            "val.controls.key_ability_3",
            "val.controls.key_ultimate",
        ],
        "cs2Ids": [
            "cs2.kbmouse.key_flashbang",
            "cs2.kbmouse.key_smoke",
            "cs2.kbmouse.key_he_grenade",
            "cs2.kbmouse.key_molotov",
        ],
        "personalFactKeys": ["utility_key_habit"],
        "summary": (
            "VALORANT maps 3 agent abilities plus an Ultimate onto Q/E/C/X, while CS2 separates individual "
            "purchasable grenade slots (Flashbang, Smoke Grenade, HE Grenade, Molotov / Incendiary)."
        ),
        "differences": (
            "Mechanics and counts do not align 1:1 (every CS2 player can hold multiple grenade classes, and there is no "
            "agent Ultimate slot). Also note CS2 default F is Inspect Weapon while E is Use; in VALORANT F is Use Object."
        ),
        "safetyNote": "Do not blindly copy keybinds across games — map only the grenade binds whose ergonomics match your hand comfort.",
        "proposable": False,
    },
    {
        "id": "movement_and_use_keys",
        "topic": "Walk, Crouch, Drop, Ping & Use Keys",
        "relationship": "similar_with_differences",
        "keywords": [
            "walk", "crouch", "duck", "jump", "ping", "use", "inspect", "drop", "reload",
            "interact", "defuse", "plant", "keybind", "keybinds", "controls", "binds",
        ],
        "valorantIds": [
            "val.controls.key_walk",
            "val.controls.key_crouch",
            "val.controls.key_use_object",
            "val.controls.key_ping",
            "val.controls.key_drop",
            "val.controls.key_inspect",
        ],
        "cs2Ids": [
            "cs2.kbmouse.key_walk",
            "cs2.kbmouse.key_duck",
            "cs2.kbmouse.key_use",
            "cs2.kbmouse.key_player_ping",
            "cs2.kbmouse.key_drop",
            "cs2.kbmouse.key_inspect",
        ],
        "personalFactKeys": ["ping_key", "crouch_walk_convention"],
        "summary": (
            "Core WASD/Walk/Drop keys mirror cleanly across games, while Use and Inspect swap defaults: "
            "VALORANT uses F for Use Object and Y for Inspect, whereas CS2 defaults E to Use and F to Inspect Weapon."
        ),
        "differences": (
            "Also check Duck Mode / Walk Mode (Hold vs Toggle) in CS2 Keyboard & Mouse Settings if you rely on hold-to-walk "
            "precision, and rebind Player Ping intentionally if you are accustomed to Z in VALORANT (CS2 defaults MOUSE3)."
        ),
        "safetyNote": "Personal movement and communication keybindings must always be set directly in the menu.",
        "proposable": False,
    },
    {
        "id": "crosshair_traits",
        "topic": "Crosshair Characteristics",
        "relationship": "similar_with_differences",
        "keywords": [
            "crosshair", "reticle", "dot", "outline", "outlines", "center dot",
            "static", "gap", "thickness", "color",
        ],
        "valorantIds": [
            "val.crosshair.primary_color",
            "val.crosshair.primary_outlines",
            "val.crosshair.primary_center_dot",
            "val.crosshair.primary_inner_length",
            "val.crosshair.primary_inner_thickness",
        ],
        "cs2Ids": [
            "cs2.crosshair.xhair_color_hex",
            "cs2.crosshair.xhair_style",
            "cs2.crosshair.xhair_outline",
            "cs2.crosshair.xhair_center_dot",
            "cs2.crosshair.xhair_length",
            "cs2.crosshair.xhair_thickness",
        ],
        "personalFactKeys": ["crosshair_style"],
        "summary": (
            "Both games support static vs. dynamic behavior, outlines, center dot, color, thickness, and line length, "
            "letting you match overall visual traits (e.g., high-contrast cyan static crosshair with outlines)."
        ),
        "differences": (
            "Crosshair units, resolutions, and spread/recoil rendering differ between engines, so numerical length/thickness "
            "and share codes cannot be converted into a pixel-identical reticle."
        ),
        "safetyNote": "Visual personal preferences — preview and tweak directly in each game's crosshair controls.",
        "proposable": False,
    },
    {
        "id": "frame_pacing_latency",
        "topic": "V-Sync, NVIDIA Reflex & Display Mode",
        "relationship": "direct_equivalent",
        "keywords": [
            "vsync", "v-sync", "reflex", "nvidia reflex", "input latency", "input lag",
            "display mode", "fullscreen", "frame pacing", "tearing", "fps", "latency",
        ],
        "valorantIds": [
            "val.video.vsync",
            "val.video.nvidia_reflex",
            "val.video.display_mode",
        ],
        "cs2Ids": [
            "cs2.video.vsync",
            "cs2.video.nvidia_reflex",
            "cs2.video.display_mode",
        ],
        "personalFactKeys": [],
        "summary": (
            "Exclusive Fullscreen, V-Sync Off, and NVIDIA Reflex (Enabled / Enabled + Boost) play the same role in both "
            "titles when prioritizing low display/render input latency."
        ),
        "differences": (
            "CS2 queues Video changes behind an explicit Apply Changes step inside Advanced Video, while VALORANT saves Video options immediately."
        ),
        "safetyNote": "Only applicable when your priorities support low latency or performance (requires NVIDIA GPU for Reflex).",
        "proposable": True,
    },
    {
        "id": "player_visibility_clarity",
        "topic": "Enemy Visibility & Contrast Controls",
        "relationship": "similar_with_differences",
        "keywords": [
            "visibility", "clarity", "contrast", "boost player contrast", "enemy highlight",
            "vignette", "bloom", "see enemies", "spot enemies",
        ],
        "valorantIds": [
            "val.general.enemy_highlight_color",
            "val.video.vignette",
            "val.video.bloom",
            "val.video.improve_clarity",
        ],
        "cs2Ids": [
            "cs2.video.boost_player_contrast",
            "cs2.game.player_colors",
        ],
        "personalFactKeys": [],
        "summary": (
            "VALORANT relies on Enemy Highlight Color plus turning off distracting post-processing (Vignette, Bloom), "
            "while CS2 highlights silhouettes at range primarily via Boost Player Contrast."
        ),
        "differences": (
            "CS2's Show Player Colors in Competitive colors teammates on the radar rather than rendering enemy outlines."
        ),
        "safetyNote": "Abstract visibility priority transfers cleanly across games without assuming identical post-processing controls.",
        "proposable": True,
    },
    {
        "id": "positional_audio",
        "topic": "Positional Audio & Footstep Cues",
        "relationship": "similar_with_differences",
        "keywords": [
            "audio", "hrtf", "footsteps", "eq", "perspective", "headphone", "positional", "sound",
        ],
        "valorantIds": [
            "val.audio.enable_hrtf",
            "val.audio.speaker_configuration",
            "val.audio.voip_ducks_music",
        ],
        "cs2Ids": [
            "cs2.audio.eq_profile",
            "cs2.audio.perspective_correction",
            "cs2.audio.mute_mvp_music",
        ],
        "personalFactKeys": [],
        "summary": (
            "VALORANT's Enable HRTF (with Stereo speakers) and CS2's Perspective Correction + Crisp EQ Profile serve the "
            "same spatial footstep clarity goal."
        ),
        "differences": (
            "CS2 provides headphone EQ profiles (Natural / Crisp / Smooth) directly in audio settings rather than a single HRTF toggle."
        ),
        "safetyNote": "Different audio engines — test both in practice matches with headphones.",
        "proposable": True,
    },
]


def validate_cross_game_mappings(registry: CatalogRegistry) -> list[str]:
    """Return any catalog ID errors across CROSS_GAME_MAPPINGS (empty when valid)."""
    errors: list[str] = []
    for m in CROSS_GAME_MAPPINGS:
        for sid in m["valorantIds"]:
            if registry.setting("valorant", sid) is None:
                errors.append(f"{m['id']}: unknown valorant settingId '{sid}'")
        for sid in m["cs2Ids"]:
            if registry.setting("cs2", sid) is None:
                errors.append(f"{m['id']}: unknown cs2 settingId '{sid}'")
    return errors


def convert_hipfire_sensitivity(
    source_game: str,
    target_game: str,
    source_value: Any,
    *,
    confirmed: bool = True,
) -> dict[str, Any]:
    """Convert hipfire sensitivity along a verified 360-degree yaw ratio with explicit caveats."""
    num = coerce_number(source_value)
    if num is None or num <= 0:
        return {
            "convertible": False,
            "sourceGame": source_game,
            "targetGame": target_game,
            "reason": "Need a positive source hipfire sensitivity number (plus matching mouse DPI) before calculating a 360° starting point.",
            "assumptions": [
                "Mouse DPI stays identical across both games.",
                "CS2 m_yaw remains at its default 0.022 and OS pointer acceleration is off.",
            ],
            "caveats": [
                "Even with matching physical 360° distance, perceived aim feel differs slightly because 16:9 FOV differs (VALORANT 103° vs CS2 ~106.26°) and scoped multipliers scale differently.",
            ],
        }
    if source_game == "valorant" and target_game == "cs2":
        if not (0.05 <= num <= 5.0):
            return {
                "convertible": False,
                "sourceGame": source_game,
                "targetGame": target_game,
                "reason": f"VALORANT sensitivity {num:g} is outside the expected 0.05–5.0 range; please double-check your source value first.",
                "assumptions": [],
                "caveats": [],
            }
        converted = round(num * VAL_TO_CS2_RATIO, 2)
        formula = f"{num:g} × (0.07 / 0.022) ≈ {converted:.2f}"
    elif source_game == "cs2" and target_game == "valorant":
        if not (0.1 <= num <= 8.0):
            return {
                "convertible": False,
                "sourceGame": source_game,
                "targetGame": target_game,
                "reason": f"CS2 sensitivity {num:g} is outside the expected 0.1–8.0 range; please double-check your source value first.",
                "assumptions": [],
                "caveats": [],
            }
        converted = round(num / VAL_TO_CS2_RATIO, 3)
        formula = f"{num:g} × (0.022 / 0.07) ≈ {converted:.3f}"
    else:
        return {
            "convertible": False,
            "sourceGame": source_game,
            "targetGame": target_game,
            "reason": "Choose distinct source and target games (VALORANT ↔ CS2).",
            "assumptions": [],
            "caveats": [],
        }

    return {
        "convertible": True,
        "confirmed": confirmed,
        "sourceGame": source_game,
        "targetGame": target_game,
        "sourceValue": round(num, 3),
        "convertedValue": converted,
        "formula": formula,
        "assumptions": [
            "Assumes identical mouse DPI/polling rate between games.",
            "Assumes CS2 default m_yaw = 0.022 and Raw Input / no OS mouse acceleration.",
        ],
        "caveats": [
            "Matches physical 360° hipfire turn distance — NOT identical screen-space speed because horizontal FOV differs (VALORANT 103° vs CS2 ~106.26° at 16:9).",
            "ADS / scoped sniper multipliers are separate and cannot be copied 1:1 with this ratio.",
        ],
    }


def _setting_snapshot(store: Store, vals: dict[str, Any], game: str, setting_id: str) -> Optional[dict[str, Any]]:
    s = store.registry.setting(game, setting_id)
    if s is None:
        return None
    cur = vals.get(setting_id)
    return {
        "settingId": s.id,
        "game": game,
        "label": s.exactLabel,
        "path": s.canonicalPath,
        "controlType": s.controlType,
        "aiProposable": s.aiProposable,
        "currentValue": cur,
        "currentDisplay": display_value(s, cur),
    }


def compare_cross_game(
    store: Store,
    profile: ProfileService,
    conn: sqlite3.Connection,
    *,
    query: str,
    current_game: str,
    source_sensitivity: Optional[float] = None,
) -> dict[str, Any]:
    """Find grounded cross-game analogies for a query across BOTH VALORANT and CS2 catalogues."""
    q = (query or "").lower()
    other_game = "valorant" if current_game == "cs2" else "cs2"
    val_vals = store.flat_values(conn, "valorant")
    cs2_vals = store.flat_values(conn, "cs2")
    facts = profile.personal_facts(conn)
    facts_by_key = {(f["factKey"], f.get("originGame")): f for f in facts}
    prefs = [p for p in profile.preferences(conn) if p["scope"] == "durable"]

    scored: list[tuple[int, dict[str, Any]]] = []
    broad_transfer = any(
        k in q for k in (
            "carry over", "what should i change based on", "move my settings", "new to cs2",
            "new to valorant", "similarities", "setup carry", "from valorant to cs2",
            "from cs2 to valorant",
        )
    )
    for m in CROSS_GAME_MAPPINGS:
        hits = sum(2 if " " in kw else 1 for kw in m["keywords"] if kw in q)
        if hits > 0 or (broad_transfer and m["id"] in ("push_to_talk", "mouse_sensitivity", "frame_pacing_latency")):
            scored.append((max(1, hits), m))
    scored.sort(key=lambda t: -t[0])

    if not scored:
        return {
            "matched": False,
            "currentGame": current_game,
            "otherGame": other_game,
            "comparisons": [],
            "durablePriorities": [
                {"dimension": p["dimension"], "label": DIMENSION_LABELS.get(p["dimension"], p["dimension"]), "originGame": p.get("originGame")}
                for p in prefs
            ],
            "note": (
                "No direct curated analogy matched that request across VALORANT and CS2. "
                "Ask about push-to-talk, mouse sensitivity, abilities vs. grenades, movement/use keys, crosshairs, or V-Sync/Reflex/contrast/audio."
            ),
        }

    comparisons: list[dict[str, Any]] = []
    for _, m in scored[:3]:
        val_settings = [x for sid in m["valorantIds"] if (x := _setting_snapshot(store, val_vals, "valorant", sid))]
        cs2_settings = [x for sid in m["cs2Ids"] if (x := _setting_snapshot(store, cs2_vals, "cs2", sid))]
        matching_facts = []
        for fk in m.get("personalFactKeys", []):
            f = facts_by_key.get((fk, other_game)) or facts_by_key.get((fk, None))
            if f:
                matching_facts.append(f)

        item: dict[str, Any] = {
            "id": m["id"],
            "topic": m["topic"],
            "relationship": m["relationship"],
            "relationshipLabel": RELATIONSHIP_LABELS[m["relationship"]],
            "summary": m["summary"],
            "differences": m["differences"],
            "safetyNote": m["safetyNote"],
            "proposable": m["proposable"],
            "valorantSettings": val_settings,
            "cs2Settings": cs2_settings,
            "confirmedFacts": matching_facts,
            "targetNavigateId": (cs2_settings[0]["settingId"] if current_game == "cs2" and cs2_settings else (val_settings[0]["settingId"] if val_settings else None)),
        }

        if m["id"] == "mouse_sensitivity":
            if source_sensitivity is not None:
                item["sensitivityConversion"] = convert_hipfire_sensitivity(
                    other_game, current_game, source_sensitivity, confirmed=True
                )
            elif matching_facts:
                item["sensitivityConversion"] = convert_hipfire_sensitivity(
                    other_game, current_game, matching_facts[0]["valueText"], confirmed=True
                )
            else:
                item["sensitivityConversion"] = {
                    "convertible": False,
                    "sourceGame": other_game,
                    "targetGame": current_game,
                    "reason": (
                        f"You have not confirmed your {other_game.upper()} sensitivity in this profile yet. "
                        f"Share your exact in-game {other_game.upper()} sensitivity (or save it in My Priorities → Personal setup preferences) "
                        "to calculate a starting 360° value rather than guessing from placeholder defaults."
                    ),
                    "assumptions": [
                        "Same mouse DPI across both games and CS2 default m_yaw = 0.022.",
                    ],
                    "caveats": [
                        "Matches physical 360° hipfire rotation rather than identical FOV/ADS feel.",
                    ],
                }
        comparisons.append(item)

    return {
        "matched": True,
        "currentGame": current_game,
        "otherGame": other_game,
        "comparisons": comparisons,
        "durablePriorities": [
            {"dimension": p["dimension"], "label": DIMENSION_LABELS.get(p["dimension"], p["dimension"]), "originGame": p.get("originGame")}
            for p in prefs
        ],
    }
