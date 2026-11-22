import { useEffect, useState } from "react";
import type { Setting } from "../../api/types";
import { availability } from "../../lib/availability";
import { rowDomId, verificationLabel } from "../../lib/format";
import { useAppStore } from "../../store/useAppStore";
import { SettingControl } from "../controls/Controls";
import type { GameView } from "./useGameView";

const HIGHLIGHT_MS = 2800;

export function SettingRow({ setting, view }: { setting: Setting; view: GameView }) {
  const { game } = view;
  const highlight = useAppStore((s) => s.highlight);
  const changeSetting = useAppStore((s) => s.changeSetting);
  const togglePin = useAppStore((s) => s.togglePin);
  const toggleLock = useAppStore((s) => s.toggleLock);
  const prefill = useAppStore((s) => s.prefillComposer);
  const [flash, setFlash] = useState(false);

  useEffect(() => {
    if (highlight && highlight.game === game && highlight.settingId === setting.id) {
      setFlash(true);
      const t = window.setTimeout(() => setFlash(false), HIGHLIGHT_MS);
      return () => window.clearTimeout(t);
    }
    return undefined;
  }, [highlight, game, setting.id]);

  const av = availability(setting, view.byKey, view.values, view.hardware);
  if (av.hidden || !view.state) return null;
  const value = view.values[setting.id];
  const labelId = `lbl-${rowDomId(setting.id)}`;
  const pendingEdit = view.pending[setting.id] !== undefined;
  const locked = view.adaptive && view.state.locks.includes(setting.id);
  const pinned = view.adaptive && view.state.pins.includes(setting.id);
  const staged = view.adaptive ? view.staged[setting.id] : undefined;
  const lowConfidence = setting.verificationStatus === "secondary-only" || setting.verificationStatus === "partially-verified";
  const tip = [setting.description, setting.riskOrTradeoffs ? `Trade-off: ${setting.riskOrTradeoffs}` : null, av.disabledReason]
    .filter(Boolean).join("\n\n");

  return (
    <div
      id={rowDomId(setting.id)}
      tabIndex={-1}
      role="group"
      aria-labelledby={labelId}
      data-setting-id={setting.id}
      data-control={setting.controlType}
      className={[
        "setting-row",
        flash ? "is-highlighted" : "",
        av.disabledReason ? "is-disabled" : "",
        pendingEdit ? "is-pending" : "",
        locked ? "is-locked" : "",
        staged ? "is-staged" : "",
      ].join(" ")}
    >
      <div className="row-label">
        <span id={labelId} className="row-label-text" title={tip}>
          {setting.exactLabel}
          {setting.qualifier ? <span className="row-qualifier"> · {setting.qualifier}</span> : null}
        </span>
        {lowConfidence ? (
          <span className="row-provenance" title={`${verificationLabel(setting.verificationStatus)}${setting.verificationNotes ? ` — ${setting.verificationNotes}` : ""}`}
            aria-label={verificationLabel(setting.verificationStatus)}>†</span>
        ) : null}
        {pendingEdit ? <span className="row-pending-dot" title="Changed — not applied until you press Apply Changes" aria-label="Unapplied change" /> : null}
        {view.adaptive ? (
          <span className="row-flags">
            {pinned ? <span className="flag flag-pin" title="Pinned">📌</span> : null}
            {locked ? <span className="flag flag-lock" title="Locked from AI changes (you can still edit it)">🔒</span> : null}
            {staged ? (
              <button type="button" className="chip chip-staged" title={`Staged suggestion: ${staged.item.label} → ${staged.item.effectiveDisplay}. Not applied yet.`}
                onClick={() => useAppStore.getState().openWorkspace("changes")}>
                Staged → {staged.item.effectiveDisplay}
              </button>
            ) : null}
          </span>
        ) : null}
        {view.adaptive && setting.controlType !== "preset" ? (
          <span className="row-tools">
            <button type="button" className={`tool ${pinned ? "is-on" : ""}`} aria-pressed={pinned}
              aria-label={`${pinned ? "Unpin" : "Pin"} ${setting.exactLabel}`} title={pinned ? "Unpin" : "Pin to your list"}
              onClick={() => void togglePin(game, setting.id)}>📌</button>
            <button type="button" className={`tool ${locked ? "is-on" : ""}`} aria-pressed={locked}
              aria-label={`${locked ? "Unlock" : "Lock"} ${setting.exactLabel} ${locked ? "" : "from AI changes"}`.trim()}
              title={locked ? "Unlock (allow AI suggestions again)" : "Lock from AI changes"}
              onClick={() => void toggleLock(game, setting.id)}>{locked ? "🔒" : "🔓"}</button>
            <button type="button" className="tool" aria-label={`Ask the assistant about ${setting.exactLabel}`} title="Ask the assistant"
              onClick={() => prefill(game, `What does ${setting.exactLabel} do, and would changing it help my goal?`)}>?</button>
          </span>
        ) : null}
      </div>
      <div className="row-control" title={av.disabledReason ?? undefined}>
        <SettingControl game={game} setting={setting} value={value} disabled={Boolean(av.disabledReason)} labelId={labelId}
          onChange={(v) => void changeSetting(game, setting.id, v)} />
      </div>
    </div>
  );
}

export function NotSimulated({ note }: { note: string | null }) {
  return (
    <div className="not-simulated" role="note">
      <strong>Not simulated in this prototype.</strong>
      <span>{note ?? "This part of the menu is shown for orientation only."}</span>
    </div>
  );
}
