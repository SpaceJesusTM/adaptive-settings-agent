import { useState } from "react";
import type { GameId, RelevantCard } from "../api/types";
import { EMPTY, useAppStore } from "../store/useAppStore";
import { RecommendationCard, type CardModel } from "./RecommendationCard";

function toCard(c: RelevantCard): CardModel {
  return {
    key: c.cardId,
    label: c.label,
    path: c.path,
    from: c.currentDisplay,
    to: c.targetDisplay,
    whatItDoes: c.whatItDoes,
    whatItDoesSource: c.whatItDoesSource,
    why: c.why,
    whyOrigin: c.whyBasis === "official" ? "rule-based; reason from official game documentation" : "rule-based; editorial reason",
    tradeoff: c.tradeoff,
    basedOn: c.basedOn,
    crossGame: c.crossGame,
    dimensionLabel: c.dimensionLabel,
    verificationStatus: c.verificationStatus,
    sourceURL: c.sourceURL,
    provenance: "rules",
    state: c.state === "changed" ? "changed" : c.state,
  };
}

const DISMISS_REASONS = ["Not relevant to me", "Already tried it", "I prefer my current value"];

export function RelevantNow({ game }: { game: GameId }) {
  const rn = useAppStore((s) => s.relevantNow[game]);
  const openCards = useAppStore((s) => s.openCards);
  const setCardOpen = useAppStore((s) => s.setCardOpen);
  const refresh = useAppStore((s) => s.refreshRelevantNow);
  const dismiss = useAppStore((s) => s.dismissCard);
  const stage = useAppStore((s) => s.stage);
  const goToSetting = useAppStore((s) => s.goToSetting);
  const triggerContext = useAppStore((s) => s.triggerContext);
  const [collapsed, setCollapsed] = useState(false);
  const [dismissing, setDismissing] = useState<string | null>(null);
  const anyOpen = (rn?.items ?? []).some((c) => openCards[c.cardId]);

  return (
    <section className="rn" aria-label="Relevant now">
      <header className="rn-head">
        <button type="button" className="rn-title" aria-expanded={!collapsed} onClick={() => setCollapsed((c) => !c)}>
          Relevant now <span className="rn-count">{(rn?.items ?? []).filter((c) => c.state === "suggested").length}</span>
        </button>
        <span className="rn-sub">Rule-based · from your goals, saved preferences and simulated context</span>
      </header>
      {collapsed ? null : (
        <>
          {rn?.context ? (
            <div className="rn-context" role="note">
              <span className="sim-tag">Simulated event</span> {rn.context.label}
              <button type="button" className="link" onClick={() => void triggerContext(game, null)}>clear</button>
            </div>
          ) : null}
          {rn?.disabled ? <p className="rn-empty">Proactive suggestions are switched off (Study controls → Adaptation).</p> : null}
          {rn?.updateAvailable ? (
            <div className="rn-update">
              <span>New suggestions are available based on newer evidence.</span>
              <button type="button" className="btn btn-small" disabled={anyOpen} title={anyOpen ? "Close the open card first — cards never reshuffle while you are reading one." : undefined}
                onClick={() => void refresh(game)}>Refresh</button>
            </div>
          ) : null}
          {!rn?.disabled && (rn?.items ?? []).length === 0 ? (
            <p className="rn-empty">
              {rn?.updateAvailable
                ? "Refresh to see suggestions for your current goals."
                : rn?.hasEvidence
                  ? "Your current settings already match your goals (or the relevant settings are locked or staged)."
                  : "No suggestions yet. Describe a goal in the chat, save a preference, or trigger a simulated event in Study controls."}
            </p>
          ) : null}
          <div className="rn-cards">
            {(rn?.items ?? []).map((c) => (
              <div key={c.cardId} className="rn-card-wrap">
                <RecommendationCard
                  card={toCard(c)}
                  open={Boolean(openCards[c.cardId])}
                  onToggle={(o) => setCardOpen(c.cardId, o)}
                  onShow={() => goToSetting(game, c.settingId, "assistant")}
                  onStage={() => void stage(game, [c], "rules", null, `Relevant now: ${c.label}`)}
                  onDismiss={() => setDismissing(c.cardId)}
                />
                {dismissing === c.cardId ? (
                  <div className="dismiss-box" role="group" aria-label={`Why dismiss ${c.label}?`}>
                    <span>Why dismiss? (kept as feedback; it will not reappear unless your goals change)</span>
                    {DISMISS_REASONS.map((r) => (
                      <button key={r} type="button" className="btn btn-small" onClick={() => { void dismiss(game, c.settingId, r); setDismissing(null); }}>{r}</button>
                    ))}
                    <button type="button" className="btn btn-small btn-ghost" onClick={() => setDismissing(null)}>Cancel</button>
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </>
      )}
    </section>
  );
}

export function PinnedStrip({ game }: { game: GameId }) {
  const pins = useAppStore((s) => s.states[game]?.pins ?? EMPTY);
  const byId = useAppStore((s) => s.byId[game]);
  const values = useAppStore((s) => s.states[game]?.values);
  const goToSetting = useAppStore((s) => s.goToSetting);
  if (!pins.length || !byId) return null;
  return (
    <section className="pinned" aria-label="Pinned settings">
      <span className="pinned-title">📌 Pinned</span>
      <ul>
        {pins.map((id) => {
          const s = byId[id];
          if (!s) return null;
          const v = values?.[id]?.value;
          const label = s.validOptions?.find((o) => o.value === String(v))?.label ?? String(v ?? "");
          return (
            <li key={id}>
              <button type="button" className="pin-chip" title={`${s.canonicalPath} — go to setting`} onClick={() => goToSetting(game, id, "pin")}>
                <span>{s.exactLabel}</span>
                {s.controlType !== "slider" ? <em>{label}</em> : null}
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
