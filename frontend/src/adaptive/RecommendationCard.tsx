import { useState, type ReactNode } from "react";
import { descriptionSourceLabel, verificationLabel } from "../lib/format";

export type CardState = "suggested" | "staged" | "applied" | "dismissed" | "locked" | "changed" | "stale" | "undone";

const STATE_LABEL: Record<CardState, string> = {
  suggested: "Suggested",
  staged: "Staged — awaiting your approval",
  applied: "Applied",
  dismissed: "Dismissed",
  locked: "Locked by you",
  changed: "Setting changed since",
  stale: "No longer available",
  undone: "Undone",
};

export interface CardModel {
  key: string;
  label: string;
  path: string;
  from: string;
  to: string;
  whatItDoes: string;
  whatItDoesSource: string;
  why: string;
  whyOrigin: string; // e.g. "Local AI (gemma4…)" or "Rule-based"
  tradeoff: string | null;
  basedOn: string[];
  crossGame: boolean;
  dimensionLabel: string | null;
  verificationStatus: string;
  sourceURL: string;
  provenance: "ai" | "fallback" | "rules";
  state: CardState;
}

export function RecommendationCard({
  card,
  open,
  onToggle,
  onShow,
  onStage,
  onDismiss,
  extraActions,
}: {
  card: CardModel;
  open?: boolean;
  onToggle?: (open: boolean) => void;
  onShow: () => void;
  onStage?: () => void;
  onDismiss?: () => void;
  extraActions?: ReactNode;
}) {
  const [localOpen, setLocalOpen] = useState(false);
  const expanded = open ?? localOpen;
  const toggle = () => (onToggle ? onToggle(!expanded) : setLocalOpen(!expanded));
  const [showWhy, setShowWhy] = useState(false);
  const resolved = card.state !== "suggested" && card.state !== "changed";

  return (
    <article className={`rec-card prov-${card.provenance} state-${card.state}`} aria-label={`Suggestion: ${card.label}`}>
      <header className="rec-head">
        <span className={`prov-badge prov-${card.provenance}`}>{card.provenance === "ai" ? "Local AI" : card.provenance === "fallback" ? "Offline fallback · not AI" : "Rule-based"}</span>
        <span className={`state-badge st-${card.state}`}>{STATE_LABEL[card.state]}</span>
      </header>
      <div className="rec-title">
        <strong>{card.label}</strong>
        <span className="rec-path">{card.path}</span>
      </div>
      <div className="rec-change" aria-label={`Change from ${card.from} to ${card.to}`}>
        <span className="rec-from">{card.from}</span>
        <span className="rec-arrow" aria-hidden>→</span>
        <span className="rec-to">{card.to}</span>
      </div>
      {card.basedOn.length ? (
        <p className={`rec-basis ${card.crossGame ? "is-cross" : ""}`}>
          {card.crossGame ? "↪ " : ""}Based on {card.basedOn.join("; ")}
          {card.crossGame ? <em> — options differ between games; please confirm.</em> : null}
        </p>
      ) : null}
      <div className="rec-why">
        <span className="layer-label">Why this may help your goal <small>({card.whyOrigin})</small></span>
        <p>{card.why}</p>
      </div>
      <button type="button" className="rec-more" aria-expanded={expanded} onClick={toggle}>
        {expanded ? "Hide details" : "What it does & trade-offs"}
      </button>
      {expanded ? (
        <div className="rec-layers">
          <div className="layer">
            <span className="layer-label">What it does <small>(from {descriptionSourceLabel(card.whatItDoesSource)})</small></span>
            <p>{card.whatItDoes}</p>
          </div>
          {card.tradeoff ? (
            <div className="layer">
              <span className="layer-label">Trade-offs &amp; uncertainty</span>
              <p>{card.tradeoff}</p>
            </div>
          ) : null}
          <p className="layer-source">
            {verificationLabel(card.verificationStatus)} ·{" "}
            <a href={card.sourceURL} target="_blank" rel="noreferrer noopener">source</a>
          </p>
        </div>
      ) : null}
      {showWhy ? (
        <div className="rec-evidence" role="note">
          <span className="layer-label">Why this appeared</span>
          <ul>
            {card.dimensionLabel ? <li>Matches the goal: <strong>{card.dimensionLabel}</strong></li> : null}
            {card.basedOn.map((b) => <li key={b}>Evidence: {b}</li>)}
            <li>Origin: {card.provenance === "ai" ? "selected by the local model, then checked against the catalogue, your locks and allowed values" : "fixed ranking rule over catalogue goal tags (not AI)"}</li>
            <li>Nothing changes until you stage and apply it.</li>
          </ul>
        </div>
      ) : null}
      <footer className="rec-actions">
        <button type="button" className="btn btn-small" onClick={onShow} title="Highlight this setting in its normal place in the menu">Show in settings</button>
        {onStage && !resolved ? <button type="button" className="btn btn-small btn-primary" onClick={onStage}>Stage for review</button> : null}
        <button type="button" className="btn btn-small btn-ghost" aria-expanded={showWhy} onClick={() => setShowWhy((v) => !v)}>Why this?</button>
        {extraActions}
        {onDismiss && !resolved ? <button type="button" className="btn btn-small btn-ghost" onClick={onDismiss}>Dismiss</button> : null}
      </footer>
    </article>
  );
}
