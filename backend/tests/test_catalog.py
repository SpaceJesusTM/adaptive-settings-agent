"""Catalogue validation: IDs, paths, types, domains, categories, provenance, game separation, duplicates."""
from __future__ import annotations

import copy
import json
from collections import Counter
from pathlib import Path

import pytest

from app.catalog.loader import CatalogError, build_catalog, load_registry, value_in_domain
from app.catalog.schema import RawCatalog

CATALOG_DIR = Path(__file__).resolve().parents[2] / "data" / "catalogs"
WELL_VERIFIED = {"verified-game-files", "verified-official-doc", "verified-official-screenshot"}


@pytest.fixture(scope="module")
def registry():
    return load_registry(CATALOG_DIR)


def labels(registry, game):
    return {s.exactLabel for s in registry.settings(game)}


def test_both_catalogs_load_with_30_plus_well_verified_interactive_settings(registry):
    for game in ("valorant", "cs2"):
        ss = registry.settings(game)
        well = [s for s in ss if s.verificationStatus in WELL_VERIFIED and s.controlType != "preset"]
        assert len(well) >= 30, f"{game}: only {len(well)} well-verified settings"


def test_top_level_tabs_match_current_menus(registry):
    assert [t.label for t in registry.catalog("valorant").menu] == ["General", "Controls", "Crosshair", "Video", "Audio"]
    assert [t.label for t in registry.catalog("cs2").menu] == ["Video", "Audio", "Game", "Keyboard / Mouse", "Crosshair / Scopes"]
    val_video = next(t for t in registry.catalog("valorant").menu if t.id == "video")
    assert [s.label for s in val_video.subtabs] == ["General", "Graphics Quality", "Stats"]
    cs2_video = next(t for t in registry.catalog("cs2").menu if t.id == "video")
    assert [s.label for s in cs2_video.subtabs] == ["Video", "Advanced Video", "HUD Edge Positions"]
    assert cs2_video.applyMode == "explicit"


def test_ids_prefixed_unique_and_games_separated(registry):
    val_ids = {s.id for s in registry.settings("valorant")}
    cs2_ids = {s.id for s in registry.settings("cs2")}
    assert all(i.startswith("val.") for i in val_ids)
    assert all(i.startswith("cs2.") for i in cs2_ids)
    assert not val_ids & cs2_ids
    for game in ("valorant", "cs2"):
        ids = [s.id for s in registry.settings(game)]
        paths = [s.canonicalPath for s in registry.settings(game)]
        assert len(ids) == len(set(ids))
        assert len(paths) == len(set(paths))


def test_every_setting_has_required_provenance_fields(registry):
    for game in ("valorant", "cs2"):
        for s in registry.settings(game):
            assert s.sourceURL.startswith("https://"), s.id
            assert s.sourceDate, s.id
            assert s.verificationStatus, s.id
            assert s.lastReviewed == "2026-11-21", s.id
            assert s.canonicalPath.endswith(s.exactLabel if not s.qualifier else f"({s.qualifier})"), s.id
            assert s.description and s.descriptionSource, s.id
            for ref in s.sourceRefs:
                assert ref in registry.catalog(game).sources


def test_domains_are_consistent(registry):
    for game in ("valorant", "cs2"):
        for s in registry.settings(game):
            if s.controlType in ("dropdown", "segmented"):
                assert s.validOptions and len({o.value for o in s.validOptions}) == len(s.validOptions)
                assert s.min is None and s.max is None
            if s.controlType == "slider":
                assert s.min < s.max and s.step > 0
            if s.controlType != "preset":
                assert value_in_domain(s, s.sampleInitialValue), s.id
            for h in s.goalHints:
                assert all(value_in_domain(s, v) for v in h.prefer), s.id
            if s.controlType == "keybind" or (s.controlType == "slider" and not s.rangeVerified):
                assert not s.aiProposable, s.id


def test_riot_documented_valorant_labels_and_paths(registry):
    val = labels(registry, "valorant")
    for label in ["Material Quality", "Texture Quality", "Detail Quality", "UI Quality", "Improve Clarity",
                  "Experimental Sharpening", "Bloom", "Distortion", "Cast Shadows", "VSync", "Display Mode",
                  "Player Loadouts Always Visible", "Hide User Interface In Game", "Show Map Region Names"]:
        assert label in val, label
    paths = {s.canonicalPath for s in registry.settings("valorant")}
    assert "General > Map > Show Map Region Names" in paths
    assert "Controls > Interface > General > Combat Report" in paths
    assert "Video > Graphics Quality > Material Quality" in paths
    display = registry.setting("valorant", "val.video.display_mode")
    assert "Fullscreen" in {o.label for o in display.validOptions}
    regions = registry.setting("valorant", "val.general.show_map_region_names")
    assert [o.label for o in regions.validOptions] == ["Always", "Only in Buy Phase", "Never"]
    quality = registry.setting("valorant", "val.video.material_quality")
    assert [o.label for o in quality.validOptions] == ["High", "Med", "Low"]


def test_cs2_labels_from_game_files_and_september_2026_crosshair(registry):
    cs2 = labels(registry, "cs2")
    for label in ["Boost Player Contrast", "V-Sync", "NVIDIA Reflex Low Latency", "Multisampling Anti-Aliasing Mode",
                  "Global Shadow Quality", "Dynamic Shadows", "Model / Texture Detail", "Texture Filtering Mode",
                  "Shader Detail", "Particle Detail", "Ambient Occlusion", "High Dynamic Range",
                  "FidelityFX Super Resolution", "Maximum FPS In Game", "Silent Reload Mode", "Dynamic Spread Limit"]:
        assert label in cs2, label
    style = registry.setting("cs2", "cs2.crosshair.xhair_style")
    assert style.verifiedDefault.status == "verified" and style.option_label(style.verifiedDefault.value) == "Dynamic Quadrant"
    assert style.canonicalPath == "Crosshair / Scopes > Style Settings > Style"
    reflex = registry.setting("cs2", "cs2.video.nvidia_reflex")
    assert [o.label for o in reflex.validOptions] == ["Disabled", "Enabled", "Enabled + Boost"]
    assert reflex.availability.requires.gpuVendor == ["NVIDIA"]


def test_no_obsolete_or_removed_settings(registry):
    for game in ("valorant", "cs2"):
        for s in registry.settings(game):
            # CS:GO-era 'Raw Input' toggle and VALORANT's RawInputBuffer (removed in Patch 11.06) must not appear.
            assert "rawinput" not in s.exactLabel.lower().replace(" ", ""), s.id


def test_cs2_preset_matches_video_preset_files(registry):
    preset = registry.setting("cs2", "cs2.video.video_preset")
    assert set(preset.preset.values) == {"0", "1", "2", "3"}
    high = preset.preset.values["2"]
    samples = {s.key: s.sampleInitialValue for s in registry.settings("cs2")}
    assert all(str(samples[k]) == v for k, v in high.items()), "catalogue samples should equal the High preset"


def test_verification_mix_is_reported_honestly(registry):
    val = Counter(s.verificationStatus for s in registry.settings("valorant"))
    assert val["secondary-only"] > 0  # secondary-only items exist and are flagged, not hidden
    for s in registry.settings("valorant"):
        if s.verificationStatus == "secondary-only":
            assert s.sourceRefs and all(registry.catalog("valorant").sources[r].kind == "secondary" for r in s.sourceRefs), s.id
    assert set(Counter(s.verificationStatus for s in registry.settings("cs2"))) == {"verified-game-files"}


def _raw(game: str) -> dict:
    return json.loads((CATALOG_DIR / f"{game}.json").read_text(encoding="utf-8"))


def test_loader_rejects_duplicate_ids():
    data = _raw("cs2")
    section = data["tabs"][0]["subtabs"][0]["sections"][0]
    section["settings"].append(copy.deepcopy(section["settings"][0]))
    with pytest.raises(CatalogError):
        build_catalog(RawCatalog.model_validate(data))


def test_loader_rejects_sample_outside_domain():
    data = _raw("valorant")
    data["tabs"][0]["subtabs"][0]["sections"][2]["settings"][0]["sample"] = "sideways"
    with pytest.raises(CatalogError):
        build_catalog(RawCatalog.model_validate(data))


def test_loader_rejects_unknown_source_and_bad_dependency():
    data = _raw("valorant")
    data["tabs"][0]["subtabs"][0]["sections"][2]["settings"][0]["sources"] = ["made-up-source"]
    with pytest.raises(CatalogError):
        build_catalog(RawCatalog.model_validate(data))
    data = _raw("valorant")
    data["tabs"][0]["subtabs"][0]["sections"][2]["settings"][1]["availability"]["enabledWhen"]["setting"] = "nope"
    with pytest.raises(CatalogError):
        build_catalog(RawCatalog.model_validate(data))


def test_loader_rejects_proposable_keybind():
    data = _raw("cs2")
    kb = data["tabs"][3]["subtabs"][1]["sections"][0]["settings"][0]
    assert kb["control"] == "keybind"
    kb["aiProposable"] = True
    with pytest.raises(CatalogError):
        build_catalog(RawCatalog.model_validate(data))
