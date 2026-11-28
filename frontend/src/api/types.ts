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
  currentValue?: Value | null;
  currentDisplay?: string | null;
  revisionAfter: number;
  stillCurrent: boolean;
  why?: string | null;
  tradeoff?: string | null;
  basedOn?: string | null;
  wasEditedByUser?: boolean;
}

export interface HistoryProvenance {
  hasRecordedRationale: boolean;
  userRequest: string | null;
  userRequestIsExcerpt?: boolean;
  runId: string | null;
  model: string | null;
  proposalTitle: string | null;
  restagedFromBatchId: string | null;
  planReason: string | null;
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
  superseded?: boolean;
  supersededCount?: number;
  outdatedForCurrentGoal?: boolean;
  provenance?: HistoryProvenance;
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
  tradeoffRetainedCount?: number;
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
  dimension?: string | null;
  dimensionLabel?: string | null;
  why?: string | null;
  reason: string;
  whatItDoes: string;
  tradeoffs: string | null;
}

export interface PlanAlignedItem {
  settingId: string;
  label: string;
  path: string;
  category?: string;
  currentDisplay: string;
  dimension?: string | null;
  dimensionLabel?: string | null;
  why?: string | null;
  whatItDoes?: string;
  tradeoffs?: string | null;
}

export interface PlanStatusItem {
  settingId: string;
  label: string;
  path: string;
  currentDisplay?: string;
  reason: string;
}

export interface TradeoffRetainedItem {
  settingId: string;
  label: string;
  path: string;
  category: string;
  currentDisplay: string;
  reason: string;
  conflictsWith?: string[];
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
  restagedFromBatchId?: string | null;
  coverage: PlanCoverage;
  alreadyAlignedItems?: PlanAlignedItem[];
  tradeoffRetainedItems?: TradeoffRetainedItem[];
  lockedItems?: PlanStatusItem[];
  unavailableItems?: PlanStatusItem[];
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
  source: "ai" | "fallback" | "rules" | "history";
  sourceLabel: string;
  runId: string | null;
  title: string;
  status: "pending" | "applied" | "rejected" | "closed";
  createdAt: string;
  updatedAt: string;
  appliedBatchId: string | null;
  autoStaged?: boolean;
  restagedFromBatchId?: string | null;
  generatedGoalText?: string | null;
  generatedGoalDimensions?: string[];
  freshnessStatus?: "consistent" | "outdated_goal" | "historical_preference" | "technically_stale";
  freshnessWarning?: string | null;
  plan?: PlanMetadata | null;
  items: ProposalItem[];
}

export interface RestageResult {
  proposal: Proposal | null;
  stagedCount: number;
  alreadyAlignedItems: PlanAlignedItem[];
  manualConsiderations: PlanManualConsideration[];
  lockedItems: PlanStatusItem[];
  unavailableItems: PlanStatusItem[];
  message: string;
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
  source: "ai" | "fallback" | "rules";
  model: string | null;
  modelTag?: string | null;
  fallbackReason?: string | null;
  indicator?: string;
  latencyMs?: number;
}

export interface CrossGameSettingRef {
  settingId: string;
  game: GameId;
  label: string;
  path: string;
  controlType: ControlType;
  aiProposable: boolean;
  currentValue: Value;
  currentDisplay: string;
}

export interface SensitivityConversionResult {
  convertible: boolean;
  confirmed?: boolean;
  sourceGame: GameId;
  targetGame: GameId;
  sourceValue?: number;
  convertedValue?: number;
  formula?: string;
  reason?: string;
  assumptions: string[];
  caveats: string[];
}

export interface CrossGameComparison {
  id: string;
  topic: string;
  relationship: "direct_equivalent" | "similar_with_differences" | "loose_analogy" | "not_directly_comparable";
  relationshipLabel: string;
  summary: string;
  differences: string;
  safetyNote: string;
  proposable: boolean;
  sourceGame?: GameId;
  targetGame?: GameId;
  directionExplicit?: boolean;
  discrepancyNote?: string | null;
  sourceEvidence?: string;
  sourceEvidenceLabel?: string;
  targetNavigateGame?: GameId;
  valorantSettings: CrossGameSettingRef[];
  cs2Settings: CrossGameSettingRef[];
  confirmedFacts?: PersonalFact[];
  targetNavigateId?: string | null;
  sensitivityConversion?: SensitivityConversionResult;
}

export interface AppliedMemoryUpdate {
  kind: "preference" | "fact";
  id: string;
  label: string;
  dimension?: string;
  dimensionLabel?: string;
  direction?: "prioritize" | "deprioritize";
  scope?: "session" | "durable";
  factKey?: string;
  valueText?: string;
  originGame?: GameId;
  game?: GameId;
}

export interface AssistantResponse {
  intent: string;
  reply: string;
  knownsAndUnknowns: string | null;
  goalDimensions: string[];
  goalChanged?: boolean;
  recommendations: Recommendation[];
  explanations: Explanation[];
  navigateTo: { settingId: string; label: string; path: string; tabId: string; subtabId: string } | null;
  preferenceSuggestions: PreferenceSuggestion[];
  appliedMemoryUpdates?: AppliedMemoryUpdate[];
  clarifyingQuestion: string | null;
  filtered: { settingRef?: string; settingId?: string; kind: string; reason: string }[];
  validationNotes: string[];
  provenance: Provenance;
  sessionGoalId?: string | null;
  stagedProposalId?: string | null;
  stagedCount?: number;
  alreadyPendingCount?: number;
  plan?: PlanMetadata | null;
  crossGameComparisons?: CrossGameComparison[];
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
  kind?: "change" | "inspect";
  triggerGroup?: "onboarding" | "context_event" | "followup" | "goal_or_preference";
  triggerLabel?: string;
  checkId?: string;
  ruleId?: string;
  triggerBatchId?: string;
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
  whyOrigin?: "goal_hint" | "followup_rule" | "onboarding_observation";
  whyBasis: "official" | "editorial";
  basedOn: string[];
  crossGame: boolean;
  tradeoff: string | null;
  sourceURL: string;
  verificationStatus: string;
  state: "suggested" | "staged" | "applied" | "checked" | "no_longer_relevant" | "dismissed" | "locked" | "changed" | "stale";
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
  onboardingStatus?: "active" | "completed" | "dismissed" | null;
  canRevisitOnboarding?: boolean;
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
  appliesToGame?: GameId | null;
  source: string;
  note: string | null;
  createdAt: string;
  evidence: { kind: string; game: string | null; setting_id: string | null; detail: string | null; created_at: string; sourceCategory?: string }[];
}

export interface PersonalFact {
  id: string;
  factKey: string;
  label: string;
  valueText: string;
  originGame: GameId | null;
  sourceSettingId: string | null;
  source: string;
  note: string | null;
  createdAt: string;
}

export interface PersonalFactType {
  id: string;
  label: string;
  description: string;
  placeholder: string;
}

export interface GoalPreferenceConflict {
  goalDimension: string;
  goalDimensionLabel: string;
  preferenceId: string;
  preferenceLabel: string;
  preferenceDirection: string;
  scope: string;
  explanation: string;
}

export interface SessionGoal {
  id: string;
  protectedSettingIds?: string[];
  text: string;
  dimensions: string[];
  source: string;
  createdAt: string;
}

export interface ObservedSetting {
  settingId: string;
  game: GameId;
  label: string;
  path: string;
  controlType: string;
  value: Value;
  display: string;
  sourceKind: string;
  sourceLabel: string;
  deliberate: boolean;
  batchId?: string | null;
  updatedAt?: string | null;
  matchesDefault: boolean;
}

export interface FactDiscrepancy {
  factId: string;
  factKey: string;
  label: string;
  savedValue: string;
  game: GameId;
  settingId: string;
  settingLabel: string;
  liveValue: Value;
  liveDisplay: string;
  liveSourceKind: string;
  explanation: string;
}

export interface TentativeSignal {
  dimension: string;
  dimensionLabel: string;
  tentative: boolean;
  explanation: string;
}

export interface RecentObservedAction {
  batchId: string;
  game: GameId;
  source: string;
  label: string;
  count: number;
  createdAt: string;
  summary: string;
}

export interface ObservedSummary {
  keySettings: ObservedSetting[];
  recentActions: RecentObservedAction[];
  tentativeSignals: TentativeSignal[];
  discrepancies: FactDiscrepancy[];
}

export interface Profile {
  preferences: Preference[];
  personalFacts?: PersonalFact[];
  personalFactTypes?: PersonalFactType[];
  sessionGoals: Record<GameId, SessionGoal[]>;
  conflicts?: Record<GameId, GoalPreferenceConflict[]>;
  context: Record<GameId, RelevantNowSet["context"]>;
  evidence: { id: string; kind: string; dimension: string | null; game: string | null; preference_id?: string | null; detail: string | null; created_at: string }[];
  dimensions: { id: string; label: string }[];
  observed?: ObservedSummary;
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
