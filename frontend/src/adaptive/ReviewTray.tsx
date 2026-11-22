import { useEffect, useMemo, useRef, useState } from "react";
import type { GameId, Proposal, ProposalItem } from "../api/types";
import { SettingControl } from "../components/controls/Controls";
import { timeAgo } from "../lib/format";
import { EMPTY, useAppStore } from "../store/useAppStore";

function ItemRow({ proposal, item, selected, onSelect }: { proposal: Proposal; item: ProposalItem; selected: boolean; onSelect: (on: boolean) => void }) {
  const setting = useAppStore((s) => s.byId[proposal.game]?.[item.settingId]);
  const edit = useAppStore((s) => s.editProposalItem);
  const rebase = useAppStore((s) => s.rebaseItem);
  const toggleLock = useAppStore((s) => s.toggleLock);
  const goToSetting = useAppStore((s) => s.goToSetting);
  const blocked = item.locked || Boolean(item.unavailableReason);
  const labelId = `tray-${item.id}`;
  return (
    <li className={`tray-item ${item.stale ? "is-stale" : ""} ${blocked ? "is-blocked" : ""}`}>
      <label className="tray-check">
        <input type="checkbox" checked={selected} disabled={blocked || item.stale} onChange={(e) => onSelect(e.target.checked)}
          aria-label={`Include ${item.label} in the change set`} />
      </label>
      <div className="tray-main">
        <div className="tray-title">
          <strong id={labelId}>{item.label}</strong>
          <span className="rec-path">{item.path}</span>
        </div>
        <div className="tray-change">
          <span className="rec-from" title="Value when this suggestion was staged">{item.baselineDisplay}</span>
          <span className="rec-arrow" aria-hidden>→</span>
          {setting ? (
            <div className="tray-edit">
              <SettingControl game={proposal.game} setting={setting} value={item.effectiveValue} labelId={labelId}
                onChange={(v) => void edit(proposal, item.id, v)} />
            </div>
          ) : <span className="rec-to">{item.effectiveDisplay}</span>}
          {item.editedValue !== null ? <span className="chip">edited by you</span> : null}
        </div>
        {item.why ? <p className="tray-why">{item.why}</p> : null}
        {item.stale ? (
          <p className="tray-warn" role="alert">
            {item.label} changed since this was staged (now {item.currentDisplay}).{" "}
            <button type="button" className="link" onClick={() => void rebase(proposal, item.id)}>Keep the suggestion against the current value</button>
          </p>
        ) : null}
        {item.locked ? (
          <p className="tray-warn" role="alert">
            Locked from AI changes — it will not be applied.{" "}
            <button type="button" className="link" onClick={() => void toggleLock(proposal.game, item.settingId)}>Unlock</button>
          </p>
        ) : null}
        {item.unavailableReason ? <p className="tray-warn" role="alert">{item.unavailableReason}</p> : null}
        {item.statusReason && !item.stale && !item.locked ? <p className="tray-warn">{item.statusReason}</p> : null}
        <button type="button" className="link" onClick={() => goToSetting(proposal.game, item.settingId, "assistant")}>Show in settings</button>
      </div>
    </li>
  );
}

function ProposalBlock({ proposal }: { proposal: Proposal }) {
  const apply = useAppStore((s) => s.applyProposal);
  const reject = useAppStore((s) => s.rejectProposal);
  const pending = useMemo(() => proposal.items.filter((i) => i.status === "pending"), [proposal]);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setSelected((prev) => {
      const next: Record<string, boolean> = {};
      for (const i of pending) next[i.id] = prev[i.id] ?? !(i.locked || i.unavailableReason || i.stale);
      return next;
    });
  }, [pending]);

  const chosen = pending.filter((i) => selected[i.id] && !i.locked && !i.unavailableReason && !i.stale).map((i) => i.id);
  return (
    <div className="tray-proposal" aria-label={proposal.title}>
      <header className="tray-phead">
        <span className={`prov-badge prov-${proposal.source}`}>{proposal.sourceLabel}</span>
        <strong>{proposal.title}</strong>
        <time dateTime={proposal.createdAt}>{timeAgo(proposal.createdAt)}</time>
      </header>
      <ul className="tray-items">
        {pending.map((i) => (
          <ItemRow key={i.id} proposal={proposal} item={i} selected={Boolean(selected[i.id])}
            onSelect={(on) => setSelected((s) => ({ ...s, [i.id]: on }))} />
        ))}
      </ul>
      <footer className="tray-actions">
        <button type="button" className="btn btn-primary" disabled={!chosen.length || busy}
          onClick={async () => { setBusy(true); await apply(proposal, chosen); setBusy(false); }}>
          Apply selected changes ({chosen.length})
        </button>
        <button type="button" className="btn" disabled={!chosen.length || busy} onClick={() => void reject(proposal, chosen, "Rejected selected")}>Reject selected</button>
        <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => void reject(proposal, undefined, "Rejected all")}>Reject all</button>
      </footer>
    </div>
  );
}

export function ReviewTray({ game }: { game: GameId }) {
  const proposals = useAppStore((s) => s.proposals[game] ?? EMPTY);
  const open = useAppStore((s) => s.trayOpen);
  const setOpen = useAppStore((s) => s.setTrayOpen);
  const pending = proposals.filter((p) => p.status === "pending");
  const count = pending.reduce((n, p) => n + p.items.filter((i) => i.status === "pending").length, 0);
  const prevCount = useRef(count);
  useEffect(() => {
    if (prevCount.current > 0 && count === 0) setOpen(false); // everything applied/rejected: get out of the way
    prevCount.current = count;
  }, [count, setOpen]);
  return (
    <section className={`tray ${open ? "is-open" : ""}`} aria-label="Review staged changes">
      <button type="button" className="tray-handle" aria-expanded={open} aria-label={`Review changes: ${count} staged`} onClick={() => setOpen(!open)}>
        <span className="tray-handle-title">Review changes</span>
        <span className={`tray-count ${count ? "has-items" : ""}`}>{count} staged</span>
        <span className="tray-handle-hint">{count ? "Nothing is applied until you press “Apply selected changes”." : "Stage suggestions from the assistant to review them here."}</span>
        <span aria-hidden>{open ? "▾" : "▴"}</span>
      </button>
      {open ? (
        <div className="tray-body">
          {pending.length === 0 ? <p className="tray-empty">No staged changes.</p> : null}
          {pending.map((p) => <ProposalBlock key={p.id} proposal={p} />)}
        </div>
      ) : null}
    </section>
  );
}
