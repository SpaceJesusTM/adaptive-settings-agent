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
  const requestFocus = useAppStore((s) => s.requestFocusInMainWindow);
  const togglePin = useAppStore((s) => s.togglePin);
  const pins = useAppStore((s) => s.states[game]?.pins ?? EMPTY);
  const triggerContext = useAppStore((s) => s.triggerContext);
  const [dismissing, setDismissing] = useState<string | null>(null);
  const anyOpen = (rn?.items ?? []).some((c) => openCards[c.cardId]);

  return (
    <section className="rn" aria-label="Discover suggestions">
      <header className="rn-head">
        <span className="rn-title">
          Discover <span className="rn-count">{(rn?.items ?? []).filter((c) => c.state === "suggested").length}</span>
        </span>
        <span className="rn-sub">Unsolicited suggestions from your goals and saved preferences — never added to Changes until you prepare them.</span>
      </header>
      {rn?.context ? (
        <div className="rn-context" role="note">
          <span className="sim-tag">Simulated event</span> {rn.context.label}
          <button type="button" className="link" onClick={() => void triggerContext(game, null)}>
            clear
          </button>
        </div>
      ) : null}
      {rn?.disabled ? <p className="rn-empty">Proactive Discover suggestions are switched off (Study controls → Adaptation).</p> : null}
      {rn?.updateAvailable ? (
        <div className="rn-update">
          <span>New suggestions are available based on newer goals or preferences.</span>
          <button
            type="button"
            className="btn btn-small"
            disabled={anyOpen}
            title={anyOpen ? "Close the open card first — cards never reshuffle while you are examining one." : undefined}
            onClick={() => void refresh(game)}
          >
            Refresh
          </button>
        </div>
      ) : null}
      {!rn?.disabled && (rn?.items ?? []).length === 0 ? (
        <p className="rn-empty">
          {rn?.updateAvailable
            ? "Refresh to see suggestions for your current goals."
            : rn?.hasEvidence
              ? "Your current settings already match your goals (or the relevant settings are locked or queued in Changes)."
              : "No proactive suggestions yet. Describe a goal in chat or save a preference to see relevant settings."}
        </p>
      ) : null}
      <div className="rn-cards">
        {(rn?.items ?? []).map((c) => {
          const isPinned = pins.includes(c.settingId);
          return (
            <div key={c.cardId} className="rn-card-wrap">
              <RecommendationCard
                card={toCard(c)}
                open={Boolean(openCards[c.cardId])}
                onToggle={(o) => setCardOpen(c.cardId, o)}
                onShow={() => requestFocus(game, c.settingId)}
                onStage={() => void stage(game, [c], "rules", null, `Discover: ${c.label}`)}
                onDismiss={() => setDismissing(c.cardId)}
                extraActions={
                  <button type="button" className="btn btn-small btn-ghost" onClick={() => void togglePin(game, c.settingId)}>
                    {isPinned ? "Unpin" : "Pin"}
                  </button>
                }
              />
              {dismissing === c.cardId ? (
                <div className="dismiss-box" role="group" aria-label={`Why dismiss ${c.label}?`}>
                  <span>Why dismiss? (It will not reappear unless your goals change.)</span>
                  {DISMISS_REASONS.map((r) => (
                    <button
                      key={r}
                      type="button"
                      className="btn btn-small"
                      onClick={() => {
                        void dismiss(game, c.settingId, r);
                        setDismissing(null);
                      }}
                    >
                      {r}
                    </button>
                  ))}
                  <button type="button" className="btn btn-small btn-ghost" onClick={() => setDismissing(null)}>
                    Cancel
                  </button>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </section>
  );
}
