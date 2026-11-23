import { useEffect, useState } from "react";
import { gameName, timeAgo } from "../../lib/format";
import { useAppStore } from "../../store/useAppStore";

export function HistoryDrawer() {
  const open = useAppStore((s) => s.historyOpen);
  const setOpen = useAppStore((s) => s.setHistoryOpen);
  const game = useAppStore((s) => s.session?.selectedGame);
  const adaptive = useAppStore((s) => s.session?.condition === "adaptive");
  const history = useAppStore((s) => (game ? s.history[game] : undefined));
  const undo = useAppStore((s) => s.undo);
  const restageHistoryBatch = useAppStore((s) => s.restageHistoryBatch);
  const requestFocusInMainWindow = useAppStore((s) => s.requestFocusInMainWindow);
  const [expandedWhy, setExpandedWhy] = useState<Record<string, boolean>>({});

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
            <small>
              Inspect what changed, why it was suggested (when recorded), Undo the most recent change, or restage an editable draft safely.
            </small>
          </div>
          <button type="button" className="sc-close" aria-label="Close history" onClick={() => setOpen(false)}>
            ×
          </button>
        </header>
        <ol className="history-list">
          {(history ?? []).length === 0 ? <li className="history-empty">No changes yet in this game.</li> : null}
          {(history ?? []).map((b) => {
            const prov = b.provenance;
            const hasRationale = Boolean(prov?.hasRecordedRationale);
            const showWhy = Boolean(expandedWhy[b.batchId]);
            const hasEventWhy = b.events.some((e) => e.why || e.tradeoff || e.basedOn);
            return (
              <li
                key={b.batchId}
                className={`history-item src-${b.source} ${b.undoneByBatchId ? "is-undone" : ""} ${b.superseded ? "is-superseded" : ""}`}
              >
                <div className="history-meta">
                  <span className={`badge badge-${b.source}`}>{b.sourceLabel}</span>
                  <time dateTime={b.createdAt} title={new Date(b.createdAt).toLocaleString()}>
                    {timeAgo(b.createdAt)}
                  </time>
                  {b.undoneByBatchId ? (
                    <span className="badge badge-undone">Undone</span>
                  ) : b.superseded ? (
                    <span className="badge badge-superseded">Changed since</span>
                  ) : (
                    <span className="badge badge-current">Active</span>
                  )}
                  {prov?.restagedFromBatchId ? <span className="badge">Restaged</span> : null}
                  {b.outdatedForCurrentGoal ? (
                    <span className="badge badge-warn">Outdated for current goal</span>
                  ) : null}
                </div>

                {b.label ? <div className="history-label">{b.label}</div> : null}

                {prov?.userRequest ? (
                  <p className="history-request">
                    <strong>{prov.userRequestIsExcerpt ? "Request excerpt:" : "Original request:"}</strong> “{prov.userRequest}”
                  </p>
                ) : hasRationale && prov?.planReason ? (
                  <p className="history-request">{prov.planReason}</p>
                ) : (
                  <p className="history-missing-prov">
                    Manual edit — no assistant rationale was recorded.
                  </p>
                )}

                <ul className="history-events">
                  {b.events.map((e) => (
                    <li key={e.eventId}>
                      <button
                        type="button"
                        className="link"
                        onClick={() => {
                          setOpen(false);
                          requestFocusInMainWindow(game, e.settingId, "history");
                        }}
                      >
                        {e.label}
                      </button>
                      : <span className="old">{e.oldDisplay}</span> → <span className="new">{e.newDisplay}</span>
                      {!e.stillCurrent && e.currentDisplay ? (
                        <span className="history-now"> (now {e.currentDisplay})</span>
                      ) : null}
                      {e.wasEditedByUser ? <span className="chip">edited before apply</span> : null}
                      <span className="history-path">{e.path}</span>
                    </li>
                  ))}
                </ul>

                {hasRationale && hasEventWhy ? (
                  <div className="history-why-wrap">
                    <button
                      type="button"
                      className="link"
                      aria-expanded={showWhy}
                      onClick={() => setExpandedWhy((m) => ({ ...m, [b.batchId]: !m[b.batchId] }))}
                    >
                      {showWhy ? "Hide original reasoning & trade-offs" : "Why suggested & trade-offs"}
                    </button>
                    {showWhy ? (
                      <ul className="history-why-list">
                        {b.events.map((e) =>
                          e.why || e.tradeoff || e.basedOn ? (
                            <li key={e.eventId}>
                              <strong>{e.label}:</strong> {e.why ?? e.basedOn}
                              {e.tradeoff ? <span className="history-tradeoff"> Trade-off: {e.tradeoff}</span> : null}
                            </li>
                          ) : null,
                        )}
                      </ul>
                    ) : null}
                  </div>
                ) : null}

                <div className="history-actions">
                  {b.undoable ? (
                    <button type="button" className="btn btn-small" onClick={() => void undo(b)}>
                      Undo
                    </button>
                  ) : !b.undoneByBatchId ? (
                    <span className="history-note" title="A later change touched the same setting; undo that one first.">
                      Undo unavailable (changed later)
                    </span>
                  ) : null}

                  {adaptive && b.source !== "reset" ? (
                    <button
                      type="button"
                      className="btn btn-small btn-ghost"
                      title="Open an editable draft with these target values in Changes (nothing changes until you apply)"
                      onClick={() => void restageHistoryBatch(b)}
                    >
                      Review &amp; restage
                    </button>
                  ) : null}
                </div>
              </li>
            );
          })}
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
          <button type="button" aria-label="Dismiss notification" onClick={() => dismiss(t.id)}>
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
