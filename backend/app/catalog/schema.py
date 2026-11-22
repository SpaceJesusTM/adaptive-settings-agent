"""Typed schema for the canonical per-game settings catalogues (data/catalogs/*.json).

The JSON files are nested (tab -> sub-tab -> section -> settings) so that menu position is explicit and
ordering is stable. The loader flattens them into `Setting` records that carry every per-setting field the
research specification requires (id, path, labels, domain, provenance, verification status, ...).
"""
from __future__ import annotations

from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

Value = Union[str, int, float]

Dimension = Literal[
    "performance",
    "input_latency",
    "visibility",
    "visual_quality",
    "audio_awareness",
    "communication",
    "focus",
    "comfort",
    "network_stability",
]

DIMENSION_LABELS: dict[str, str] = {
    "performance": "smoother, more stable frame rate",
    "input_latency": "low input latency",
    "visibility": "clear player visibility",
    "visual_quality": "visual quality",
    "audio_awareness": "hearing positional audio cues",
    "communication": "team communication",
    "focus": "fewer distractions",
    "comfort": "comfort and ergonomics",
    "network_stability": "stable network play",
}

ControlType = Literal["segmented", "dropdown", "slider", "keybind", "preset", "color"]
VerificationStatus = Literal[
    "verified-game-files",
    "verified-official-doc",
    "verified-official-screenshot",
    "partially-verified",
    "secondary-only",
]
DefaultStatus = Literal["verified", "inferred", "reported", "conflicting", "unknown", "hardware-dependent"]
DescriptionSource = Literal[
    "official-tooltip", "official-doc", "official-notes", "official-convar-help", "editorial"
]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Source(_Strict):
    title: str
    publisher: str
    url: str
    date: str
    kind: Literal["game-files", "official-doc", "official-notes", "official-screenshot", "secondary"]
    note: Optional[str] = None


class Option(_Strict):
    value: str
    label: str


class DefaultInfo(_Strict):
    status: DefaultStatus
    value: Optional[Value] = None
    source: Optional[str] = None
    note: Optional[str] = None


class GoalHint(_Strict):
    dimension: Dimension
    prefer: list[Value] = Field(min_length=1)
    why: str
    basis: Literal["official", "editorial"]


class Condition(_Strict):
    setting: str  # setting key within the same game
    values: list[Value] = Field(min_length=1)


class Requirements(_Strict):
    gpuVendor: Optional[list[str]] = None
    gsyncDisplay: Optional[bool] = None


class Availability(_Strict):
    requires: Optional[Requirements] = None
    enabledWhen: Optional[Condition] = None
    visibleWhen: Optional[Condition] = None
    note: Optional[str] = None


class PresetSpec(_Strict):
    members: list[str]
    values: dict[str, dict[str, str]]


class RawSetting(_Strict):
    key: str = Field(pattern=r"^[a-z0-9_]+$")
    label: str
    control: ControlType
    options: Optional[Union[str, list[Option]]] = None
    optionsSimulated: bool = False
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    precision: Optional[int] = None
    unit: Optional[str] = None
    display: Optional[Literal["percent"]] = None
    rangeVerified: bool = True
    applyMode: Optional[Literal["immediate", "explicit"]] = None
    qualifier: Optional[str] = None
    preset: Optional[PresetSpec] = None
    default: DefaultInfo
    sample: Value
    description: str
    descriptionSource: DescriptionSource
    tradeoffs: Optional[str] = None
    hints: list[GoalHint] = Field(default_factory=list)
    tags: list[Dimension] = Field(default_factory=list)
    aiProposable: Optional[bool] = None
    availability: Optional[Availability] = None
    verification: Optional[VerificationStatus] = None
    verificationNotes: Optional[str] = None
    pathVerification: Optional[Literal["verified", "inferred", "partial"]] = None
    sources: Optional[list[str]] = None
    lastReviewed: Optional[str] = None


class RawSection(_Strict):
    id: str
    label: Optional[str]
    pathVerification: Optional[Literal["verified", "inferred", "partial"]] = None
    settings: list[RawSetting] = Field(default_factory=list)


class RawSubtab(_Strict):
    id: str
    label: Optional[str]
    simulated: bool = True
    note: Optional[str] = None
    sections: list[RawSection] = Field(default_factory=list)


class RawTab(_Strict):
    id: str
    label: str
    subtabMode: Literal["single", "pages", "anchors"]
    applyMode: Literal["immediate", "explicit"] = "immediate"
    simulated: bool = True
    note: Optional[str] = None
    preview: Optional[Literal["crosshair"]] = None
    subtabs: list[RawSubtab]


class NavExtra(_Strict):
    type: Literal["search", "promoted"]
    label: str
    simulated: bool
    note: Optional[str] = None


class CatalogDefaults(_Strict):
    verification: VerificationStatus
    sources: list[str]
    aiProposable: bool = True


class RawCatalog(_Strict):
    schemaVersion: int
    game: Literal["valorant", "cs2"]
    displayName: str
    shortName: str
    catalogVersion: str
    lastReviewed: str
    menuNote: str
    navExtras: list[NavExtra] = Field(default_factory=list)
    sources: dict[str, Source]
    optionSets: dict[str, list[Option]] = Field(default_factory=dict)
    defaults: CatalogDefaults
    tabs: list[RawTab]


# ---------------------------------------------------------------------------------------------
# Flattened, API-facing records
# ---------------------------------------------------------------------------------------------


class Setting(BaseModel):
    """One canonical setting with every field required by the specification (flattened)."""

    model_config = ConfigDict(frozen=True)

    id: str
    key: str
    game: str
    tabId: str
    subtabId: str
    sectionId: str
    category: str  # tab label
    subcategory: Optional[str]  # sub-tab label (None when the tab has no sub-tabs)
    section: Optional[str]  # section heading (None when the game shows no heading)
    order: int
    exactLabel: str
    qualifier: Optional[str]
    canonicalPath: str
    description: str
    descriptionSource: str
    controlType: ControlType
    validOptions: Optional[list[Option]]
    optionsSimulated: bool
    min: Optional[float]
    max: Optional[float]
    step: Optional[float]
    precision: Optional[int]
    unit: Optional[str]
    display: Optional[str]
    rangeVerified: bool
    preset: Optional[PresetSpec]
    verifiedDefault: DefaultInfo
    sampleInitialValue: Value
    availability: Availability
    riskOrTradeoffs: Optional[str]
    goalTags: list[str]
    goalHints: list[GoalHint]
    aiProposable: bool
    applyMode: Literal["immediate", "explicit"]
    sourceRefs: list[str]
    sourceURL: str
    sourceDate: str
    verificationStatus: VerificationStatus
    verificationNotes: Optional[str]
    pathVerification: Literal["verified", "inferred", "partial"]
    lastReviewed: str

    def option_label(self, value: Any) -> Optional[str]:
        if self.validOptions is None:
            return None
        for opt in self.validOptions:
            if opt.value == str(value):
                return opt.label
        return None


class MenuSection(BaseModel):
    id: str
    label: Optional[str]
    pathVerification: str
    settingIds: list[str]


class MenuSubtab(BaseModel):
    id: str
    label: Optional[str]
    simulated: bool
    note: Optional[str]
    sections: list[MenuSection]


class MenuTab(BaseModel):
    id: str
    label: str
    subtabMode: str
    applyMode: str
    simulated: bool
    note: Optional[str]
    preview: Optional[str]
    subtabs: list[MenuSubtab]


class Catalog(BaseModel):
    game: str
    displayName: str
    shortName: str
    catalogVersion: str
    lastReviewed: str
    menuNote: str
    navExtras: list[NavExtra]
    sources: dict[str, Source]
    menu: list[MenuTab]
    settings: list[Setting]

    def by_id(self) -> dict[str, Setting]:
        return {s.id: s for s in self.settings}
