import type { Catalog, GameState, Proposal, Session, Setting } from "../api/types";

function setting(partial: Partial<Setting> & Pick<Setting, "id" | "key" | "exactLabel" | "controlType" | "sectionId">): Setting {
  return {
    game: "valorant",
    tabId: "video",
    subtabId: "graphics_quality",
    category: "Video",
    subcategory: "Graphics Quality",
    section: null,
    order: 10,
    qualifier: null,
    canonicalPath: `Video > Graphics Quality > ${partial.exactLabel}`,
    description: `${partial.exactLabel} description`,
    descriptionSource: "official-doc",
    validOptions: null,
    optionsSimulated: false,
    min: null,
    max: null,
    step: null,
    precision: null,
    unit: null,
    display: null,
    rangeVerified: true,
    preset: null,
    verifiedDefault: { status: "unknown" },
    sampleInitialValue: "on",
    availability: {},
    riskOrTradeoffs: null,
    goalTags: [],
    goalHints: [],
    aiProposable: true,
    applyMode: "immediate",
    sourceRefs: ["src"],
    sourceURL: "https://example.org",
    sourceDate: "2026-10-07",
    verificationStatus: "verified-official-doc",
    verificationNotes: null,
    pathVerification: "verified",
    lastReviewed: "2026-11-21",
    ...partial,
  };
}

const ON_OFF = [{ value: "on", label: "On" }, { value: "off", label: "Off" }];

export const SETTINGS: Setting[] = [
  setting({ id: "val.video.vsync", key: "vsync", exactLabel: "VSync", controlType: "segmented", sectionId: "graphics", validOptions: ON_OFF }),
  setting({ id: "val.video.bloom", key: "bloom", exactLabel: "Bloom", controlType: "segmented", sectionId: "graphics", validOptions: ON_OFF, order: 20 }),
  setting({ id: "val.video.anti_aliasing", key: "anti_aliasing", exactLabel: "Anti-Aliasing", controlType: "dropdown", sectionId: "graphics", order: 30,
    validOptions: [{ value: "none", label: "None" }, { value: "msaa_2x", label: "MSAA 2x" }, { value: "msaa_4x", label: "MSAA 4x" }] }),
  setting({ id: "val.video.rotate", key: "rotate", exactLabel: "Rotate", controlType: "segmented", sectionId: "graphics", order: 40,
    validOptions: [{ value: "rotate", label: "Rotate" }, { value: "fixed", label: "Fixed" }] }),
  setting({ id: "val.video.fixed_orientation", key: "fixed_orientation", exactLabel: "Fixed Orientation", controlType: "segmented", sectionId: "graphics", order: 50,
    validOptions: [{ value: "always_same", label: "Always the Same" }, { value: "based_on_side", label: "Based On Side" }],
    availability: { enabledWhen: { setting: "rotate", values: ["fixed"] } } }),
];

export const CATALOG: Catalog = {
  game: "valorant",
  displayName: "VALORANT",
  shortName: "VALORANT",
  catalogVersion: "test",
  lastReviewed: "2026-11-21",
  menuNote: "",
  navExtras: [],
  sources: { src: { title: "t", publisher: "p", url: "https://example.org", date: "2026-10-07", kind: "official-doc" } },
  menu: [
    { id: "general", label: "General", subtabMode: "single", applyMode: "immediate", simulated: true, note: null, preview: null,
      subtabs: [{ id: "general", label: null, simulated: true, note: null, sections: [] }] },
    { id: "video", label: "Video", subtabMode: "pages", applyMode: "immediate", simulated: true, note: null, preview: null,
      subtabs: [{ id: "graphics_quality", label: "Graphics Quality", simulated: true, note: null,
        sections: [{ id: "graphics", label: null, pathVerification: "verified", settingIds: SETTINGS.map((s) => s.id) }] }] },
  ],
  settings: SETTINGS,
};

export const STATE: GameState = {
  game: "valorant",
  gameRevision: 0,
  values: {
    "val.video.vsync": { value: "on", revision: 0 },
    "val.video.bloom": { value: "on", revision: 0 },
    "val.video.anti_aliasing": { value: "msaa_4x", revision: 0 },
    "val.video.rotate": { value: "rotate", revision: 0 },
    "val.video.fixed_orientation": { value: "based_on_side", revision: 0 },
  },
  pins: [],
  locks: ["val.video.vsync"],
  pendingProposalIds: [],
  hardware: { gpuVendor: "NVIDIA" },
};

export function session(condition: "baseline" | "adaptive"): Session {
  return { sessionId: "s", condition, selectedGame: "valorant", adaptationEnabled: true, aiMode: "local", scenario: "default", hardware: {}, startedAt: "" };
}

export const PROPOSAL: Proposal = {
  id: "prop_1",
  game: "valorant",
  source: "ai",
  sourceLabel: "Local AI suggestion",
  runId: null,
  title: "Chat suggestions",
  status: "pending",
  createdAt: new Date().toISOString(),
  updatedAt: new Date().toISOString(),
  appliedBatchId: null,
  items: [{
    id: "item_1", settingId: "val.video.bloom", label: "Bloom", path: "Video > Graphics Quality > Bloom", tabId: "video", subtabId: "graphics_quality",
    controlType: "segmented", validOptions: ON_OFF, min: null, max: null, step: null, display: null, unit: null,
    baselineValue: "on", baselineDisplay: "On", baselineRevision: 0, proposedValue: "off", proposedDisplay: "Off", editedValue: null,
    effectiveValue: "off", effectiveDisplay: "Off", currentValue: "on", currentDisplay: "On", currentRevision: 0, stale: false, locked: false,
    unavailableReason: null, status: "pending", statusReason: null, why: "Fewer effects", tradeoff: null, whatItDoes: "Glow", whatItDoesSource: "official-doc",
    sourceURL: "https://example.org", confidence: "medium", dimensions: ["performance"], basedOn: null,
  }],
};
