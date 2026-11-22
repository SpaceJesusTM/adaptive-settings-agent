// Thin fetch wrapper. The browser only talks to the local backend (/api); Ollama is never called from here.
import type {
  Catalog,
  ChatMessage,
  ContextEventType,
  GameId,
  GameState,
  HistoryBatch,
  ModelStatus,
  Profile,
  Proposal,
  RelevantNowSet,
  RunStatus,
  ScenarioInfo,
  SearchHit,
  Session,
  Value,
} from "./types";

export class ApiError extends Error {
  status: number;
  code: string;
  details: unknown;
  constructor(status: number, code: string, message: string, details: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (err) {
    throw new ApiError(0, "network", "Cannot reach the local backend. Is it running?", err);
  }
  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  if (!res.ok) {
    const d = (data && typeof data === "object" ? data : {}) as { error?: string; message?: string; details?: unknown; detail?: unknown };
    const message = d.message ?? (Array.isArray(d.detail) ? "The request was not valid." : String(d.detail ?? res.statusText));
    throw new ApiError(res.status, d.error ?? "http_error", message, d.details ?? d.detail);
  }
  return data as T;
}

export function newRequestId(prefix = "req"): string {
  const rand = typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
  return `${prefix}-${rand}`;
}

export const api = {
  health: () => request<{ ok: boolean; version: string }>("GET", "/api/health"),
  modelStatus: (force = false) => request<ModelStatus>("GET", `/api/model/status${force ? "?force=true" : ""}`),
  session: () => request<Session>("GET", "/api/session"),
  updateSession: (patch: Partial<Pick<Session, "condition" | "selectedGame" | "adaptationEnabled" | "aiMode">>) =>
    request<Session>("PUT", "/api/session", patch),
  catalog: (game: GameId) => request<Catalog>("GET", `/api/games/${game}/catalog`),
  state: (game: GameId) => request<GameState>("GET", `/api/games/${game}/state`),
  search: (game: GameId, q: string) => request<SearchHit[]>("GET", `/api/games/${game}/search?q=${encodeURIComponent(q)}`),
  changeSetting: (game: GameId, settingId: string, value: Value, expectedRevision?: number) =>
    request<HistoryBatch>("PUT", `/api/games/${game}/settings/${encodeURIComponent(settingId)}`, {
      value,
      expectedRevision,
      clientRequestId: newRequestId("chg"),
    }),
  changeBatch: (game: GameId, changes: { settingId: string; value: Value; expectedRevision?: number }[], label?: string) =>
    request<HistoryBatch>("POST", `/api/games/${game}/batch`, { changes, label, clientRequestId: newRequestId("bat") }),
  history: (game: GameId) => request<HistoryBatch[]>("GET", `/api/games/${game}/history`),
  undo: (batchId: string) => request<HistoryBatch>("POST", `/api/history/${batchId}/undo`, { clientRequestId: newRequestId("undo") }),
  setPin: (game: GameId, settingId: string, on: boolean) =>
    request<{ pins: string[] }>("PUT", `/api/games/${game}/pins/${encodeURIComponent(settingId)}`, { on }),
  setLock: (game: GameId, settingId: string, on: boolean) =>
    request<{ locks: string[] }>("PUT", `/api/games/${game}/locks/${encodeURIComponent(settingId)}`, { on }),
  proposals: (game: GameId, status?: string) =>
    request<Proposal[]>("GET", `/api/games/${game}/proposals${status ? `?status=${status}` : ""}`),
  createProposal: (body: {
    game: GameId;
    source: "ai" | "fallback" | "rules";
    runId?: string | null;
    title?: string;
    items: { settingId: string; proposedValue: Value; why?: string; tradeoff?: string | null; confidence?: string; dimensions?: string[]; basedOn?: string | null }[];
  }) => request<Proposal>("POST", "/api/proposals", body),
  editItem: (proposalId: string, itemId: string, value: Value) =>
    request<Proposal>("PATCH", `/api/proposals/${proposalId}/items/${itemId}`, { value }),
  rebaseItem: (proposalId: string, itemId: string) => request<Proposal>("POST", `/api/proposals/${proposalId}/items/${itemId}/rebase`),
  applyProposal: (proposalId: string, itemIds: string[]) =>
    request<{ proposal: Proposal; batch: HistoryBatch }>("POST", `/api/proposals/${proposalId}/apply`, {
      itemIds,
      idempotencyKey: newRequestId("apply"),
    }),
  rejectProposal: (proposalId: string, itemIds?: string[], reason?: string) =>
    request<Proposal>("POST", `/api/proposals/${proposalId}/reject`, { itemIds, reason }),
  chat: (game: GameId, message: string, uiState: Record<string, unknown>) =>
    request<RunStatus>("POST", "/api/chat", { game, message, uiState }),
  run: (runId: string) => request<RunStatus>("GET", `/api/chat/runs/${runId}`),
  cancelRun: (runId: string) => request<RunStatus>("POST", `/api/chat/runs/${runId}/cancel`),
  thread: (game: GameId) => request<ChatMessage[]>("GET", `/api/games/${game}/chat`),
  clearThread: (game: GameId) => request<{ ok: boolean }>("DELETE", `/api/games/${game}/chat`),
  traces: (game?: GameId) => request<RunStatus[]>("GET", `/api/traces${game ? `?game=${game}` : ""}`),
  relevantNow: (game: GameId) => request<RelevantNowSet>("GET", `/api/games/${game}/relevant-now`),
  refreshRelevantNow: (game: GameId) => request<RelevantNowSet>("POST", `/api/games/${game}/relevant-now/refresh`),
  dismissCard: (game: GameId, settingId: string, reason?: string) =>
    request<RelevantNowSet>("POST", `/api/games/${game}/relevant-now/dismiss`, { settingId, reason }),
  contextEventTypes: () => request<ContextEventType[]>("GET", "/api/context-events"),
  setContextEvent: (game: GameId, eventType: string | null) =>
    request<RelevantNowSet>("POST", "/api/context-events", { game, eventType }),
  profile: () => request<Profile>("GET", "/api/profile"),
  addPreference: (body: {
    dimension: string;
    direction: "prioritize" | "deprioritize";
    scope: "durable" | "session";
    source: "user_explicit" | "chat_confirmed";
    game?: GameId;
    note?: string;
  }) => request<{ id: string }>("POST", "/api/profile/preferences", body),
  removePreference: (id: string) => request<{ ok: boolean }>("DELETE", `/api/profile/preferences/${id}`),
  clearSessionGoals: (game: GameId) => request<{ ok: boolean }>("DELETE", `/api/games/${game}/session-goals`),
  scenarios: () => request<ScenarioInfo[]>("GET", "/api/admin/scenarios"),
  reset: (scenario: string, mode: "full" | "ai_only") =>
    request<{ scenario: string; mode: string; backup: string | null; session: Session }>("POST", "/api/admin/reset", { scenario, mode }),
  exportState: () => request<unknown>("GET", "/api/admin/export"),
};
