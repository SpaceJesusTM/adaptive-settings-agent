import { create } from "zustand";
import { ApiError, api } from "../api/client";
import type {
  AppliedMemoryUpdate,
  Catalog,
  ChatMessage,
  Condition,
  ContextEventType,
  CrosshairProfile,
  GameId,
  GameState,
  HistoryBatch,
  ModelStatus,
  PreferenceSuggestion,
  Profile,
  Proposal,
  Recommendation,
  RelevantCard,
  RelevantNowSet,
  RunStatus,
  ScenarioInfo,
  ScopeOverride,
  Session,
  Setting,
  Value,
  WorkspaceTab,
} from "../api/types";
import { derivePreset } from "../lib/availability";
import { displayValue, rowDomId, sameValue } from "../lib/format";
import { broadcastSync, clearDetachedLease, isDetachedLeaseAlive, subscribeSync } from "../lib/sync";

export const GAMES: GameId[] = ["valorant", "cs2"];

/** Stable empty array for selector fallbacks: zustand v5 selectors must not return a fresh [] on each call.
 *  Typed never[] so `x ?? EMPTY` keeps the element type of x. Never mutated. */
export const EMPTY: never[] = [];

export interface NavState {
  tabId: string;
  subtabId: string;
}

export interface Toast {
  id: number;
  kind: "info" | "success" | "error" | "warning";
  text: string;
}

export interface Highlight {
  game: GameId;
  settingId: string;
  nonce: number;
  reason: "search" | "assistant" | "pin" | "history";
}

export interface PinnedFeedback {
  status: "saved" | "error" | "conflict";
  message: string;
  batchId?: string;
}

function readInitialExperimenterMode(): boolean {
  if (typeof window === "undefined") return false;
  const params = new URLSearchParams(window.location.search);
  if (params.get("experimenter") === "1") return true;
  if (params.get("experimenter") === "0") return false;
  try {
    return window.sessionStorage.getItem("csc2524.experimenter") === "1";
  } catch {
    return false;
  }
}

function syncWorkspaceUrlGame(game: GameId) {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  if (url.searchParams.get("view") !== "workspace") return;
  if (url.searchParams.get("game") !== game) {
    url.searchParams.set("game", game);
    window.history.replaceState(null, "", url.pathname + url.search + url.hash);
  }
}

interface AppState {
  ready: boolean;
  fatal: string | null;
  session: Session | null;
  modelStatus: ModelStatus | null;
  catalogs: Partial<Record<GameId, Catalog>>;
  byId: Partial<Record<GameId, Record<string, Setting>>>;
  byKey: Partial<Record<GameId, Record<string, Setting>>>;
  states: Partial<Record<GameId, GameState>>;
  proposals: Partial<Record<GameId, Proposal[]>>;
  history: Partial<Record<GameId, HistoryBatch[]>>;
  relevantNow: Partial<Record<GameId, RelevantNowSet>>;
  chat: Partial<Record<GameId, ChatMessage[]>>;
  runs: Partial<Record<GameId, RunStatus | null>>;
  traces: RunStatus[];
  profile: Profile | null;
  contextTypes: ContextEventType[];
  scenarios: ScenarioInfo[];
  crosshairProfiles: CrosshairProfile[];
  nav: Record<GameId, NavState>;
  highlight: Highlight | null;
  pendingVideo: Partial<Record<GameId, Record<string, Value>>>;
  pinnedFeedback: Record<string, PinnedFeedback>;
  historyOpen: boolean;
  workspaceOpen: boolean;
  workspaceTab: WorkspaceTab;
  trayOpen: boolean;
  detachedWorkspaceActive: boolean;
  experimenterMode: boolean;
  scopeOverride: ScopeOverride;
  openCards: Record<string, boolean>;
  seenDiscoverIds: Record<GameId, string[]>;
  toasts: Toast[];
  composerPrefill: { game: GameId; text: string; nonce: number } | null;

  init: () => Promise<void>;
  prefillComposer: (game: GameId, text: string) => void;
  toast: (kind: Toast["kind"], text: string) => void;
  dismissToast: (id: number) => void;
  setExperimenterMode: (on: boolean) => void;
  setScopeOverride: (scope: ScopeOverride) => void;
  setWorkspaceOpen: (open: boolean) => void;
  setWorkspaceTab: (tab: WorkspaceTab) => void;
  openWorkspace: (tab?: WorkspaceTab) => void;
  setTrayOpen: (open: boolean) => void;
  loadGame: (game: GameId) => Promise<void>;
  refreshState: (game: GameId) => Promise<void>;
  refreshAdaptive: (game: GameId) => Promise<void>;
  refreshModelStatus: (force?: boolean) => Promise<void>;
  loadCrosshairProfiles: () => Promise<void>;
  createCrosshairProfile: (name: string, copyFromCurrent?: boolean) => Promise<boolean>;
  selectCrosshairProfile: (profileId: string) => Promise<void>;
  renameCrosshairProfile: (profileId: string, name: string) => Promise<void>;
  deleteCrosshairProfile: (profileId: string) => Promise<void>;
  importCrosshairCode: (code: string, name?: string) => Promise<string | null>;
  exportCrosshairCode: (profileId: string) => Promise<{ code: string; name: string; simulatedNote: string } | null>;
  switchGame: (game: GameId) => Promise<void>;
  setCondition: (condition: Condition) => Promise<void>;
  setAiMode: (mode: "local" | "fallback") => Promise<void>;
  setAdaptation: (on: boolean) => Promise<void>;
  navigate: (game: GameId, tabId: string, subtabId?: string) => void;
  goToSetting: (game: GameId, settingId: string, reason: Highlight["reason"]) => void;
  requestFocusInMainWindow: (game: GameId, settingId: string, reason?: Highlight["reason"]) => void;
  displayValues: (game: GameId) => Record<string, Value>;
  changeSetting: (game: GameId, settingId: string, value: Value) => Promise<void>;
  changePinnedSetting: (game: GameId, settingId: string, value: Value, opts?: { forceOverridePendingVideo?: boolean }) => Promise<boolean>;
  clearPinnedFeedback: (settingId: string) => void;
  applyHudEdgePositions: (x: number, y: number) => Promise<boolean>;
  applyPendingVideo: (game: GameId) => Promise<void>;
  discardPendingVideo: (game: GameId) => void;
  setHistoryOpen: (open: boolean) => void;
  loadHistory: (game: GameId) => Promise<void>;
  undo: (batch: HistoryBatch) => Promise<void>;
  undoById: (game: GameId, batchId: string) => Promise<void>;
  restageHistoryBatch: (batch: HistoryBatch) => Promise<void>;
  togglePin: (game: GameId, settingId: string) => Promise<void>;
  toggleLock: (game: GameId, settingId: string) => Promise<void>;
  stage: (game: GameId, recs: Recommendation[] | RelevantCard[], source: "ai" | "fallback" | "rules", runId: string | null, title: string) => Promise<void>;
  applyProposal: (proposal: Proposal, itemIds: string[], opts?: { overridePendingVideo?: boolean }) => Promise<boolean>;
  rejectProposal: (proposal: Proposal, itemIds?: string[], reason?: string) => Promise<void>;
  editProposalItem: (proposal: Proposal, itemId: string, value: Value) => Promise<void>;
  rebaseItem: (proposal: Proposal, itemId: string) => Promise<void>;
  sendChat: (game: GameId, text: string) => Promise<void>;
  cancelRun: (game: GameId) => Promise<void>;
  clearChat: (game: GameId) => Promise<void>;
  refreshRelevantNow: (game: GameId) => Promise<void>;
  dismissCard: (game: GameId, settingId: string, reason?: string) => Promise<void>;
  markDiscoverChecked: (game: GameId, checkId: string) => Promise<void>;
  revisitOnboarding: (game: GameId) => Promise<void>;
  setCardOpen: (cardId: string, open: boolean) => void;
  markDiscoverSeen: (game: GameId) => void;
  triggerContext: (game: GameId, eventType: string | null) => Promise<void>;
  loadProfile: () => Promise<void>;
  confirmPreference: (s: PreferenceSuggestion, scope: "session" | "durable", dimension?: string) => Promise<boolean>;
  addPreference: (game: GameId, dimension: string, direction: "prioritize" | "deprioritize", scope: "session" | "durable", note?: string) => Promise<void>;
  removePreference: (id: string) => Promise<void>;
  addPersonalFact: (game: GameId, factKey: string, valueText: string, sourceSettingId?: string, note?: string) => Promise<void>;
  removePersonalFact: (id: string) => Promise<void>;
  undoMemoryUpdate: (update: AppliedMemoryUpdate) => Promise<void>;
  navigateCrossGame: (targetGame: GameId, settingId: string) => Promise<void>;
  clearGoals: (game: GameId) => Promise<void>;
  loadTraces: () => Promise<void>;
  reset: (scenario: string, mode: "full" | "ai_only") => Promise<void>;
  popOutWorkspace: (game: GameId) => boolean;
  focusDetachedWorkspace: () => void;
  recallDetachedWorkspace: () => Promise<void>;
}

let toastSeq = 1;
let highlightSeq = 1;
let syncUnsubscribe: (() => void) | null = null;
let detachedMonitorTimer: number | null = null;
let detachedWindowRef: Window | null = null;

/** Values as currently shown in the menu: stored values + unapplied explicit edits + derived presets. */
export function computeDisplayValues(
  state: GameState | undefined,
  pending: Record<string, Value> | undefined,
  byId: Record<string, Setting> | undefined,
  byKey: Record<string, Setting> | undefined,
): Record<string, Value> {
  const out: Record<string, Value> = {};
  if (!state) return out;
  for (const [id, entry] of Object.entries(state.values)) out[id] = entry.value;
  Object.assign(out, pending ?? {});
  for (const s of Object.values(byId ?? {})) {
    if (s.controlType === "preset") out[s.id] = derivePreset(s, byKey ?? {}, out);
  }
  return out;
}

function errText(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  return err instanceof Error ? err.message : String(err);
}

function defaultNav(catalog: Catalog): NavState {
  const tab = catalog.menu.find((t) => t.simulated) ?? catalog.menu[0];
  const sub = tab.subtabs.find((s) => s.simulated) ?? tab.subtabs[0];
  return { tabId: tab.id, subtabId: sub.id };
}

export const useAppStore = create<AppState>((set, get) => ({
  ready: false,
  fatal: null,
  session: null,
  modelStatus: null,
  catalogs: {},
  byId: {},
  byKey: {},
  states: {},
  proposals: {},
  history: {},
  relevantNow: {},
  chat: {},
  runs: {},
  traces: [],
  profile: null,
  contextTypes: [],
  scenarios: [],
  crosshairProfiles: [],
  nav: { valorant: { tabId: "video", subtabId: "graphics_quality" }, cs2: { tabId: "video", subtabId: "advanced" } },
  highlight: null,
  pendingVideo: {},
  pinnedFeedback: {},
  historyOpen: false,
  workspaceOpen: false,
  workspaceTab: "changes",
  trayOpen: false,
  detachedWorkspaceActive: false,
  experimenterMode: readInitialExperimenterMode(),
  scopeOverride: "auto",
  openCards: {},
  seenDiscoverIds: { valorant: [], cs2: [] },
  toasts: [],
  composerPrefill: null,

  prefillComposer: (game, text) => set({ composerPrefill: { game, text, nonce: highlightSeq++ } }),

  toast: (kind, text) => {
    const id = toastSeq++;
    set((s) => ({ toasts: [...s.toasts.slice(-3), { id, kind, text }] }));
    window.setTimeout(() => get().dismissToast(id), kind === "error" ? 9000 : 5000);
  },
  dismissToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),

  setExperimenterMode: (on) => {
    set({ experimenterMode: on });
    try {
      if (typeof window !== "undefined") window.sessionStorage.setItem("csc2524.experimenter", on ? "1" : "0");
    } catch {
      // ignore storage failure
    }
  },

  setScopeOverride: (scopeOverride) => set({ scopeOverride }),

  setWorkspaceOpen: (open) => set({ workspaceOpen: open, trayOpen: open }),
  setWorkspaceTab: (workspaceTab) => set({ workspaceTab }),
  openWorkspace: (tab = "changes") => set({ workspaceOpen: true, trayOpen: true, workspaceTab: tab }),
  setTrayOpen: (open) => set({ workspaceOpen: open, trayOpen: open }),

  init: async () => {
    try {
      const [session, scenarios, contextTypes] = await Promise.all([api.session(), api.scenarios(), api.contextEventTypes()]);
      const params = typeof window !== "undefined" ? new URLSearchParams(window.location.search) : null;
      const paramGame = params?.get("game");
      const activeGame: GameId = paramGame === "cs2" || paramGame === "valorant" ? paramGame : session.selectedGame;
      syncWorkspaceUrlGame(activeGame);
      set({ session: activeGame !== session.selectedGame ? { ...session, selectedGame: activeGame } : session, scenarios, contextTypes });
      await Promise.all(GAMES.map((g) => get().loadGame(g)));
      void get().loadCrosshairProfiles();
      set({ ready: true });
      void get().refreshModelStatus();
      if (session.condition === "adaptive") {
        await get().refreshAdaptive(activeGame);
      }
      if (!syncUnsubscribe && typeof window !== "undefined") {
        const isSelfDetached = new URLSearchParams(window.location.search).get("view") === "workspace";
        if (!isSelfDetached && isDetachedLeaseAlive()) {
          set({ detachedWorkspaceActive: true });
          broadcastSync({ type: "workspace_ping" });
        }
        const ensureMonitor = () => {
          if (detachedMonitorTimer !== null || isSelfDetached) return;
          detachedMonitorTimer = window.setInterval(() => {
            if (!get().detachedWorkspaceActive) return;
            const refClosed = detachedWindowRef !== null && detachedWindowRef.closed;
            if (refClosed || (!isDetachedLeaseAlive() && detachedWindowRef === null)) {
              detachedWindowRef = null;
              clearDetachedLease();
              set({ detachedWorkspaceActive: false });
              const cur = get().session?.selectedGame;
              if (cur) {
                void get().refreshState(cur);
                if (get().session?.condition === "adaptive") void get().refreshAdaptive(cur);
              }
            }
          }, 1200);
        };
        if (!isSelfDetached) ensureMonitor();

        syncUnsubscribe = subscribeSync(
          (msg) => {
            if (msg.type === "state_changed") {
              void api.session().then((fresh) => {
                set({ session: fresh });
                syncWorkspaceUrlGame(fresh.selectedGame);
                const targets = fresh.selectedGame && fresh.selectedGame !== msg.game
                  ? [msg.game, fresh.selectedGame]
                  : [msg.game];
                for (const g of targets) {
                  void get().refreshState(g);
                  if (fresh.condition === "adaptive") void get().refreshAdaptive(g);
                }
                if (targets.includes("valorant")) void get().loadCrosshairProfiles();
              }).catch(() => undefined);
            } else if (msg.type === "navigate_setting") {
              const isDetached = new URLSearchParams(window.location.search).get("view") === "workspace";
              if (!isDetached) {
                get().goToSetting(msg.game, msg.settingId, "assistant");
                window.focus();
              }
            } else if (msg.type === "open_workspace_tab") {
              set({ workspaceTab: msg.tab, workspaceOpen: true, trayOpen: true });
              if (msg.game) void get().refreshAdaptive(msg.game);
            } else if (msg.type === "workspace_attached" || msg.type === "workspace_heartbeat") {
              if (!isSelfDetached) {
                if (!get().detachedWorkspaceActive) {
                  set({ detachedWorkspaceActive: true });
                }
                ensureMonitor();
              }
            } else if (msg.type === "workspace_closed") {
              if (!isSelfDetached && get().detachedWorkspaceActive) {
                detachedWindowRef = null;
                set({ detachedWorkspaceActive: false });
                const cur = get().session?.selectedGame;
                if (cur) {
                  void get().refreshState(cur);
                  if (get().session?.condition === "adaptive") void get().refreshAdaptive(cur);
                }
              }
            }
          },
          () => {
            const cur = get().session?.selectedGame;
            if (cur) {
              void get().refreshState(cur);
              if (get().session?.condition === "adaptive") void get().refreshAdaptive(cur);
              if (cur === "valorant") void get().loadCrosshairProfiles();
            }
            if (!isSelfDetached && get().detachedWorkspaceActive && !isDetachedLeaseAlive() && (!detachedWindowRef || detachedWindowRef.closed)) {
              detachedWindowRef = null;
              set({ detachedWorkspaceActive: false });
            }
          },
        );
      }
    } catch (err) {
      set({ fatal: errText(err) });
    }
  },

  loadGame: async (game) => {
    const [catalog, state] = await Promise.all([api.catalog(game), api.state(game)]);
    const byId: Record<string, Setting> = {};
    const byKey: Record<string, Setting> = {};
    for (const s of catalog.settings) {
      byId[s.id] = s;
      byKey[s.key] = s;
    }
    set((s) => ({
      catalogs: { ...s.catalogs, [game]: catalog },
      byId: { ...s.byId, [game]: byId },
      byKey: { ...s.byKey, [game]: byKey },
      states: { ...s.states, [game]: state },
      nav: s.catalogs[game] ? s.nav : { ...s.nav, [game]: s.nav[game] ?? defaultNav(catalog) },
    }));
  },

  refreshState: async (game) => {
    const state = await api.state(game);
    set((s) => ({ states: { ...s.states, [game]: state } }));
    if (get().historyOpen) void get().loadHistory(game);
  },

  refreshAdaptive: async (game) => {
    const session = get().session;
    if (!session || session.condition !== "adaptive") return;
    const [proposals, chat, profile] = await Promise.all([
      api.proposals(game, "pending"),
      api.thread(game),
      api.profile(game),
    ]);
    set((s) => ({ proposals: { ...s.proposals, [game]: proposals }, chat: { ...s.chat, [game]: chat }, profile }));
    try {
      let rn = await api.relevantNow(game);
      const anyCardOpen = Object.values(get().openCards).some(Boolean);
      const existingRn = get().relevantNow[game];
      if (!anyCardOpen && rn.updateAvailable) {
        try {
          rn = await api.refreshRelevantNow(game);
        } catch {
          // fall back to current rn if auto-sync fails
        }
      }
      const preserveStable = anyCardOpen && existingRn && existingRn.items.length > 0;
      set((s) => ({
        relevantNow: {
          ...s.relevantNow,
          [game]: preserveStable
            ? {
                ...existingRn,
                updateAvailable: true,
                onboardingStatus: rn.onboardingStatus,
                canRevisitOnboarding: rn.canRevisitOnboarding,
                context: rn.context,
              }
            : rn,
        },
      }));
    } catch (err) {
      get().toast("error", errText(err));
    }
  },

  refreshModelStatus: async (force = false) => {
    try {
      set({ modelStatus: await api.modelStatus(force) });
    } catch {
      set({ modelStatus: null });
    }
  },

  loadCrosshairProfiles: async () => {
    try {
      const profiles = await api.crosshairProfiles();
      set({ crosshairProfiles: profiles });
    } catch {
      // ignore if backend not ready yet
    }
  },

  createCrosshairProfile: async (name, copyFromCurrent = true) => {
    try {
      const res = await api.createCrosshairProfile(name, copyFromCurrent);
      set({ crosshairProfiles: res.profiles });
      await get().refreshState("valorant");
      broadcastSync({ type: "state_changed", game: "valorant" });
      get().toast("success", `Created crosshair profile “${name}”.`);
      return true;
    } catch (err) {
      get().toast("error", errText(err));
      return false;
    }
  },

  selectCrosshairProfile: async (profileId) => {
    try {
      const res = await api.selectCrosshairProfile(profileId);
      set({ crosshairProfiles: res.profiles });
      await get().refreshState("valorant");
      broadcastSync({ type: "state_changed", game: "valorant" });
    } catch (err) {
      get().toast("error", errText(err));
    }
  },

  renameCrosshairProfile: async (profileId, name) => {
    try {
      const res = await api.renameCrosshairProfile(profileId, name);
      set({ crosshairProfiles: res.profiles });
      broadcastSync({ type: "state_changed", game: "valorant" });
    } catch (err) {
      get().toast("error", errText(err));
    }
  },

  deleteCrosshairProfile: async (profileId) => {
    try {
      const res = await api.deleteCrosshairProfile(profileId);
      set({ crosshairProfiles: res.profiles });
      await get().refreshState("valorant");
      broadcastSync({ type: "state_changed", game: "valorant" });
    } catch (err) {
      get().toast("error", errText(err));
    }
  },

  importCrosshairCode: async (code, name) => {
    try {
      const res = await api.importCrosshairCode(code, name);
      set({ crosshairProfiles: res.profiles });
      await get().refreshState("valorant");
      broadcastSync({ type: "state_changed", game: "valorant" });
      get().toast("success", "Imported crosshair profile.");
      return null;
    } catch (err) {
      return errText(err);
    }
  },

  exportCrosshairCode: async (profileId) => {
    try {
      return await api.exportCrosshairCode(profileId);
    } catch (err) {
      get().toast("error", errText(err));
      return null;
    }
  },

  switchGame: async (game) => {
    const session = await api.updateSession({ selectedGame: game });
    syncWorkspaceUrlGame(game);
    set({ session, highlight: null });
    await get().refreshState(game);
    await get().refreshAdaptive(game);
    if (game === "valorant") void get().loadCrosshairProfiles();
    broadcastSync({ type: "state_changed", game });
  },

  setCondition: async (condition) => {
    const session = await api.updateSession({ condition });
    set({ session, highlight: null, workspaceOpen: false, trayOpen: false });
    await get().refreshState(session.selectedGame);
    await get().refreshAdaptive(session.selectedGame);
    broadcastSync({ type: "state_changed", game: session.selectedGame });
    get().toast("info", condition === "adaptive" ? "Condition B — adaptive augmentation" : "Condition A — static baseline");
  },

  setAiMode: async (mode) => {
    const session = await api.updateSession({ aiMode: mode });
    set({ session });
    await get().refreshModelStatus(true);
    broadcastSync({ type: "state_changed", game: session.selectedGame });
  },

  setAdaptation: async (on) => {
    const session = await api.updateSession({ adaptationEnabled: on });
    set({ session });
    await get().refreshAdaptive(session.selectedGame);
    broadcastSync({ type: "state_changed", game: session.selectedGame });
  },

  navigate: (game, tabId, subtabId) => {
    const catalog = get().catalogs[game];
    if (!catalog) return;
    if (game === "cs2" && tabId === "promoted") {
      set((s) => ({ nav: { ...s.nav, cs2: { tabId: "promoted", subtabId: "promoted" } } }));
      return;
    }
    const tab = catalog.menu.find((t) => t.id === tabId);
    if (!tab) return;
    const sub = subtabId ?? (tab.subtabs.find((s) => s.simulated) ?? tab.subtabs[0]).id;
    set((s) => ({ nav: { ...s.nav, [game]: { tabId, subtabId: sub } } }));
  },

  goToSetting: (game, settingId, reason) => {
    const setting = get().byId[game]?.[settingId];
    if (!setting) return;
    const catalog = get().catalogs[game]!;
    const tab = catalog.menu.find((t) => t.id === setting.tabId)!;
    const subtabId = tab.subtabMode === "anchors" ? tab.subtabs[0].id : setting.subtabId;
    set((s) => ({
      nav: { ...s.nav, [game]: { tabId: setting.tabId, subtabId } },
      highlight: { game, settingId, nonce: highlightSeq++, reason },
    }));
    if (get().session?.selectedGame !== game) void get().switchGame(game);
    window.setTimeout(() => {
      const el = document.getElementById(rowDomId(settingId));
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        el.focus({ preventScroll: true });
      }
    }, 60);
  },

  requestFocusInMainWindow: (game, settingId, reason = "assistant") => {
    broadcastSync({ type: "navigate_setting", game, settingId });
    const isDetached =
      typeof window !== "undefined" && new URLSearchParams(window.location.search).get("view") === "workspace";
    if (isDetached) {
      try {
        window.opener?.focus?.();
      } catch {
        // browsers may restrict cross-window focus
      }
      const label = get().byId[game]?.[settingId]?.exactLabel ?? "setting";
      get().toast("info", `Highlighted ${label} in the main settings window.`);
      return;
    }
    get().goToSetting(game, settingId, reason);
  },

  displayValues: (game) => {
    const state = get().states[game];
    const out: Record<string, Value> = {};
    if (!state) return out;
    for (const [id, entry] of Object.entries(state.values)) out[id] = entry.value;
    const pending = get().pendingVideo[game] ?? {};
    Object.assign(out, pending);
    const byKey = get().byKey[game] ?? {};
    for (const s of Object.values(get().byId[game] ?? {})) {
      if (s.controlType === "preset") out[s.id] = derivePreset(s, byKey, out);
    }
    return out;
  },

  changeSetting: async (game, settingId, value) => {
    const setting = get().byId[game]?.[settingId];
    const state = get().states[game];
    if (!setting || !state) return;
    if (setting.applyMode === "explicit") {
      // CS2 video settings: like the real menu, edits stay pending until "Apply Changes".
      const pending = { ...(get().pendingVideo[game] ?? {}) };
      const members = setting.controlType === "preset" && setting.preset ? setting.preset.values[String(value)] : null;
      const updates: Record<string, Value> = members
        ? Object.fromEntries(Object.entries(members).map(([k, v]) => [get().byKey[game]![k].id, v]))
        : { [settingId]: value };
      for (const [id, v] of Object.entries(updates)) {
        if (sameValue(state.values[id]?.value, v)) delete pending[id];
        else pending[id] = v;
      }
      set((s) => ({ pendingVideo: { ...s.pendingVideo, [game]: pending } }));
      return;
    }
    try {
      const batch = await api.changeSetting(game, settingId, value, state.values[settingId]?.revision);
      if (!batch.noop) {
        const ev = batch.events[0];
        get().toast("success", `${setting.exactLabel}: ${ev?.oldDisplay ?? ""} → ${ev?.newDisplay ?? displayValue(setting, value)} (saved, undoable)`);
      }
      broadcastSync({ type: "state_changed", game });
    } catch (err) {
      get().toast("error", errText(err));
    }
    await get().refreshState(game);
    await get().refreshAdaptive(game);
    if (game === "valorant" && settingId.startsWith("val.crosshair.")) void get().loadCrosshairProfiles();
  },

  clearPinnedFeedback: (settingId) =>
    set((s) => {
      const next = { ...s.pinnedFeedback };
      delete next[settingId];
      return { pinnedFeedback: next };
    }),

  changePinnedSetting: async (game, settingId, value, opts) => {
    const setting = get().byId[game]?.[settingId];
    const state = get().states[game];
    if (!setting || !state) return false;
    // CS2 Video guard: never silently overwrite unapplied CS2 video edits unless user confirms.
    const pendingForGame = get().pendingVideo[game] ?? {};
    if (game === "cs2" && setting.applyMode === "explicit" && pendingForGame[settingId] !== undefined && !opts?.forceOverridePendingVideo) {
      set((s) => ({
        pinnedFeedback: {
          ...s.pinnedFeedback,
          [settingId]: {
            status: "conflict",
            message: `Unapplied Video menu draft (${displayValue(setting, pendingForGame[settingId])}) conflicts with saving immediately.`,
          },
        },
      }));
      return false;
    }
    try {
      const batch = await api.changeSetting(game, settingId, value, state.values[settingId]?.revision);
      if (pendingForGame[settingId] !== undefined) {
        const nextPending = { ...pendingForGame };
        delete nextPending[settingId];
        set((s) => ({ pendingVideo: { ...s.pendingVideo, [game]: nextPending } }));
      }
      set((s) => ({
        pinnedFeedback: {
          ...s.pinnedFeedback,
          [settingId]: {
            status: "saved",
            message: batch.noop ? "Unchanged" : "Saved",
            batchId: batch.batchId ?? undefined,
          },
        },
      }));
      await get().refreshState(game);
      await get().refreshAdaptive(game);
      if (game === "valorant" && settingId.startsWith("val.crosshair.")) void get().loadCrosshairProfiles();
      broadcastSync({ type: "state_changed", game });
      return true;
    } catch (err) {
      set((s) => ({
        pinnedFeedback: {
          ...s.pinnedFeedback,
          [settingId]: { status: "error", message: errText(err) },
        },
      }));
      return false;
    }
  },

  applyHudEdgePositions: async (x, y) => {
    const state = get().states.cs2;
    if (!state) return false;
    try {
      const batch = await api.changeBatch(
        "cs2",
        [
          { settingId: "cs2.video.hud_edge_x", value: x, expectedRevision: state.values["cs2.video.hud_edge_x"]?.revision },
          { settingId: "cs2.video.hud_edge_y", value: y, expectedRevision: state.values["cs2.video.hud_edge_y"]?.revision },
        ],
        "HUD Edge Positions (Done)",
      );
      if (!batch.noop) {
        get().toast("success", "HUD Edge Positions saved.");
      }
      await get().refreshState("cs2");
      await get().refreshAdaptive("cs2");
      broadcastSync({ type: "state_changed", game: "cs2" });
      return true;
    } catch (err) {
      get().toast("error", errText(err));
      return false;
    }
  },

  applyPendingVideo: async (game) => {
    const pending = get().pendingVideo[game] ?? {};
    const state = get().states[game];
    if (!state || Object.keys(pending).length === 0) return;
    try {
      const changes = Object.entries(pending).map(([settingId, value]) => ({ settingId, value, expectedRevision: state.values[settingId]?.revision }));
      const batch = await api.changeBatch(game, changes, "Video settings (Apply Changes)");
      set((s) => ({ pendingVideo: { ...s.pendingVideo, [game]: {} } }));
      get().toast("success", `Applied ${batch.events.length} video setting change(s).`);
      broadcastSync({ type: "state_changed", game });
    } catch (err) {
      get().toast("error", errText(err));
    }
    await get().refreshState(game);
    await get().refreshAdaptive(game);
  },

  discardPendingVideo: (game) => set((s) => ({ pendingVideo: { ...s.pendingVideo, [game]: {} } })),

  setHistoryOpen: (open) => {
    set({ historyOpen: open });
    const game = get().session?.selectedGame;
    if (open && game) void get().loadHistory(game);
  },

  loadHistory: async (game) => {
    const history = await api.history(game);
    set((s) => ({ history: { ...s.history, [game]: history } }));
  },

  undo: async (batch) => {
    try {
      await api.undo(batch.batchId);
      get().toast("success", `Undid: ${batch.label ?? batch.sourceLabel}`);
      broadcastSync({ type: "state_changed", game: batch.game });
    } catch (err) {
      get().toast("error", errText(err));
    }
    await get().refreshState(batch.game);
    await get().loadHistory(batch.game);
    await get().refreshAdaptive(batch.game);
    if (batch.game === "valorant") void get().loadCrosshairProfiles();
  },

  undoById: async (game, batchId) => {
    try {
      await api.undo(batchId);
      get().toast("success", "Undid change.");
      broadcastSync({ type: "state_changed", game });
    } catch (err) {
      get().toast("error", errText(err));
    }
    await get().refreshState(game);
    await get().loadHistory(game);
    await get().refreshAdaptive(game);
    if (game === "valorant") void get().loadCrosshairProfiles();
  },

  restageHistoryBatch: async (batch) => {
    try {
      const res = await api.restageHistory(batch.batchId);
      await get().refreshAdaptive(batch.game);
      if (res.stagedCount > 0) {
        set({ workspaceOpen: true, trayOpen: true, workspaceTab: "changes", historyOpen: false });
        if (get().detachedWorkspaceActive) {
          broadcastSync({ type: "open_workspace_tab", tab: "changes", game: batch.game });
        }
        get().toast("info", res.message);
      } else {
        get().toast("info", res.message);
      }
      broadcastSync({ type: "state_changed", game: batch.game });
    } catch (err) {
      get().toast("error", errText(err));
    }
  },

  togglePin: async (game, settingId) => {
    const pinned = get().states[game]?.pins.includes(settingId) ?? false;
    try {
      await api.setPin(game, settingId, !pinned);
      broadcastSync({ type: "state_changed", game });
    } catch (err) {
      get().toast("error", errText(err));
    }
    await get().refreshState(game);
  },

  toggleLock: async (game, settingId) => {
    const locked = get().states[game]?.locks.includes(settingId) ?? false;
    try {
      await api.setLock(game, settingId, !locked);
      const label = get().byId[game]?.[settingId]?.exactLabel ?? settingId;
      get().toast("info", locked ? `${label} unlocked — suggestions may include it again.` : `${label} locked from AI changes.`);
      broadcastSync({ type: "state_changed", game });
    } catch (err) {
      get().toast("error", errText(err));
    }
    await get().refreshState(game);
    await get().refreshAdaptive(game);
  },

  stage: async (game, recs, source, runId, title) => {
    if (recs.length === 0) return;
    try {
      const items = recs.map((r) =>
        "proposedValue" in r
          ? { settingId: r.settingId, proposedValue: r.proposedValue, why: r.whyForGoal, tradeoff: r.tradeoff, confidence: r.confidence,
              dimensions: r.dimension ? [r.dimension] : [], basedOn: r.basedOn }
          : { settingId: r.settingId, proposedValue: r.targetValue, why: r.why, tradeoff: r.tradeoff, confidence: r.whyBasis === "official" ? "medium" : "low",
              dimensions: [r.dimension], basedOn: r.basedOn.join("; ") },
      );
      const proposal = await api.createProposal({ game, source, runId, title, items });
      const blocked = proposal.items.filter((i) => i.status === "blocked");
      if (blocked.length) get().toast("warning", blocked.map((b) => b.statusReason).join(" "));
      else get().toast("info", `Prepared ${proposal.items.length} change(s) for review — nothing applied yet.`);
      set({ workspaceOpen: true, trayOpen: true, workspaceTab: "changes" });
      broadcastSync({ type: "state_changed", game });
    } catch (err) {
      get().toast("error", errText(err));
    }
    await get().refreshAdaptive(game);
  },

  applyProposal: async (proposal, itemIds, opts) => {
    const pending = get().pendingVideo[proposal.game] ?? {};
    const clash = proposal.items.filter((i) => itemIds.includes(i.id) && pending[i.settingId] !== undefined);
    if (clash.length && !opts?.overridePendingVideo) {
      get().toast("warning", `You have unapplied video edits for ${clash.map((c) => c.label).join(", ")}. Apply or discard them first.`);
      return false;
    }
    let ok = false;
    try {
      const res = await api.applyProposal(proposal.id, itemIds);
      if (clash.length && opts?.overridePendingVideo) {
        const nextPending = { ...pending };
        for (const c of clash) delete nextPending[c.settingId];
        set((s) => ({ pendingVideo: { ...s.pendingVideo, [proposal.game]: nextPending } }));
      }
      get().toast("success", `Applied ${res.batch.events.length} change(s). You can undo them from History.`);
      ok = true;
      broadcastSync({ type: "state_changed", game: proposal.game });
    } catch (err) {
      get().toast("error", errText(err));
    }
    await get().refreshState(proposal.game);
    await get().refreshAdaptive(proposal.game);
    if (proposal.game === "valorant") void get().loadCrosshairProfiles();
    return ok;
  },

  rejectProposal: async (proposal, itemIds, reason) => {
    try {
      await api.rejectProposal(proposal.id, itemIds, reason);
      get().toast("info", "Rejected — no settings were changed.");
      broadcastSync({ type: "state_changed", game: proposal.game });
    } catch (err) {
      get().toast("error", errText(err));
    }
    await get().refreshAdaptive(proposal.game);
  },

  editProposalItem: async (proposal, itemId, value) => {
    try {
      const updated = await api.editItem(proposal.id, itemId, value);
      set((s) => ({ proposals: { ...s.proposals, [proposal.game]: (s.proposals[proposal.game] ?? []).map((p) => (p.id === updated.id ? updated : p)) } }));
      broadcastSync({ type: "state_changed", game: proposal.game });
    } catch (err) {
      get().toast("error", errText(err));
    }
  },

  rebaseItem: async (proposal, itemId) => {
    try {
      await api.rebaseItem(proposal.id, itemId);
      broadcastSync({ type: "state_changed", game: proposal.game });
    } catch (err) {
      get().toast("error", errText(err));
    }
    await get().refreshAdaptive(proposal.game);
  },

  sendChat: async (game, text) => {
    const nav = get().nav[game];
    const catalog = get().catalogs[game];
    const tab = catalog?.menu.find((t) => t.id === nav.tabId);
    const sub = tab?.subtabs.find((s) => s.id === nav.subtabId);
    const path = [tab?.label, tab?.subtabMode === "pages" ? sub?.label : null].filter(Boolean).join(" > ");
    const scope = get().scopeOverride;
    try {
      const run = await api.chat(game, text, { tabId: nav.tabId, subtabId: nav.subtabId, path }, scope);
      set((s) => ({ runs: { ...s.runs, [game]: run } }));
      const thread = await api.thread(game);
      // Avoid split-brain render where the assistant message shows before staged proposals are fetched.
      const safeThread = thread.filter((m) => !(m.role === "assistant" && m.runId === run.runId));
      set((s) => ({ chat: { ...s.chat, [game]: safeThread } }));
      const poll = async () => {
        const status = await api.run(run.runId);
        set((s) => ({ runs: { ...s.runs, [game]: status } }));
        if (status.status === "running") {
          window.setTimeout(poll, 350);
          return;
        }
        set((s) => ({ runs: { ...s.runs, [game]: null } }));
        await get().refreshAdaptive(game);
        broadcastSync({ type: "state_changed", game });
        const res = status.result;
        if (res?.navigateTo && res.intent === "navigate") {
          get().goToSetting(game, res.navigateTo.settingId, "assistant");
        } else if (res?.stagedCount && res.stagedCount > 0) {
          get().toast("info", `${res.stagedCount} change(s) ready to review — nothing has been applied.`);
        }
      };
      window.setTimeout(poll, 60);
    } catch (err) {
      get().toast("error", errText(err));
    }
  },

  cancelRun: async (game) => {
    const run = get().runs[game];
    if (!run) return;
    try {
      await api.cancelRun(run.runId);
    } catch (err) {
      get().toast("error", errText(err));
    }
    set((s) => ({ runs: { ...s.runs, [game]: null } }));
    await get().refreshAdaptive(game);
  },

  clearChat: async (game) => {
    await api.clearThread(game);
    await get().refreshAdaptive(game);
    broadcastSync({ type: "state_changed", game });
  },

  refreshRelevantNow: async (game) => {
    try {
      const rn = await api.refreshRelevantNow(game);
      set((s) => ({ relevantNow: { ...s.relevantNow, [game]: rn }, openCards: {} }));
      broadcastSync({ type: "state_changed", game });
    } catch (err) {
      get().toast("error", errText(err));
    }
  },

  dismissCard: async (game, settingId, reason) => {
    try {
      const rn = await api.dismissCard(game, settingId, reason);
      set((s) => ({ relevantNow: { ...s.relevantNow, [game]: rn } }));
      broadcastSync({ type: "state_changed", game });
    } catch (err) {
      get().toast("error", errText(err));
    }
  },

  markDiscoverChecked: async (game, checkId) => {
    try {
      const rn = await api.markDiscoverChecked(game, checkId);
      set((s) => ({ relevantNow: { ...s.relevantNow, [game]: rn } }));
      broadcastSync({ type: "state_changed", game });
    } catch (err) {
      get().toast("error", errText(err));
    }
  },

  revisitOnboarding: async (game) => {
    try {
      const rn = await api.revisitOnboarding(game);
      set((s) => ({ relevantNow: { ...s.relevantNow, [game]: rn }, openCards: {} }));
      broadcastSync({ type: "state_changed", game });
    } catch (err) {
      get().toast("error", errText(err));
    }
  },

  setCardOpen: (cardId, open) => {
    set((s) => ({ openCards: { ...s.openCards, [cardId]: open } }));
    if (!open) {
      const nextOpen = get().openCards;
      const anyOpen = Object.values(nextOpen).some(Boolean);
      const game = get().session?.selectedGame;
      const rn = game ? get().relevantNow[game] : undefined;
      if (!anyOpen && game && rn?.updateAvailable) {
        void get().refreshRelevantNow(game);
      }
    }
  },

  markDiscoverSeen: (game) => {
    const rn = get().relevantNow[game];
    const ids = (rn?.items ?? [])
      .filter((c) => c.state === "suggested" || c.state === "changed")
      .map((c) => c.cardId || c.settingId);
    set((s) => ({
      seenDiscoverIds: {
        ...s.seenDiscoverIds,
        [game]: Array.from(new Set([...(s.seenDiscoverIds[game] ?? []), ...ids])),
      },
    }));
  },

  triggerContext: async (game, eventType) => {
    try {
      const rn = await api.setContextEvent(game, eventType);
      set((s) => ({ relevantNow: { ...s.relevantNow, [game]: rn }, openCards: {} }));
      await get().loadProfile();
      broadcastSync({ type: "state_changed", game });
    } catch (err) {
      get().toast("error", errText(err));
    }
  },

  loadProfile: async () => set({ profile: await api.profile() }),

  confirmPreference: async (s, scope, dimension) => {
    try {
      await api.addPreference({ dimension: dimension ?? s.dimension, direction: s.direction, scope, source: "chat_confirmed", game: s.game, note: s.quote });
      get().toast("success", scope === "session" ? "Saved for this session only." : "Saved as a lasting preference (applies across games).");
      broadcastSync({ type: "state_changed", game: s.game });
      await get().refreshAdaptive(s.game);
      return true;
    } catch (err) {
      get().toast("error", errText(err));
      return false;
    }
  },

  addPreference: async (game, dimension, direction, scope, note) => {
    try {
      await api.addPreference({ dimension, direction, scope, source: "user_explicit", game, note });
      broadcastSync({ type: "state_changed", game });
    } catch (err) {
      get().toast("error", errText(err));
    }
    await get().refreshAdaptive(game);
  },

  removePreference: async (id) => {
    await api.removePreference(id);
    const game = get().session?.selectedGame;
    if (game) {
      await get().refreshAdaptive(game);
      broadcastSync({ type: "state_changed", game });
    }
  },

  addPersonalFact: async (game, factKey, valueText, sourceSettingId, note) => {
    try {
      await api.addPersonalFact({
        factKey,
        valueText,
        originGame: game,
        sourceSettingId,
        source: "user_explicit",
        note,
      });
      await get().refreshAdaptive(game);
      broadcastSync({ type: "state_changed", game });
      get().toast("success", "Saved personal setup preference.");
    } catch (err) {
      get().toast("error", errText(err));
    }
  },

  removePersonalFact: async (id) => {
    await api.removePersonalFact(id);
    const game = get().session?.selectedGame;
    if (game) {
      await get().refreshAdaptive(game);
      broadcastSync({ type: "state_changed", game });
    }
  },

  undoMemoryUpdate: async (update) => {
    try {
      if (update.kind === "preference") {
        await api.removePreference(update.id);
      } else {
        await api.removePersonalFact(update.id);
      }
      const game = update.game || update.originGame || get().session?.selectedGame;
      if (game) {
        await get().refreshAdaptive(game);
        broadcastSync({ type: "state_changed", game });
      }
      get().toast("info", `Undid saved item: ${update.label}`);
    } catch (err) {
      get().toast("error", errText(err));
    }
  },

  navigateCrossGame: async (targetGame, settingId) => {
    const cur = get().session?.selectedGame;
    if (cur !== targetGame) {
      await get().switchGame(targetGame);
    }
    get().goToSetting(targetGame, settingId, "assistant");
  },

  clearGoals: async (game) => {
    await api.clearSessionGoals(game);
    await get().refreshAdaptive(game);
    broadcastSync({ type: "state_changed", game });
  },

  loadTraces: async () => set({ traces: await api.traces() }),

  reset: async (scenario, mode) => {
    try {
      const res = await api.reset(scenario, mode);
      set({
        session: res.session,
        pendingVideo: {},
        pinnedFeedback: {},
        highlight: null,
        relevantNow: {},
        chat: {},
        proposals: {},
        history: {},
        openCards: {},
      });
      await Promise.all(GAMES.map((g) => get().refreshState(g)));
      await get().refreshAdaptive(res.session.selectedGame);
      void get().loadCrosshairProfiles();
      broadcastSync({ type: "state_changed", game: res.session.selectedGame });
      get().toast("success", `Reset to “${scenario}” (${mode === "full" ? "full experimental state" : "AI session state only"}). Backup saved.`);
    } catch (err) {
      get().toast("error", errText(err));
    }
  },

  popOutWorkspace: (game) => {
    const url = `?view=workspace&game=${game}`;
    const win = window.open(url, "csc2524-adaptive-workspace", "width=1120,height=820");
    if (!win) {
      get().toast("warning", "Pop-up blocked — use 'Open in new tab ↗' or allow pop-ups.");
      return false;
    }
    detachedWindowRef = win;
    set({ detachedWorkspaceActive: true });
    win.focus?.();
    return true;
  },

  focusDetachedWorkspace: () => {
    try {
      detachedWindowRef?.focus?.();
    } catch {
      // ignore focus restrictions
    }
    broadcastSync({ type: "workspace_focus_request" });
  },

  recallDetachedWorkspace: async () => {
    clearDetachedLease();
    broadcastSync({ type: "workspace_recall" });
    try {
      detachedWindowRef?.close?.();
    } catch {
      // ignore close restrictions
    }
    detachedWindowRef = null;
    set({ detachedWorkspaceActive: false });
    const cur = get().session?.selectedGame;
    if (cur) {
      await get().refreshState(cur);
      if (get().session?.condition === "adaptive") await get().refreshAdaptive(cur);
    }
  },
}));
