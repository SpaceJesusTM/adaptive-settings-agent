import { useEffect, useState } from "react";
import type { GameId, RelevantCard } from "../api/types";
import { gameName } from "../lib/format";
import { EMPTY, useAppStore } from "../store/useAppStore";
import { RecommendationCard, type CardModel } from "./RecommendationCard";

function toCard(c: RelevantCard, experimenterMode: boolean): CardModel {
  const originMap: Record<string, string> = {
    goal_hint: "Catalog goal hint",
    followup_rule: "Companion check",
    onboarding_observation: "Observed setup",
  };
  const originText = experimenterMode
    ? `${originMap[c.whyOrigin ?? ""] ?? "rule-based"}; ${c.whyBasis === "official" ? "official documentation" : "editorial match"}`
    : originMap[c.whyOrigin ?? ""] ?? (c.kind === "inspect" ? "Observed setup" : "Suggestion grounded in game docs");
  return {
    key: c.cardId,
    kind: c.kind ?? "change",
    triggerLabel: c.triggerLabel,
    label: c.label,
    path: c.path,
    from: c.currentDisplay,
    to: c.targetDisplay,
    whatItDoes: c.whatItDoes,
    whatItDoesSource: c.whatItDoesSource,
    why: c.why,
    whyOrigin: originText,
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

const DISMISS_REASONS = ["Not relevant to me", "Already checked it", "I prefer my current value"];

const GROUP_ORDER: { key: NonNullable<RelevantCard["triggerGroup"]>; label: (game: GameId) => string }[] = [
  { key: "context_event", label: () => "Responding to a simulated event" },
  { key: "followup", label: () => "Something worth checking after your recent change" },
  { key: "onboarding", label: (g) => `Getting started in ${gameName(g)}` },
  { key: "goal_or_preference", label: () => "Based on your goals & saved priorities" },
];

export function RelevantNow({ game }: { game: GameId }) {
  const rn = useAppStore((s) => s.relevantNow[game]);
  const openCards = useAppStore((s) => s.openCards);
  const setCardOpen = useAppStore((s) => s.setCardOpen);
  const refresh = useAppStore((s) => s.refreshRelevantNow);
  const dismiss = useAppStore((s) => s.dismissCard);
  const markChecked = useAppStore((s) => s.markDiscoverChecked);
  const revisitOnboarding = useAppStore((s) => s.revisitOnboarding);
  const stage = useAppStore((s) => s.stage);
  const requestFocus = useAppStore((s) => s.requestFocusInMainWindow);
  const togglePin = useAppStore((s) => s.togglePin);
  const experimenterMode = useAppStore((s) => s.experimenterMode);
  const pins = useAppStore((s) => s.states[game]?.pins ?? EMPTY);
  const triggerContext = useAppStore((s) => s.triggerContext);
  const markDiscoverSeen = useAppStore((s) => s.markDiscoverSeen);
  const [dismissing, setDismissing] = useState<string | null>(null);
  const items = rn?.items ?? [];
  const anyOpen = items.some((c) => openCards[c.cardId]);
  const activeCount = items.filter((c) => c.state === "suggested" || c.state === "changed").length;

  useEffect(() => {
    if (items.length > 0) {
      markDiscoverSeen(game);
    }
  }, [game, items, markDiscoverSeen]);

  const hasConfirmedOrDeliberateOb = items.some(
    (c) =>
      (c.triggerGroup ?? "goal_or_preference") === "onboarding" &&
      (c.basedOn?.some((b) => /remembered|confirmed|manual|edit/i.test(b)) ?? false),
  );
  const effectiveOrder = hasConfirmedOrDeliberateOb
    ? GROUP_ORDER
    : [
        GROUP_ORDER[0],
        GROUP_ORDER[1],
        GROUP_ORDER[3],
        GROUP_ORDER[2],
      ];

  const groups = effectiveOrder.map((g) => ({
    ...g,
    title: g.label(game),
    cards: items.filter((c) => (c.triggerGroup ?? "goal_or_preference") === g.key),
  })).filter((g) => g.cards.length > 0);

  return (
    <section className="rn" aria-label="Discover suggestions">
      <header className="rn-head">
        <div className="rn-head-top">
          <span className="rn-title">
            Discover <span className="rn-count">{activeCount}</span>
          </span>
          {rn?.canRevisitOnboarding ? (
            <button type="button" className="link rn-revisit" onClick={() => void revisitOnboarding(game)}>
              Revisit first-time checks
            </button>
          ) : null}
        </div>
        <span className="rn-sub">
          Timely controls worth inspecting based on onboarding, recent changes, context, or priorities — nothing changes until you act.
        </span>
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
          <span>New Discover items are available based on your latest goals, priorities, or changes.</span>
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
      {!rn?.disabled && items.length === 0 ? (
        <p className="rn-empty">
          {rn?.updateAvailable
            ? "Click Refresh above to view newly relevant suggestions."
            : rn?.hasEvidence
              ? "Nothing pending right now — your current settings align with your active priorities."
              : "No proactive checks pending. Ask the assistant about a goal or confirm preferences to surface relevant controls."}
        </p>
      ) : null}
      {groups.map((grp) => (
        <div key={grp.key} className="rn-group">
          <h4 className="rn-group-title">{grp.title}</h4>
          <div className="rn-cards">
            {grp.cards.map((c) => {
              const isPinned = pins.includes(c.settingId);
              return (
                <div key={c.cardId} className="rn-card-wrap">
                  <RecommendationCard
                    card={toCard(c, experimenterMode)}
                    open={Boolean(openCards[c.cardId])}
                    onToggle={(o) => setCardOpen(c.cardId, o)}
                    onShow={() => requestFocus(game, c.settingId)}
                    onStage={c.kind === "inspect" ? undefined : () => void stage(game, [c], "rules", null, `Discover: ${c.label}`)}
                    onMarkChecked={c.kind === "inspect" || c.checkId ? () => void markChecked(game, c.checkId ?? c.ruleId ?? c.cardId) : undefined}
                    onDismiss={() => setDismissing(c.cardId)}
                    extraActions={
                      <button type="button" className="btn btn-small btn-ghost" onClick={() => void togglePin(game, c.settingId)}>
                        {isPinned ? "Unpin" : "Pin"}
                      </button>
                    }
                  />
                  {dismissing === c.cardId ? (
                    <div className="dismiss-box" role="group" aria-label={`Why dismiss ${c.label}?`}>
                      <span>Why dismiss? (Suppressed until your priorities change.)</span>
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
        </div>
      ))}
    </section>
  );
}
