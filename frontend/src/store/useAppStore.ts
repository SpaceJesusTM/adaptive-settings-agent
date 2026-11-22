import { create } from "zustand";
import { ApiError, api } from "../api/client";
import type {
  Catalog,
  ChatMessage,
  Condition,
  ContextEventType,
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
  Session,
  Setting,
  Value,
} from "../api/types";
import { derivePreset } from "../lib/availability";
import { displayValue, rowDomId, sameValue } from "../lib/format";

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
  nav: Record<GameId, NavState>;
  highlight: Highlight | null;
  pendingVideo: Partial<Record<GameId, Record<string, Value>>>;
  historyOpen: boolean;
  trayOpen: boolean;
  openCards: Record<string, boolean>;
  toasts: Toast[];
  composerPrefill: { game: GameId; text: string; nonce: number } | null;

  init: () => Promise<void>;
  prefillComposer: (game: GameId, text: string) => void;
  toast: (kind: Toast["kind"], text: string) => void;
  dismissToast: (id: number) => void;
  loadGame: (game: GameId) => Promise<void>;
  refreshState: (game: GameId) => Promise<void>;
  refreshAdaptive: (game: GameId) => Promise<void>;
  refreshModelStatus: (force?: boolean) => Promise<void>;
  switchGame: (game: GameId) => Promise<void>;
  setCondition: (condition: Condition) => Promise<void>;
  setAiMode: (mode: "local" | "fallback") => Promise<void>;
  setAdaptation: (on: boolean) => Promise<void>;
  navigate: (game: GameId, tabId: string, subtabId?: string) => void;
  goToSetting: (game: GameId, settingId: string, reason: Highlight["reason"]) => void;
  displayValues: (game: GameId) => Record<string, Value>;
  changeSetting: (game: GameId, settingId: string, value: Value) => Promise<void>;
  applyPendingVideo: (game: GameId) => Promise<void>;
  discardPendingVideo: (game: GameId) => void;
  setHistoryOpen: (open: boolean) => void;
  loadHistory: (game: GameId) => Promise<void>;
  undo: (batch: HistoryBatch) => Promise<void>;
  togglePin: (game: GameId, settingId: string) => Promise<void>;
  toggleLock: (game: GameId, settingId: string) => Promise<void>;
  stage: (game: GameId, recs: Recommendation[] | RelevantCard[], source: "ai" | "fallback" | "rules", runId: string | null, title: string) => Promise<void>;
  setTrayOpen: (open: boolean) => void;
  applyProposal: (proposal: Proposal, itemIds: string[]) => Promise<boolean>;
  rejectProposal: (proposal: Proposal, itemIds?: string[], reason?: string) => Promise<void>;
  editProposalItem: (proposal: Proposal, itemId: string, value: Value) => Promise<void>;
  rebaseItem: (proposal: Proposal, itemId: string) => Promise<void>;
  sendChat: (game: GameId, text: string) => Promise<void>;
  cancelRun: (game: GameId) => Promise<void>;
  clearChat: (game: GameId) => Promise<void>;
  refreshRelevantNow: (game: GameId) => Promise<void>;
  dismissCard: (game: GameId, settingId: string, reason?: string) => Promise<void>;
  setCardOpen: (cardId: string, open: boolean) => void;
  triggerContext: (game: GameId, eventType: string | null) => Promise<void>;
  loadProfile: () => Promise<void>;
  confirmPreference: (s: PreferenceSuggestion, scope: "session" | "durable", dimension?: string) => Promise<void>;
  addPreference: (game: GameId, dimension: string, direction: "prioritize" | "deprioritize", scope: "session" | "durable", note?: string) => Promise<void>;
  removePreference: (id: string) => Promise<void>;
  clearGoals: (game: GameId) => Promise<void>;
  loadTraces: () => Promise<void>;
  reset: (scenario: string, mode: "full" | "ai_only") => Promise<void>;
}

let toastSeq = 1;
let highlightSeq = 1;

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
  nav: { valorant: { tabId: "video", subtabId: "graphics_quality" }, cs2: { tabId: "video", subtabId: "advanced" } },
  highlight: null,
  pendingVideo: {},
  historyOpen: false,
  trayOpen: false,
  openCards: {},
  toasts: [],
  composerPrefill: null,

  prefillComposer: (game, text) => set({ composerPrefill: { game, text, nonce: highlightSeq++ } }),

  toast: (kind, text) => {
    const id = toastSeq++;
    set((s) => ({ toasts: [...s.toasts.slice(-3), { id, kind, text }] }));
    window.setTimeout(() => get().dismissToast(id), kind === "error" ? 9000 : 5000);
  },
  dismissToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),

  init: async () => {
    try {
      const [session, scenarios, contextTypes] = await Promise.all([api.session(), api.scenarios(), api.contextEventTypes()]);
      set({ session, scenarios, contextTypes });
      await Promise.all(GAMES.map((g) => get().loadGame(g)));
      set({ ready: true });
      void get().refreshModelStatus();
      if (session.condition === "adaptive") {
        await get().refreshAdaptive(session.selectedGame);
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
    const [proposals, chat, profile] = await Promise.all([api.proposals(game, "pending"), api.thread(game), api.profile()]);
    set((s) => ({ proposals: { ...s.proposals, [game]: proposals }, chat: { ...s.chat, [game]: chat }, profile }));
    try {
      const rn = await api.relevantNow(game);
      set((s) => ({ relevantNow: { ...s.relevantNow, [game]: rn } }));
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

  switchGame: async (game) => {
    const session = await api.updateSession({ selectedGame: game });
    set({ session, highlight: null });
    await get().refreshState(game);
    await get().refreshAdaptive(game);
  },

  setCondition: async (condition) => {
    const session = await api.updateSession({ condition });
    set({ session, highlight: null, trayOpen: false });
    await get().refreshState(session.selectedGame);
    await get().refreshAdaptive(session.selectedGame);
    get().toast("info", condition === "adaptive" ? "Condition B — adaptive augmentation" : "Condition A — static baseline");
  },

  setAiMode: async (mode) => {
    const session = await api.updateSession({ aiMode: mode });
    set({ session });
    await get().refreshModelStatus(true);
  },

  setAdaptation: async (on) => {
    const session = await api.updateSession({ adaptationEnabled: on });
    set({ session });
    await get().refreshAdaptive(session.selectedGame);
  },

  navigate: (game, tabId, subtabId) => {
    const catalog = get().catalogs[game];
    if (!catalog) return;
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
    } catch (err) {
      get().toast("error", errText(err));
    }
    await get().refreshState(game);
    await get().refreshAdaptive(game);
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
    } catch (err) {
      get().toast("error", errText(err));
    }
    await get().refreshState(batch.game);
    await get().loadHistory(batch.game);
    await get().refreshAdaptive(batch.game);
  },

  togglePin: async (game, settingId) => {
    const pinned = get().states[game]?.pins.includes(settingId) ?? false;
    try {
      await api.setPin(game, settingId, !pinned);
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
      else get().toast("info", `Staged ${proposal.items.length} change(s) for review — nothing applied yet.`);
      set({ trayOpen: true });
    } catch (err) {
      get().toast("error", errText(err));
    }
    await get().refreshAdaptive(game);
  },

  setTrayOpen: (open) => set({ trayOpen: open }),

  applyProposal: async (proposal, itemIds) => {
    const pending = get().pendingVideo[proposal.game] ?? {};
    const clash = proposal.items.filter((i) => itemIds.includes(i.id) && pending[i.settingId] !== undefined);
    if (clash.length) {
      get().toast("warning", `You have unapplied video edits for ${clash.map((c) => c.label).join(", ")}. Apply or discard them first.`);
      return false;
    }
    let ok = false;
    try {
      const res = await api.applyProposal(proposal.id, itemIds);
      get().toast("success", `Applied ${res.batch.events.length} change(s). You can undo them from History.`);
      ok = true;
    } catch (err) {
      get().toast("error", errText(err));
    }
    await get().refreshState(proposal.game);
    await get().refreshAdaptive(proposal.game);
    return ok;
  },

  rejectProposal: async (proposal, itemIds, reason) => {
    try {
      await api.rejectProposal(proposal.id, itemIds, reason);
      get().toast("info", "Rejected — no settings were changed.");
    } catch (err) {
      get().toast("error", errText(err));
    }
    await get().refreshAdaptive(proposal.game);
  },

  editProposalItem: async (proposal, itemId, value) => {
    try {
      const updated = await api.editItem(proposal.id, itemId, value);
      set((s) => ({ proposals: { ...s.proposals, [proposal.game]: (s.proposals[proposal.game] ?? []).map((p) => (p.id === updated.id ? updated : p)) } }));
    } catch (err) {
      get().toast("error", errText(err));
    }
  },

  rebaseItem: async (proposal, itemId) => {
    try {
      await api.rebaseItem(proposal.id, itemId);
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
    try {
      const run = await api.chat(game, text, { tabId: nav.tabId, subtabId: nav.subtabId, path });
      set((s) => ({ runs: { ...s.runs, [game]: run } }));
      const thread = await api.thread(game);
      set((s) => ({ chat: { ...s.chat, [game]: thread } }));
      const poll = async () => {
        const status = await api.run(run.runId);
        set((s) => ({ runs: { ...s.runs, [game]: status } }));
        if (status.status === "running") {
          window.setTimeout(poll, 400);
          return;
        }
        set((s) => ({ runs: { ...s.runs, [game]: null } }));
        await get().refreshAdaptive(game);
        const res = status.result;
        if (res?.navigateTo && res.intent === "navigate") get().goToSetting(game, res.navigateTo.settingId, "assistant");
      };
      window.setTimeout(poll, 300);
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
  },

  refreshRelevantNow: async (game) => {
    try {
      const rn = await api.refreshRelevantNow(game);
      set((s) => ({ relevantNow: { ...s.relevantNow, [game]: rn }, openCards: {} }));
    } catch (err) {
      get().toast("error", errText(err));
    }
  },

  dismissCard: async (game, settingId, reason) => {
    try {
      const rn = await api.dismissCard(game, settingId, reason);
      set((s) => ({ relevantNow: { ...s.relevantNow, [game]: rn } }));
    } catch (err) {
      get().toast("error", errText(err));
    }
  },

  setCardOpen: (cardId, open) => set((s) => ({ openCards: { ...s.openCards, [cardId]: open } })),

  triggerContext: async (game, eventType) => {
    try {
      const rn = await api.setContextEvent(game, eventType);
      set((s) => ({ relevantNow: { ...s.relevantNow, [game]: rn }, openCards: {} }));
      await get().loadProfile();
    } catch (err) {
      get().toast("error", errText(err));
    }
  },

  loadProfile: async () => set({ profile: await api.profile() }),

  confirmPreference: async (s, scope, dimension) => {
    try {
      await api.addPreference({ dimension: dimension ?? s.dimension, direction: s.direction, scope, source: "chat_confirmed", game: s.game, note: s.quote });
      get().toast("success", scope === "session" ? "Saved for this session only." : "Saved as a lasting preference (applies across games).");
    } catch (err) {
      get().toast("error", errText(err));
    }
    await get().refreshAdaptive(s.game);
  },

  addPreference: async (game, dimension, direction, scope, note) => {
    try {
      await api.addPreference({ dimension, direction, scope, source: "user_explicit", game, note });
    } catch (err) {
      get().toast("error", errText(err));
    }
    await get().refreshAdaptive(game);
  },

  removePreference: async (id) => {
    await api.removePreference(id);
    const game = get().session?.selectedGame;
    if (game) await get().refreshAdaptive(game);
  },

  clearGoals: async (game) => {
    await api.clearSessionGoals(game);
    await get().refreshAdaptive(game);
  },

  loadTraces: async () => set({ traces: await api.traces() }),

  reset: async (scenario, mode) => {
    try {
      const res = await api.reset(scenario, mode);
      set({ session: res.session, pendingVideo: {}, highlight: null, relevantNow: {}, chat: {}, proposals: {}, history: {}, openCards: {} });
      await Promise.all(GAMES.map((g) => get().refreshState(g)));
      await get().refreshAdaptive(res.session.selectedGame);
      get().toast("success", `Reset to “${scenario}” (${mode === "full" ? "full experimental state" : "AI session state only"}). Backup saved.`);
    } catch (err) {
      get().toast("error", errText(err));
    }
  },
}));
