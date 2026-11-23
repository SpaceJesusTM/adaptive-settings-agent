import { useEffect, useMemo, useState } from "react";
import type { GameId, Proposal, ProposalItem } from "../api/types";
import { SettingControl } from "../components/controls/Controls";
import { availability } from "../lib/availability";
import { displayValue, timeAgo } from "../lib/format";
import { EMPTY, useAppStore } from "../store/useAppStore";
import { RelevantNow } from "./RelevantNow";

const EMPTY_MAP: Record<string, never> = {};

function ItemRow({
  proposal,
  item,
  selected,
  onSelect,
}: {
  proposal: Proposal;
  item: ProposalItem;
  selected: boolean;
  onSelect: (on: boolean) => void;
}) {
  const setting = useAppStore((s) => s.byId[proposal.game]?.[item.settingId]);
  const experimenterMode = useAppStore((s) => s.experimenterMode);
  const edit = useAppStore((s) => s.editProposalItem);
  const rebase = useAppStore((s) => s.rebaseItem);
  const toggleLock = useAppStore((s) => s.toggleLock);
  const requestFocus = useAppStore((s) => s.requestFocusInMainWindow);
  const [showDetails, setShowDetails] = useState(false);

  const blocked = item.locked || Boolean(item.unavailableReason);
  const labelId = `tray-${item.id}`;
  return (
    <li className={`tray-item ${item.stale ? "is-stale" : ""} ${blocked ? "is-blocked" : ""}`}>
      <label className="tray-check">
        <input
          type="checkbox"
          checked={selected}
          disabled={blocked || item.stale}
          onChange={(e) => onSelect(e.target.checked)}
          aria-label={`Include ${item.label} in the change set`}
        />
      </label>
      <div className="tray-main">
        <div className="tray-title">
          <strong id={labelId}>{item.label}</strong>
          <span className="rec-path">{item.path}</span>
        </div>
        <div className="tray-change">
          <span className="rec-from" title="Value when this suggestion was staged">
            {item.baselineDisplay}
          </span>
          <span className="rec-arrow" aria-hidden>
            →
          </span>
          {setting ? (
            <div className="tray-edit">
              <SettingControl game={proposal.game} setting={setting} value={item.effectiveValue} labelId={labelId} onChange={(v) => void edit(proposal, item.id, v)} />
            </div>
          ) : (
            <span className="rec-to">{item.effectiveDisplay}</span>
          )}
          {item.editedValue !== null ? <span className="chip">edited by you</span> : null}
          {JSON.stringify(item.effectiveValue) === JSON.stringify(item.baselineValue) ? (
            <span className="chip chip-warn" title="This matches the current setting value, so applying it will make no change.">
              matches current
            </span>
          ) : null}
        </div>
        {item.why ? <p className="tray-why">{item.why}</p> : null}
        {item.stale ? (
          <p className="tray-warn" role="alert">
            {item.label} changed since staging (now {item.currentDisplay}).{" "}
            <button type="button" className="link" onClick={() => void rebase(proposal, item.id)}>
              Keep &amp; update baseline
            </button>
          </p>
        ) : null}
        {item.locked ? (
          <p className="tray-warn" role="alert">
            Locked from AI changes — it will not be applied.{" "}
            <button type="button" className="link" onClick={() => void toggleLock(proposal.game, item.settingId)}>
              Unlock
            </button>
          </p>
        ) : null}
        {item.unavailableReason ? (
          <p className="tray-warn" role="alert">
            {item.unavailableReason}
          </p>
        ) : null}
        {item.statusReason && !item.stale && !item.locked ? <p className="tray-warn">{item.statusReason}</p> : null}
        <div className="tray-item-links">
          <button type="button" className="link" onClick={() => requestFocus(proposal.game, item.settingId)}>
            Show in settings
          </button>
          <button type="button" className="link" aria-expanded={showDetails} onClick={() => setShowDetails((d) => !d)}>
            {showDetails ? "Hide details" : "What it does & trade-offs"}
          </button>
        </div>
        {showDetails ? (
          <div className="tray-item-details">
            <p>
              <strong>What it does:</strong> {item.whatItDoes}
            </p>
            {item.tradeoff ? (
              <p>
                <strong>Trade-offs:</strong> {item.tradeoff}
              </p>
            ) : null}
            {item.basedOn ? (
              <p>
                <strong>Based on:</strong> {item.basedOn}
              </p>
            ) : null}
            {experimenterMode || item.sourceURL ? (
              <p className="muted">
                <a href={item.sourceURL} target="_blank" rel="noreferrer">
                  Reference source
                </a>
                {experimenterMode ? ` · verification: ${setting?.verificationStatus ?? "verified"}` : ""}
              </p>
            ) : null}
          </div>
        ) : null}
      </div>
    </li>
  );
}

function ProposalBlock({ proposal }: { proposal: Proposal }) {
  const apply = useAppStore((s) => s.applyProposal);
  const reject = useAppStore((s) => s.rejectProposal);
  const requestFocus = useAppStore((s) => s.requestFocusInMainWindow);
  const byId = useAppStore((s) => s.byId[proposal.game] ?? EMPTY_MAP);
  const pendingVideo = useAppStore((s) => s.pendingVideo[proposal.game] ?? EMPTY_MAP);
  const experimenterMode = useAppStore((s) => s.experimenterMode);

  const pending = useMemo(() => proposal.items.filter((i) => i.status === "pending"), [proposal]);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false);
  const [showPlanDetails, setShowPlanDetails] = useState(false);
  const [showAligned, setShowAligned] = useState(false);
  const [videoConfirm, setVideoConfirm] = useState(false);

  useEffect(() => {
    setSelected((prev) => {
      const next: Record<string, boolean> = {};
      for (const i of pending) next[i.id] = prev[i.id] ?? !(i.locked || i.unavailableReason || i.stale);
      return next;
    });
  }, [pending]);

  const selectable = pending.filter((i) => !(i.locked || i.unavailableReason || i.stale));
  const chosen = selectable.filter((i) => selected[i.id]).map((i) => i.id);
  const cs2Clash = pending.filter((i) => chosen.includes(i.id) && pendingVideo[i.settingId] !== undefined);

  const sections = useMemo(() => {
    const groups: { category: string; items: ProposalItem[] }[] = [];
    const byCat = new Map<string, ProposalItem[]>();
    for (const item of pending) {
      const cat = item.category || byId[item.settingId]?.category || "Other";
      let arr = byCat.get(cat);
      if (!arr) {
        arr = [];
        byCat.set(cat, arr);
        groups.push({ category: cat, items: arr });
      }
      arr.push(item);
    }
    return groups;
  }, [pending, byId]);

  const setGroupSelection = (items: ProposalItem[], on: boolean) => {
    setSelected((prev) => {
      const next = { ...prev };
      for (const it of items) {
        if (!(it.locked || it.unavailableReason || it.stale)) next[it.id] = on;
      }
      return next;
    });
  };

  const handleApply = async (overridePendingVideo = false) => {
    if (!chosen.length) return;
    if (cs2Clash.length > 0 && !overridePendingVideo) {
      setVideoConfirm(true);
      return;
    }
    setBusy(true);
    await apply(proposal, chosen, { overridePendingVideo });
    setVideoConfirm(false);
    setBusy(false);
  };

  const sourceBadge =
    experimenterMode
      ? proposal.sourceLabel
      : proposal.source === "fallback"
        ? "Basic offline suggestions (not AI)"
        : proposal.source === "history"
          ? "Restaged from history"
          : "Assistant draft";

  return (
    <div className="tray-proposal" aria-label={proposal.title}>
      <header className="tray-phead">
        <span className={`prov-badge prov-${proposal.source}`}>{sourceBadge}</span>
        <strong>{proposal.title}</strong>
        <span className="tray-meta-count">{pending.length} recommended change{pending.length === 1 ? "" : "s"}</span>
        {proposal.restagedFromBatchId ? <span className="chip">Editable draft</span> : null}
        <time dateTime={proposal.createdAt}>{timeAgo(proposal.createdAt)}</time>
        {sections.length > 1 || selectable.length > 3 ? (
          <div className="tray-bulk">
            <button type="button" className="link" onClick={() => setGroupSelection(pending, true)}>
              Select all
            </button>
            <span aria-hidden>·</span>
            <button type="button" className="link" onClick={() => setGroupSelection(pending, false)}>
              Select none
            </button>
            {proposal.plan ? (
              <>
                <span aria-hidden>·</span>
                <button type="button" className="link" aria-expanded={showPlanDetails} onClick={() => setShowPlanDetails((v) => !v)}>
                  {showPlanDetails ? "Hide plan summary" : "Plan summary"}
                </button>
              </>
            ) : null}
          </div>
        ) : proposal.plan ? (
          <div className="tray-bulk">
            <button type="button" className="link" aria-expanded={showPlanDetails} onClick={() => setShowPlanDetails((v) => !v)}>
              {showPlanDetails ? "Hide plan summary" : "Plan summary"}
            </button>
          </div>
        ) : null}
      </header>

      {showPlanDetails && proposal.plan ? (
        <div className="tray-plan-summary">
          <p>{proposal.plan.reason}</p>
          <p className="muted">
            Evaluated {proposal.plan.coverage.evaluatedCount} settings · {proposal.plan.coverage.proposedCount} proposed ·{" "}
            {proposal.plan.coverage.alreadyAlignedCount} already aligned · {proposal.plan.coverage.lockedCount} locked ·{" "}
            {proposal.plan.coverage.manualCount} manual/personal excluded
          </p>
          {proposal.plan.partialCoverage ? (
            <p className="tray-warn">
              Partial coverage: finished {proposal.plan.batchesCompleted} of {proposal.plan.batchesTotal} category batches.
            </p>
          ) : null}
          {proposal.plan.manualConsiderations?.length ? (
            <div className="tray-manual-list">
              <strong>Manual settings to review yourself:</strong>
              <ul>
                {proposal.plan.manualConsiderations.map((m) => (
                  <li key={m.settingId}>
                    <span>{m.label}</span> ({m.currentDisplay}) — {m.reason}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="tray-sections">
        {sections.map((sec) => {
          const secSelectable = sec.items.filter((i) => !(i.locked || i.unavailableReason || i.stale));
          const allSelected = secSelectable.length > 0 && secSelectable.every((i) => selected[i.id]);
          return (
            <div key={sec.category} className="tray-section-group">
              {sections.length > 1 ? (
                <div className="tray-section-head">
                  <label className="tray-section-toggle">
                    <input
                      type="checkbox"
                      checked={allSelected}
                      disabled={secSelectable.length === 0}
                      onChange={(e) => setGroupSelection(sec.items, e.target.checked)}
                    />
                    <strong>{sec.category}</strong>
                    <span className="tray-sec-count">{sec.items.length}</span>
                  </label>
                </div>
              ) : null}
              <ul className="tray-items">
                {sec.items.map((i) => (
                  <ItemRow key={i.id} proposal={proposal} item={i} selected={Boolean(selected[i.id])} onSelect={(on) => setSelected((s) => ({ ...s, [i.id]: on }))} />
                ))}
              </ul>
            </div>
          );
        })}
      </div>

      {proposal.plan &&
      ((proposal.plan.alreadyAlignedItems?.length ?? 0) > 0 ||
        (proposal.plan.manualConsiderations?.length ?? 0) > 0 ||
        (proposal.plan.lockedItems?.length ?? 0) > 0 ||
        (proposal.plan.unavailableItems?.length ?? 0) > 0) ? (
        <div className="tray-review-extras" aria-label="Additional relevant settings (informational, not part of Apply)">
          {(proposal.plan.alreadyAlignedItems?.length ?? 0) > 0 ? (
            <div className="review-group">
              <div className="review-group-head">
                <strong>Already aligned ({proposal.plan.alreadyAlignedItems!.length})</strong>
                <span className="muted">Already match your goal — no change needed</span>
                <button type="button" className="link" aria-expanded={showAligned} onClick={() => setShowAligned((v) => !v)}>
                  {showAligned ? "Hide list" : "Show list"}
                </button>
              </div>
              {showAligned ? (
                <ul className="review-info-list">
                  {proposal.plan.alreadyAlignedItems!.map((a) => (
                    <li key={a.settingId} className="review-info-item">
                      <div>
                        <strong>{a.label}</strong> <span className="chip">Already {a.currentDisplay}</span>
                        {a.why ? <span className="review-info-why"> — {a.why}</span> : null}
                      </div>
                      <button type="button" className="link" onClick={() => requestFocus(proposal.game, a.settingId)}>
                        Show in settings
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}

          {(proposal.plan.manualConsiderations?.length ?? 0) > 0 ? (
            <div className="review-group">
              <div className="review-group-head">
                <strong>Needs your decision ({proposal.plan.manualConsiderations.length})</strong>
                <span className="muted">Personal or hardware controls — never changed automatically</span>
              </div>
              <ul className="review-info-list">
                {proposal.plan.manualConsiderations.slice(0, 6).map((m) => (
                  <li key={m.settingId} className="review-info-item">
                    <div>
                      <strong>{m.label}</strong> <span className="chip">{m.currentDisplay}</span>
                      <span className="review-info-why"> — {m.reason}</span>
                    </div>
                    <button type="button" className="link" onClick={() => requestFocus(proposal.game, m.settingId)}>
                      Show in settings
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {(proposal.plan.lockedItems?.length ?? 0) > 0 || (proposal.plan.unavailableItems?.length ?? 0) > 0 ? (
            <div className="review-group">
              <div className="review-group-head">
                <strong>Locked or unavailable</strong>
              </div>
              <ul className="review-info-list">
                {(proposal.plan.lockedItems ?? []).map((l) => (
                  <li key={l.settingId} className="review-info-item">
                    <div>
                      <strong>{l.label}</strong> <span className="chip">Locked</span>
                      <span className="review-info-why"> — {l.reason}</span>
                    </div>
                    <button type="button" className="link" onClick={() => requestFocus(proposal.game, l.settingId)}>
                      Show in settings
                    </button>
                  </li>
                ))}
                {(proposal.plan.unavailableItems ?? []).map((u) => (
                  <li key={u.settingId} className="review-info-item">
                    <div>
                      <strong>{u.label}</strong> <span className="chip">Unavailable</span>
                      <span className="review-info-why"> — {u.reason}</span>
                    </div>
                    <button type="button" className="link" onClick={() => requestFocus(proposal.game, u.settingId)}>
                      Show in settings
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}

      {videoConfirm ? (
        <div className="tray-clash-confirm" role="alert">
          <p>
            You have unapplied Video menu drafts for <strong>{cs2Clash.map((c) => c.label).join(", ")}</strong>. Applying these changes will replace those unapplied drafts.
          </p>
          <div className="tray-clash-actions">
            <button type="button" className="btn btn-primary btn-small" disabled={busy} onClick={() => void handleApply(true)}>
              Replace Video draft &amp; apply
            </button>
            <button type="button" className="btn btn-small" onClick={() => setVideoConfirm(false)}>
              Cancel
            </button>
          </div>
        </div>
      ) : null}

      <footer className="tray-actions">
        <button type="button" className="btn btn-primary" disabled={!chosen.length || busy} onClick={() => void handleApply(false)}>
          Apply selected changes ({chosen.length})
        </button>
        <button type="button" className="btn" disabled={!chosen.length || busy} onClick={() => void reject(proposal, chosen, "Rejected selected")}>
          Reject selected
        </button>
        <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => void reject(proposal, undefined, "Rejected all")}>
          Reject all
        </button>
      </footer>
    </div>
  );
}

function PinnedWorkspaceTab({ game }: { game: GameId }) {
  const state = useAppStore((s) => s.states[game]);
  const byId = useAppStore((s) => s.byId[game] ?? EMPTY_MAP);
  const byKey = useAppStore((s) => s.byKey[game] ?? EMPTY_MAP);
  const pendingVideo = useAppStore((s) => s.pendingVideo[game] ?? EMPTY_MAP);
  const pinnedFeedback = useAppStore((s) => s.pinnedFeedback);
  const changePinned = useAppStore((s) => s.changePinnedSetting);
  const clearFeedback = useAppStore((s) => s.clearPinnedFeedback);
  const undoById = useAppStore((s) => s.undoById);
  const togglePin = useAppStore((s) => s.togglePin);
  const requestFocus = useAppStore((s) => s.requestFocusInMainWindow);

  const [conflictChoice, setConflictChoice] = useState<{ settingId: string; value: string | number } | null>(null);

  const pins = state?.pins ?? EMPTY;
  const values = useMemo(() => {
    const out: Record<string, string | number> = {};
    for (const [id, entry] of Object.entries(state?.values ?? {})) out[id] = entry.value;
    return out;
  }, [state]);

  if (!pins.length) {
    return (
      <p className="tray-empty">
        No pinned settings for {game === "cs2" ? "CS2" : "VALORANT"} yet. Click 📌 next to any setting in the menu to edit it directly from here.
      </p>
    );
  }

  const ordered = [...pins].sort((a, b) => (byId[a]?.order ?? 9999) - (byId[b]?.order ?? 9999));

  return (
    <div className="pinned-panel" aria-label="Pinned settings editor">
      <p className="pinned-note">
        Edits made here save immediately as manual changes (never queued in AI proposals) and can be undone anytime.
      </p>
      <ul className="pinned-list">
        {ordered.map((id) => {
          const setting = byId[id];
          if (!setting) return null;
          const actualVal = values[id];
          const av = availability(setting, byKey, values, state?.hardware ?? {});
          const locked = state?.locks.includes(id) ?? false;
          const hasVideoDraft = game === "cs2" && pendingVideo[id] !== undefined;
          const fb = pinnedFeedback[id];
          const labelId = `pin-ctl-${id}`;

          return (
            <li key={id} className={`pinned-item ${av.disabledReason ? "is-disabled" : ""}`} data-pinned-id={id}>
              <div className="pinned-head">
                <div className="tray-title">
                  <strong id={labelId}>{setting.exactLabel}</strong>
                  <span className="rec-path">{setting.canonicalPath}</span>
                </div>
                <div className="pinned-head-actions">
                  {locked ? (
                    <span className="flag flag-lock" title="Locked from AI changes — your manual edits still apply">
                      🔒 AI locked
                    </span>
                  ) : null}
                  <button type="button" className="link" onClick={() => requestFocus(game, id)}>
                    Show in settings
                  </button>
                  <button type="button" className="link" onClick={() => void togglePin(game, id)} aria-label={`Unpin ${setting.exactLabel}`}>
                    Unpin
                  </button>
                </div>
              </div>

              <div className="pinned-control-row" title={av.disabledReason ?? undefined}>
                <SettingControl
                  game={game}
                  setting={setting}
                  value={actualVal}
                  disabled={Boolean(av.disabledReason)}
                  labelId={labelId}
                  onChange={async (val) => {
                    const ok = await changePinned(game, id, val);
                    if (!ok && game === "cs2" && pendingVideo[id] !== undefined) {
                      setConflictChoice({ settingId: id, value: val });
                    }
                  }}
                />
                {fb?.status === "saved" ? (
                  <span className="pin-feedback is-saved" role="status">
                    {fb.message}
                    {fb.batchId ? (
                      <>
                        {" · "}
                        <button
                          type="button"
                          className="link"
                          onClick={async () => {
                            await undoById(game, fb.batchId!);
                            clearFeedback(id);
                          }}
                        >
                          Undo
                        </button>
                      </>
                    ) : null}
                  </span>
                ) : null}
                {fb?.status === "error" ? (
                  <span className="pin-feedback is-error" role="alert">
                    {fb.message}
                  </span>
                ) : null}
              </div>

              {hasVideoDraft ? (
                <div className="pinned-video-warn" role="alert">
                  <span>
                    Unapplied Video menu draft exists ({displayValue(setting, pendingVideo[id])} in menu vs actual{" "}
                    {displayValue(setting, actualVal)}).
                  </span>
                  {conflictChoice?.settingId === id ? (
                    <div className="pinned-conflict-btns">
                      <button
                        type="button"
                        className="btn btn-small btn-primary"
                        onClick={async () => {
                          await changePinned(game, id, conflictChoice.value, { forceOverridePendingVideo: true });
                          setConflictChoice(null);
                        }}
                      >
                        Save now &amp; clear Video draft
                      </button>
                      <button
                        type="button"
                        className="btn btn-small"
                        onClick={() => {
                          clearFeedback(id);
                          setConflictChoice(null);
                          requestFocus(game, id);
                        }}
                      >
                        Go to Video menu
                      </button>
                    </div>
                  ) : null}
                </div>
              ) : null}

              {av.disabledReason ? <p className="pinned-disabled">{av.disabledReason}</p> : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function AdaptiveWorkspace({
  game,
  mode = "docked",
}: {
  game: GameId;
  mode?: "docked" | "standalone";
}) {
  const proposals = useAppStore((s) => s.proposals[game] ?? EMPTY);
  const pins = useAppStore((s) => s.states[game]?.pins ?? EMPTY);
  const relevant = useAppStore((s) => s.relevantNow[game]);
  const open = useAppStore((s) => s.workspaceOpen);
  const setOpen = useAppStore((s) => s.setWorkspaceOpen);
  const activeTab = useAppStore((s) => s.workspaceTab);
  const setTab = useAppStore((s) => s.setWorkspaceTab);
  const popOutWorkspace = useAppStore((s) => s.popOutWorkspace);
  const [popupBlocked, setPopupBlocked] = useState(false);

  const pending = proposals.filter((p) => p.status === "pending");
  const pendingCount = pending.reduce((n, p) => n + p.items.filter((i) => i.status === "pending").length, 0);
  const discoverCount = (relevant?.items ?? []).filter((c) => c.state === "suggested").length;
  const isOpen = mode === "standalone" ? true : open;
  const detachedUrl = `?view=workspace&game=${game}`;

  const popOut = () => {
    const ok = popOutWorkspace(game);
    setPopupBlocked(!ok);
  };

  return (
    <section
      className={`tray aw-workspace ${mode === "standalone" ? "is-standalone" : ""} ${isOpen ? "is-open" : ""}`}
      aria-label="Adaptive Workspace"
    >
      <header className="aw-header">
        <div className="aw-tabs" role="tablist" aria-label="Workspace tabs">
          <button
            type="button"
            role="tab"
            aria-selected={isOpen && activeTab === "changes"}
            className={`aw-tab ${isOpen && activeTab === "changes" ? "is-active" : ""}`}
            onClick={() => {
              setTab("changes");
              if (!isOpen) setOpen(true);
            }}
          >
            Changes <span className={`tray-count ${pendingCount ? "has-items" : ""}`}>{pendingCount}</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={isOpen && activeTab === "pinned"}
            className={`aw-tab ${isOpen && activeTab === "pinned" ? "is-active" : ""}`}
            onClick={() => {
              setTab("pinned");
              if (!isOpen) setOpen(true);
            }}
          >
            Pinned <span className="tray-count">{pins.length}</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={isOpen && activeTab === "discover"}
            className={`aw-tab ${isOpen && activeTab === "discover" ? "is-active" : ""}`}
            onClick={() => {
              setTab("discover");
              if (!isOpen) setOpen(true);
            }}
          >
            Discover <span className="tray-count">{discoverCount}</span>
          </button>
        </div>

        <div className="aw-header-actions">
          {!isOpen && pendingCount > 0 ? (
            <span className="aw-hint">Nothing applied until you review &amp; apply.</span>
          ) : null}
          {mode === "docked" ? (
            <>
              {popupBlocked ? (
                <a className="btn btn-small" href={detachedUrl} target="_blank" rel="noopener noreferrer">
                  Open in new tab ↗
                </a>
              ) : (
                <button type="button" className="btn btn-small" onClick={popOut} title="Open Workspace in a separate window">
                  Pop out ↗
                </button>
              )}
              <button
                type="button"
                className="btn btn-small"
                aria-expanded={isOpen}
                aria-label={isOpen ? "Collapse Workspace" : "Expand Workspace"}
                onClick={() => setOpen(!isOpen)}
              >
                {isOpen ? "▾ Hide" : "▴ Open"}
              </button>
            </>
          ) : null}
        </div>
      </header>

      {isOpen ? (
        <div className="tray-body" role="tabpanel" aria-label={`Workspace ${activeTab}`}>
          {activeTab === "changes" ? (
            <>
              {pending.length === 0 ? (
                <p className="tray-empty">
                  No pending changes. Ask the assistant for suggestions or open <strong>Discover</strong> to prepare changes for review.
                </p>
              ) : null}
              {pending.map((p) => (
                <ProposalBlock key={p.id} proposal={p} />
              ))}
            </>
          ) : activeTab === "pinned" ? (
            <PinnedWorkspaceTab game={game} />
          ) : (
            <RelevantNow game={game} />
          )}
        </div>
      ) : null}
    </section>
  );
}
