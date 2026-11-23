import type { GameId } from "../api/types";

export type SyncInput =
  | { type: "state_changed"; game: GameId }
  | { type: "navigate_setting"; game: GameId; settingId: string }
  | { type: "open_workspace_tab"; tab: "changes" | "pinned" | "discover"; game: GameId }
  | { type: "workspace_attached" }
  | { type: "workspace_heartbeat" }
  | { type: "workspace_closed" }
  | { type: "workspace_ping" }
  | { type: "workspace_focus_request" }
  | { type: "workspace_recall" };

export type SyncMessage = SyncInput & { senderId: string; ts: number };

const CHANNEL_NAME = "csc2524-workspace-sync";
const STORAGE_KEY = "csc2524.sync.event";
const LEASE_KEY = "csc2524.detached.lease";
export const DETACHED_TTL_MS = 5000;

export const TAB_SENDER_ID =
  typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;

let channel: BroadcastChannel | null = null;
function getChannel(): BroadcastChannel | null {
  if (typeof window === "undefined" || typeof BroadcastChannel === "undefined") return null;
  if (!channel) {
    try {
      channel = new BroadcastChannel(CHANNEL_NAME);
    } catch {
      channel = null;
    }
  }
  return channel;
}

export function writeDetachedLease(senderId: string = TAB_SENDER_ID): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(LEASE_KEY, JSON.stringify({ senderId, ts: Date.now() }));
  } catch {
    // ignore private browsing quota issues
  }
}

export function clearDetachedLease(senderId?: string): void {
  if (typeof window === "undefined") return;
  try {
    if (senderId) {
      const raw = window.localStorage.getItem(LEASE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as { senderId?: string };
        if (parsed.senderId && parsed.senderId !== senderId) return;
      }
    }
    window.localStorage.removeItem(LEASE_KEY);
  } catch {
    // ignore storage errors
  }
}

export function isDetachedLeaseAlive(): boolean {
  if (typeof window === "undefined") return false;
  try {
    const raw = window.localStorage.getItem(LEASE_KEY);
    if (!raw) return false;
    const parsed = JSON.parse(raw) as { ts?: number };
    return typeof parsed.ts === "number" && Date.now() - parsed.ts < DETACHED_TTL_MS;
  } catch {
    return false;
  }
}

export function broadcastSync(msg: SyncInput): void {
  const payload = { ...msg, senderId: TAB_SENDER_ID, ts: Date.now() } as SyncMessage;
  const ch = getChannel();
  if (ch) {
    try {
      ch.postMessage(payload);
    } catch {
      // ignore closed channel
    }
  }
  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
    } catch {
      // ignore private browsing quota issues
    }
  }
}

export function subscribeSync(onMessage: (msg: SyncMessage) => void, onFocus?: () => void): () => void {
  const ch = getChannel();
  const handle = (raw: unknown) => {
    if (!raw || typeof raw !== "object") return;
    const msg = raw as SyncMessage;
    if (msg.senderId === TAB_SENDER_ID) return;
    onMessage(msg);
  };
  const onBc = (e: MessageEvent) => handle(e.data);
  const onStorage = (e: StorageEvent) => {
    if (e.key === LEASE_KEY) {
      if (!e.newValue) {
        onMessage({ type: "workspace_closed", senderId: "storage", ts: Date.now() });
      }
      return;
    }
    if (e.key !== STORAGE_KEY || !e.newValue) return;
    try {
      handle(JSON.parse(e.newValue));
    } catch {
      // ignore invalid JSON
    }
  };
  const onWinFocus = () => onFocus?.();

  ch?.addEventListener("message", onBc);
  if (typeof window !== "undefined") {
    window.addEventListener("storage", onStorage);
    window.addEventListener("focus", onWinFocus);
  }
  return () => {
    ch?.removeEventListener("message", onBc);
    if (typeof window !== "undefined") {
      window.removeEventListener("storage", onStorage);
      window.removeEventListener("focus", onWinFocus);
    }
  };
}
