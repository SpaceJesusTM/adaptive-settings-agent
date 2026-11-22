// Mirrors backend/app/catalog/schema.py and the API payloads in backend/app/api/routes.py.

export type GameId = "valorant" | "cs2";
export type Value = string | number;
export type Condition = "baseline" | "adaptive";
export type ControlType = "segmented" | "dropdown" | "slider" | "keybind" | "preset" | "color";
export type ScopeOverride = "auto" | "focused" | "comprehensive";
export type WorkspaceTab = "changes" | "pinned" | "discover";

export interface Option {
  value: string;
  label: string;
}

export interface DefaultInfo {
  status: "verified" | "inferred" | "reported" | "conflicting" | "unknown" | "hardware-dependent";
  value?: Value | null;
  source?: string | null;
  note?: string | null;
}

export interface GoalHint {
  dimension: string;
  prefer: Value[];
  why: string;
  basis: "official" | "editorial";
}

export interface ConditionRef {
  setting: string;
  values: Value[];
}

export interface Availability {
  requires?: { gpuVendor?: string[] | null; gsyncDisplay?: boolean | null } | null;
  enabledWhen?: ConditionRef | null;
  visibleWhen?: ConditionRef | null;
  note?: string | null;
}

export interface Setting {
  id: string;
  key: string;
  game: GameId;
  tabId: string;
  subtabId: string;
  sectionId: string;
  category: string;
  subcategory: string | null;
  section: string | null;
  order: number;
  exactLabel: string;
  qualifier: string | null;
  canonicalPath: string;
  description: string;
  descriptionSource: string;
  controlType: ControlType;
  validOptions: Option[] | null;
  optionsSimulated: boolean;
  min: number | null;
  max: number | null;
  step: number | null;
  precision: number | null;
  unit: string | null;
  display: string | null;
  rangeVerified: boolean;
  preset: { members: string[]; values: Record<string, Record<string, string>> } | null;
  verifiedDefault: DefaultInfo;
  sampleInitialValue: Value;
  availability: Availability;
  riskOrTradeoffs: string | null;
  goalTags: string[];
  goalHints: GoalHint[];
  aiProposable: boolean;
  applyMode: "immediate" | "explicit";
  sourceRefs: string[];
  sourceURL: string;
  sourceDate: string;
  verificationStatus: string;
  verificationNotes: string | null;
  pathVerification: string;
  lastReviewed: string;
}

export interface MenuSection {
  id: string;
  label: string | null;
  pathVerification: string;
  settingIds: string[];
}
export interface MenuSubtab {
  id: string;
  label: string | null;
  simulated: boolean;
  note: string | null;
  sections: MenuSection[];
}
export interface MenuTab {
  id: string;
  label: string;
  subtabMode: "single" | "pages" | "anchors";
  applyMode: "immediate" | "explicit";
  simulated: boolean;
  note: string | null;
  preview: string | null;
  subtabs: MenuSubtab[];
}
export interface Source {
  title: string;
  publisher: string;
  url: string;
  date: string;
  kind: string;
  note?: string | null;
}
export interface Catalog {
  game: GameId;
  displayName: string;
  shortName: string;
  catalogVersion: string;
  lastReviewed: string;
  menuNote: string;
  navExtras: { type: "search" | "promoted"; label: string; simulated: boolean; note?: string | null }[];
  sources: Record<string, Source>;
  menu: MenuTab[];
  settings: Setting[];
}

export interface ValueEntry {
  value: Value;
  revision: number;
  derived?: boolean;
}

export interface Hardware {
  label?: string;
  gpuVendor?: string;
  gpu?: string;
  cpuCores?: number;
  ramGB?: number;
  vramGB?: number;
  displayRefreshHz?: number;
  gsyncDisplay?: boolean;
}

export interface GameState {
  game: GameId;
  gameRevision: number;
  values: Record<string, ValueEntry>;
  pins: string[];
  locks: string[];
  pendingProposalIds: string[];
  hardware: Hardware;
}

export interface Session {
  sessionId: string;
  condition: Condition;
  selectedGame: GameId;
  adaptationEnabled: boolean;
  aiMode: "local" | "fallback";
  scenario: string | null;
  hardware: Hardware;
  startedAt: string;
}

export interface HistoryEvent {
  eventId: string;
  settingId: string;
  label: string;
  path: string;
  oldValue: Value;
  newValue: Value;
  oldDisplay: string;
  newDisplay: string;
  revisionAfter: number;
  stillCurrent: boolean;
}

export interface HistoryBatch {
  batchId: string;
  game: GameId;
  source: string;
  sourceLabel: string;
  label: string | null;
  proposalId: string | null;
  condition: string | null;
  createdAt: string;
  undoesBatchId: string | null;
  undoneByBatchId: string | null;
  undoable: boolean;
  events: HistoryEvent[];
  gameRevision: number;
  values: Record<string, ValueEntry>;
  noop?: boolean;
  idempotentReplay?: boolean;
}

export interface ProposalItem {
  id: string;
  settingId: string;
  label: string;
  path: string;
  category?: string;
  section?: string | null;
  applyMode?: "immediate" | "explicit";
  tabId: string;
  subtabId: string;
  controlType: ControlType;
  validOptions: Option[];
  min: number | null;
  max: number | null;
  step: number | null;
  display: string | null;
  unit: string | null;
  baselineValue: Value;
  baselineDisplay: string;
  baselineRevision: number;
  proposedValue: Value;
  proposedDisplay: string;
  editedValue: Value | null;
  effectiveValue: Value;
  effectiveDisplay: string;
  currentValue: Value;
  currentDisplay: string;
  currentRevision: number;
  stale: boolean;
  locked: boolean;
  unavailableReason: string | null;
  status: "pending" | "applied" | "rejected" | "blocked";
  statusReason: string | null;
  why: string | null;
  tradeoff: string | null;
  whatItDoes: string;
  whatItDoesSource: string;
  sourceURL: string;
  confidence: string | null;
  dimensions: string[];
  basedOn: string | null;
}

export interface PlanCoverage {
  evaluatedCount: number;
  eligibleCount: number;
  proposedCount: number;
  alreadyAlignedCount: number;
  alreadyStagedCount: number;
  lockedCount: number;
  unavailableCount: number;
  manualCount: number;
  byCategory: Record<
    string,
    {
      evaluated: number;
      eligible: number;
      alreadyAligned: number;
      alreadyStaged: number;
      locked: number;
      unavailable: number;
      manual: number;
    }
  >;
}

export interface PlanManualConsideration {
  settingId: string;
  label: string;
  path: string;
  category: string;
  currentDisplay: string;
  reason: string;
  whatItDoes: string;
  tradeoffs: string | null;
}

export interface PlanMetadata {
  scope: "explain_only" | "focused" | "category_optimization" | "broad_optimization" | "full_game_setup";
  maxRecommendations: number;
  includeMinor: boolean;
  isSupplement: boolean;
  reason: string;
  inferredDimensions: string[];
  explicitOverride?: string | null;
  singleSettingHint?: boolean;
  autoStage: boolean;
  partialCoverage: boolean;
  batchesCompleted: number;
  batchesTotal: number;
  coverage: PlanCoverage;
  manualConsiderations: PlanManualConsideration[];
}

export interface CrosshairProfile {
  id: string;
  name: string;
  isActive: boolean;
  settings: Record<string, Value>;
  createdAt: string;
  updatedAt: string;
}

export interface Proposal {
  id: string;
  game: GameId;
  source: "ai" | "fallback" | "rules";
  sourceLabel: string;
  runId: string | null;
  title: string;
  status: "pending" | "applied" | "rejected" | "closed";
  createdAt: string;
  updatedAt: string;
  appliedBatchId: string | null;
  autoStaged?: boolean;
  plan?: PlanMetadata | null;
  items: ProposalItem[];
}

export interface Recommendation {
  settingId: string;
  label: string;
  path: string;
  tabId: string;
  subtabId: string;
  currentValue: Value;
  currentDisplay: string;
  proposedValue: Value;
  proposedDisplay: string;
  whatItDoes: string;
  whatItDoesSource: string;
  sourceURL: string;
  verificationStatus: string;
  whyForGoal: string;
  tradeoff: string | null;
  confidence: string;
  dimension: string | null;
  dimensionLabel: string | null;
  basedOn: string | null;
  crossGame?: boolean;
  source: "ai" | "fallback" | "rules";
}

export interface Explanation {
  settingId: string;
  label: string;
  path: string;
  tabId: string;
  subtabId: string;
  explanation: string;
  catalogDescription: string;
  tradeoffs: string | null;
  sourceURL: string;
  verificationStatus: string;
  source: string;
}

export interface PreferenceSuggestion {
  dimension: string;
  dimensionLabel: string;
  direction: "prioritize" | "deprioritize";
  scope: "session" | "durable";
  quote: string;
  game: GameId;
}

export interface Provenance {
  source: "ai" | "fallback";
  model: string | null;
  modelTag?: string | null;
  fallbackReason?: string | null;
  indicator?: string;
  latencyMs?: number;
}

export interface AssistantResponse {
  intent: string;
  reply: string;
  knownsAndUnknowns: string | null;
  goalDimensions: string[];
  recommendations: Recommendation[];
  explanations: Explanation[];
  navigateTo: { settingId: string; label: string; path: string; tabId: string; subtabId: string } | null;
  preferenceSuggestions: PreferenceSuggestion[];
  clarifyingQuestion: string | null;
  filtered: { settingRef?: string; settingId?: string; kind: string; reason: string }[];
  validationNotes: string[];
  provenance: Provenance;
  sessionGoalId?: string | null;
  stagedProposalId?: string | null;
  stagedCount?: number;
  alreadyPendingCount?: number;
  plan?: PlanMetadata | null;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  runId: string | null;
  createdAt: string;
  text?: string;
  response?: AssistantResponse;
}

export interface RunStatus {
  runId: string;
  game: GameId;
  status: "running" | "succeeded" | "fallback" | "failed" | "cancelled";
  steps: { label: string; at: string }[];
  elapsedMs?: number;
  result?: AssistantResponse | null;
  error?: string | null;
  latencyMs?: number | null;
  toolCalls?: { tool: string; by: string; ok: boolean; ms?: number; args?: unknown; error?: string | null }[];
  validation?: { filtered: unknown[]; notes: string[]; modelCalls: unknown[] };
  model?: string | null;
  mode?: string;
  condition?: string | null;
  goalExcerpt?: string;
  startedAt?: string;
  finishedAt?: string | null;
}

export interface RelevantCard {
  cardId: string;
  settingId: string;
  label: string;
  path: string;
  currentValue: Value;
  currentDisplay: string;
  targetValue: Value;
  targetDisplay: string;
  score: number;
  dimension: string;
  dimensionLabel: string;
  whatItDoes: string;
  whatItDoesSource: string;
  why: string;
  whyBasis: "official" | "editorial";
  basedOn: string[];
  crossGame: boolean;
  tradeoff: string | null;
  sourceURL: string;
  verificationStatus: string;
  state: "suggested" | "staged" | "applied" | "dismissed" | "locked" | "changed" | "stale";
  liveValue?: Value;
  liveDisplay?: string;
  dismissReason?: string | null;
}

export interface RelevantNowSet {
  game: GameId;
  items: RelevantCard[];
  trigger: string | null;
  createdAt: string | null;
  updateAvailable: boolean;
  hasEvidence?: boolean;
  disabled?: boolean;
  context?: { id: string; eventType: string; label: string; dimensions: string[]; simulated: boolean } | null;
}

export interface Preference {
  id: string;
  dimension: string;
  dimensionLabel: string;
  direction: "prioritize" | "deprioritize";
  scope: "durable" | "session";
  game: GameId | null;
  originGame: GameId | null;
  source: string;
  note: string | null;
  createdAt: string;
  evidence: { kind: string; game: string | null; setting_id: string | null; detail: string | null; created_at: string }[];
}

export interface SessionGoal {
  id: string;
  text: string;
  dimensions: string[];
  source: string;
  createdAt: string;
}

export interface Profile {
  preferences: Preference[];
  sessionGoals: Record<GameId, SessionGoal[]>;
  context: Record<GameId, RelevantNowSet["context"]>;
  evidence: { id: string; kind: string; dimension: string | null; game: string | null; detail: string | null; created_at: string }[];
  dimensions: { id: string; label: string }[];
}

export interface ModelStatus {
  state: string;
  indicator: "connected" | "unavailable" | "fallback";
  indicatorLabel: string;
  model: string | null;
  baseUrl: string;
  ollamaVersion: string | null;
  details: { family?: string; parameterSize?: string; quantization?: string } | null;
  capabilities: string[];
  message: string;
  aiMode: "local" | "fallback";
}

export interface SearchHit {
  settingId: string;
  label: string;
  path: string;
  tabId: string;
  subtabId: string;
  sectionId: string;
}

export interface ScenarioInfo {
  name: string;
  title: string;
  description: string;
  synthetic: boolean;
}

export interface ContextEventType {
  eventType: string;
  label: string;
  dimensions: string[];
  simulated: boolean;
}
