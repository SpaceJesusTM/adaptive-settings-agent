import { useEffect } from "react";
import { gameName, timeAgo } from "../../lib/format";
import { useAppStore } from "../../store/useAppStore";

export function HistoryDrawer() {
  const open = useAppStore((s) => s.historyOpen);
  const setOpen = useAppStore((s) => s.setHistoryOpen);
  const game = useAppStore((s) => s.session?.selectedGame);
  const history = useAppStore((s) => (game ? s.history[game] : undefined));
  const undo = useAppStore((s) => s.undo);
  const requestFocusInMainWindow = useAppStore((s) => s.requestFocusInMainWindow);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, setOpen]);

  if (!open || !game) return null;
  return (
    <div className="drawer-scrim" onMouseDown={(e) => e.target === e.currentTarget && setOpen(false)}>
      <aside className="drawer" role="dialog" aria-label={`${gameName(game)} change history`}>
        <header className="drawer-head">
          <div>
            <strong>Change history · {gameName(game)}</strong>
            <small>Every change, its source and its before/after values. Undo restores the earlier value if nothing changed since.</small>
          </div>
          <button type="button" className="sc-close" aria-label="Close history" onClick={() => setOpen(false)}>×</button>
        </header>
        <ol className="history-list">
          {(history ?? []).length === 0 ? <li className="history-empty">No changes yet in this game.</li> : null}
          {(history ?? []).map((b) => (
            <li key={b.batchId} className={`history-item src-${b.source} ${b.undoneByBatchId ? "is-undone" : ""}`}>
              <div className="history-meta">
                <span className={`badge badge-${b.source}`}>{b.sourceLabel}</span>
                <time dateTime={b.createdAt} title={new Date(b.createdAt).toLocaleString()}>{timeAgo(b.createdAt)}</time>
                {b.undoneByBatchId ? <span className="badge badge-undone">Undone</span> : null}
              </div>
              {b.label ? <div className="history-label">{b.label}</div> : null}
              <ul className="history-events">
                {b.events.map((e) => (
                  <li key={e.eventId}>
                    <button type="button" className="link" onClick={() => { setOpen(false); requestFocusInMainWindow(game, e.settingId, "history"); }}>{e.label}</button>
                    : <span className="old">{e.oldDisplay}</span> → <span className="new">{e.newDisplay}</span>
                    <span className="history-path">{e.path}</span>
                  </li>
                ))}
              </ul>
              {b.proposalId ? <div className="history-proposal">Proposal {b.proposalId}</div> : null}
              <div className="history-actions">
                {b.undoable ? (
                  <button type="button" className="btn btn-small" onClick={() => void undo(b)}>Undo</button>
                ) : !b.undoneByBatchId ? (
                  <span className="history-note" title="A later change touched the same setting; undo that one first.">Undo unavailable (changed later)</span>
                ) : null}
              </div>
            </li>
          ))}
        </ol>
      </aside>
    </div>
  );
}

export function Toasts() {
  const toasts = useAppStore((s) => s.toasts);
  const dismiss = useAppStore((s) => s.dismissToast);
  return (
    <div className="toasts" aria-live="polite" aria-atomic="false">
      {toasts.map((t) => (
        <div key={t.id} className={`toast toast-${t.kind}`} role={t.kind === "error" ? "alert" : "status"}>
          <span>{t.text}</span>
          <button type="button" aria-label="Dismiss notification" onClick={() => dismiss(t.id)}>×</button>
        </div>
      ))}
    </div>
  );
}
