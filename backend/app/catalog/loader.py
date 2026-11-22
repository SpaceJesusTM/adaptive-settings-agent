"""Load, flatten and integrity-check the canonical catalogues.

Integrity rules enforced here (and re-tested in tests/test_catalog.py):
* unique, game-prefixed, stable IDs; unique canonical paths;
* option values unique per setting; sample/default values inside the declared domain;
* goal-hint values valid; dependency and preset references resolve inside the same game;
* every referenced source exists and carries a URL and date.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from .schema import (
    Availability,
    Catalog,
    MenuSection,
    MenuSubtab,
    MenuTab,
    Option,
    RawCatalog,
    RawSetting,
    Setting,
    Value,
)

GAME_PREFIX = {"valorant": "val", "cs2": "cs2"}


class CatalogError(ValueError):
    """Raised when a catalogue violates an integrity rule."""


def setting_id(game: str, tab_id: str, key: str) -> str:
    return f"{GAME_PREFIX[game]}.{tab_id}.{key}"


def _path(parts: list[Optional[str]], label: str, qualifier: Optional[str]) -> str:
    segs: list[str] = []
    for p in parts:
        if p and (not segs or segs[-1].lower() != p.lower()):
            segs.append(p)
    tail = f"{label} ({qualifier})" if qualifier else label
    return " > ".join(segs + [tail])


def _resolve_options(raw: RawSetting, option_sets: dict[str, list[Option]], where: str) -> Optional[list[Option]]:
    if raw.options is None:
        return None
    if isinstance(raw.options, str):
        if not raw.options.startswith("@") or raw.options[1:] not in option_sets:
            raise CatalogError(f"{where}: unknown option set {raw.options!r}")
        return [o.model_copy() for o in option_sets[raw.options[1:]]]
    return list(raw.options)


def value_in_domain(setting: Setting, value: Any) -> bool:
    """True when `value` is a legal stored value for `setting` (no label resolution, no snapping)."""
    if setting.controlType in ("dropdown", "segmented", "preset"):
        return setting.validOptions is not None and any(o.value == str(value) for o in setting.validOptions)
    if setting.controlType == "slider":
        if isinstance(value, bool) or not isinstance(value, (int, float)) or math.isnan(float(value)):
            return False
        return setting.min is not None and setting.max is not None and setting.min - 1e-9 <= float(value) <= setting.max + 1e-9
    if setting.controlType == "keybind":
        return isinstance(value, str) and len(value) <= 40
    return False


def build_catalog(raw: RawCatalog) -> Catalog:
    game = raw.game
    sources = raw.sources
    for key, src in sources.items():
        if not src.url.startswith("http") or not src.date:
            raise CatalogError(f"{game}: source {key} lacks url/date")

    settings: list[Setting] = []
    menu: list[MenuTab] = []
    order = 0
    for tab in raw.tabs:
        m_subtabs: list[MenuSubtab] = []
        for sub in tab.subtabs:
            m_sections: list[MenuSection] = []
            if not sub.simulated and sub.sections:
                raise CatalogError(f"{game}.{tab.id}.{sub.id}: non-simulated sub-tab must not contain settings")
            for sec in sub.sections:
                ids: list[str] = []
                for rs in sec.settings:
                    where = f"{game}.{tab.id}.{rs.key}"
                    order += 10
                    options = _resolve_options(rs, raw.optionSets, where)
                    src_refs = rs.sources or list(raw.defaults.sources)
                    for ref in src_refs:
                        if ref not in sources:
                            raise CatalogError(f"{where}: unknown source {ref!r}")
                    primary = sources[src_refs[0]]
                    tags = sorted({h.dimension for h in rs.hints} | set(rs.tags))
                    path_ver = rs.pathVerification or sec.pathVerification or "verified"
                    s = Setting(
                        id=setting_id(game, tab.id, rs.key),
                        key=rs.key,
                        game=game,
                        tabId=tab.id,
                        subtabId=sub.id,
                        sectionId=sec.id,
                        category=tab.label,
                        subcategory=sub.label,
                        section=sec.label,
                        order=order,
                        exactLabel=rs.label,
                        qualifier=rs.qualifier,
                        canonicalPath=_path([tab.label, sub.label, sec.label], rs.label, rs.qualifier),
                        description=rs.description,
                        descriptionSource=rs.descriptionSource,
                        controlType=rs.control,
                        validOptions=options,
                        optionsSimulated=rs.optionsSimulated,
                        min=rs.min,
                        max=rs.max,
                        step=rs.step,
                        precision=rs.precision,
                        unit=rs.unit,
                        display=rs.display,
                        rangeVerified=rs.rangeVerified,
                        preset=rs.preset,
                        verifiedDefault=rs.default,
                        sampleInitialValue=rs.sample,
                        availability=rs.availability or Availability(),
                        riskOrTradeoffs=rs.tradeoffs,
                        goalTags=tags,
                        goalHints=rs.hints,
                        aiProposable=raw.defaults.aiProposable if rs.aiProposable is None else rs.aiProposable,
                        applyMode=tab.applyMode,
                        sourceRefs=src_refs,
                        sourceURL=primary.url,
                        sourceDate=primary.date,
                        verificationStatus=rs.verification or raw.defaults.verification,
                        verificationNotes=rs.verificationNotes,
                        pathVerification=path_ver,
                        lastReviewed=rs.lastReviewed or raw.lastReviewed,
                    )
                    settings.append(s)
                    ids.append(s.id)
                m_sections.append(MenuSection(id=sec.id, label=sec.label,
                                              pathVerification=sec.pathVerification or "verified", settingIds=ids))
            m_subtabs.append(MenuSubtab(id=sub.id, label=sub.label, simulated=sub.simulated and tab.simulated,
                                        note=sub.note, sections=m_sections))
        menu.append(MenuTab(id=tab.id, label=tab.label, subtabMode=tab.subtabMode, applyMode=tab.applyMode,
                            simulated=tab.simulated, note=tab.note, preview=tab.preview, subtabs=m_subtabs))

    catalog = Catalog(game=game, displayName=raw.displayName, shortName=raw.shortName,
                      catalogVersion=raw.catalogVersion, lastReviewed=raw.lastReviewed, menuNote=raw.menuNote,
                      navExtras=raw.navExtras, sources=sources, menu=menu, settings=settings)
    validate_catalog(catalog)
    return catalog


def validate_catalog(catalog: Catalog) -> None:
    by_id: dict[str, Setting] = {}
    by_key: dict[str, Setting] = {}
    paths: set[str] = set()
    prefix = GAME_PREFIX[catalog.game] + "."
    for s in catalog.settings:
        where = s.id
        if not s.id.startswith(prefix):
            raise CatalogError(f"{where}: id must start with {prefix!r}")
        if s.id in by_id:
            raise CatalogError(f"duplicate setting id {s.id}")
        if s.key in by_key:
            raise CatalogError(f"duplicate setting key {s.key} in {catalog.game}")
        if s.canonicalPath in paths:
            raise CatalogError(f"duplicate canonical path {s.canonicalPath}")
        by_id[s.id], by_key[s.key] = s, s
        paths.add(s.canonicalPath)

        if s.controlType in ("dropdown", "segmented", "preset"):
            if not s.validOptions or len(s.validOptions) < 2:
                raise CatalogError(f"{where}: discrete control needs >= 2 options")
            vals = [o.value for o in s.validOptions]
            if len(set(vals)) != len(vals):
                raise CatalogError(f"{where}: duplicate option values")
            labels = [o.label for o in s.validOptions]
            if len(set(labels)) != len(labels):
                raise CatalogError(f"{where}: duplicate option labels")
            if s.min is not None or s.max is not None:
                raise CatalogError(f"{where}: discrete control must not declare min/max")
        elif s.controlType == "slider":
            if s.min is None or s.max is None or s.step is None or not (s.min < s.max) or s.step <= 0:
                raise CatalogError(f"{where}: slider needs min < max and step > 0")
            if s.validOptions:
                raise CatalogError(f"{where}: slider must not declare options")
        elif s.controlType == "keybind" and s.aiProposable:
            raise CatalogError(f"{where}: keybinds are never AI-proposable")

        if s.controlType == "preset":
            if s.preset is None or s.aiProposable:
                raise CatalogError(f"{where}: preset needs a spec and must not be AI-proposable")
        elif not value_in_domain(s, s.sampleInitialValue):
            raise CatalogError(f"{where}: sample value {s.sampleInitialValue!r} outside domain")
        dv = s.verifiedDefault
        if dv.status in ("verified", "inferred", "reported") and dv.value is None:
            raise CatalogError(f"{where}: default status {dv.status} requires a value")
        if dv.value is not None and s.controlType != "preset" and not value_in_domain(s, dv.value):
            raise CatalogError(f"{where}: default value {dv.value!r} outside domain")
        if dv.source and dv.source not in catalog.sources:
            raise CatalogError(f"{where}: default source {dv.source!r} unknown")
        for h in s.goalHints:
            for v in h.prefer:
                if not value_in_domain(s, v):
                    raise CatalogError(f"{where}: hint value {v!r} outside domain")
        if s.controlType == "slider" and not s.rangeVerified and s.aiProposable:
            raise CatalogError(f"{where}: unverified-range sliders must not be AI-proposable")

    for s in catalog.settings:
        av = s.availability
        for cond in (av.enabledWhen, av.visibleWhen):
            if cond is None:
                continue
            target = by_key.get(cond.setting)
            if target is None:
                raise CatalogError(f"{s.id}: dependency on unknown setting {cond.setting!r}")
            for v in cond.values:
                if not value_in_domain(target, v):
                    raise CatalogError(f"{s.id}: dependency value {v!r} invalid for {target.id}")
        if s.preset is not None:
            for member in s.preset.members:
                if member not in by_key:
                    raise CatalogError(f"{s.id}: preset member {member!r} unknown")
            option_values = {o.value for o in (s.validOptions or [])}
            for pval, mapping in s.preset.values.items():
                if pval not in option_values:
                    raise CatalogError(f"{s.id}: preset value {pval!r} not an option")
                if set(mapping) != set(s.preset.members):
                    raise CatalogError(f"{s.id}: preset {pval!r} must assign every member")
                for member, mv in mapping.items():
                    if not value_in_domain(by_key[member], mv):
                        raise CatalogError(f"{s.id}: preset {pval!r} gives invalid {member}={mv!r}")


def load_catalog_file(path: Path) -> Catalog:
    data = json.loads(path.read_text(encoding="utf-8"))
    return build_catalog(RawCatalog.model_validate(data))


class CatalogRegistry:
    """All loaded catalogues, keyed by game id."""

    def __init__(self, catalogs: dict[str, Catalog]):
        self._catalogs = catalogs
        self._by_id = {g: c.by_id() for g, c in catalogs.items()}
        self._by_key = {g: {s.key: s for s in c.settings} for g, c in catalogs.items()}

    @property
    def games(self) -> list[str]:
        return list(self._catalogs)

    def catalog(self, game: str) -> Catalog:
        if game not in self._catalogs:
            raise KeyError(game)
        return self._catalogs[game]

    def setting(self, game: str, setting_id: str) -> Optional[Setting]:
        return self._by_id.get(game, {}).get(setting_id)

    def by_key(self, game: str, key: str) -> Optional[Setting]:
        return self._by_key.get(game, {}).get(key)

    def settings(self, game: str) -> list[Setting]:
        return self.catalog(game).settings

    def find_any_game(self, setting_id: str) -> Optional[Setting]:
        for g in self._catalogs:
            s = self.setting(g, setting_id)
            if s is not None:
                return s
        return None


def load_registry(catalog_dir: Path) -> CatalogRegistry:
    catalogs: dict[str, Catalog] = {}
    for game in ("valorant", "cs2"):
        path = catalog_dir / f"{game}.json"
        catalogs[game] = load_catalog_file(path)
    return CatalogRegistry(catalogs)


@lru_cache(maxsize=4)
def cached_registry(catalog_dir: str) -> CatalogRegistry:
    return load_registry(Path(catalog_dir))


def coerce_number(value: Value) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None
