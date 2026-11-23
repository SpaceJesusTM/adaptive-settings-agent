import { useState } from "react";
import type { GameId } from "../../api/types";
import { gameName } from "../../lib/format";
import { EMPTY, useAppStore } from "../../store/useAppStore";
import { ExperimenterDrawer } from "./ExperimenterDrawer";
import { SearchBox } from "./SearchBox";

export function ModelStatusPill({ compact = false }: { compact?: boolean }) {
  const status = useAppStore((s) => s.modelStatus);
  const experimenterMode = useAppStore((s) => s.experimenterMode);
  const refresh = useAppStore((s) => s.refreshModelStatus);

  if (!status) return <span className="ai-pill is-unknown">Checking assistant…</span>;

  const det = status.details;
  const offline = status.indicator !== "connected";
  const participantText = offline ? "Assistant offline — using basic suggestions" : "Assistant ready";

  if (!experimenterMode) {
    if (!offline && compact) return null;
    return (
      <span
        className={`ai-pill is-${status.indicator}`}
        role="status"
        aria-label={participantText}
        title={offline ? "Local AI model is currently unavailable; suggestions come from basic rules." : "Local assistant connected"}
      >
        <span className="ai-dot" aria-hidden />
        {participantText}
      </span>
    );
  }

  const title = [
    status.indicatorLabel,
    status.model
      ? `Model: ${status.model}${det ? ` (${[det.family, det.parameterSize, det.quantization].filter(Boolean).join(", ")})` : ""}`
      : "Model: not configured",
    status.ollamaVersion ? `Ollama ${status.ollamaVersion} at ${status.baseUrl}` : status.message,
    "Click to re-check.",
  ].join("\n");

  return (
    <button
      type="button"
      className={`ai-pill is-${status.indicator}`}
      title={title}
      onClick={() => void refresh(true)}
      aria-label={`AI status: ${status.indicatorLabel}`}
    >
      <span className="ai-dot" aria-hidden />
      {compact ? status.indicatorLabel : status.indicatorLabel}
      {!compact && status.indicator === "connected" && status.model ? <span className="ai-model">{status.model}</span> : null}
    </button>
  );
}

export function StudyBar() {
  const session = useAppStore((s) => s.session)!;
  const experimenterMode = useAppStore((s) => s.experimenterMode);
  const setExperimenterMode = useAppStore((s) => s.setExperimenterMode);
  const switchGame = useAppStore((s) => s.switchGame);
  const setCondition = useAppStore((s) => s.setCondition);
  const setHistoryOpen = useAppStore((s) => s.setHistoryOpen);
  const workspaceOpen = useAppStore((s) => s.workspaceOpen);
  const openWorkspace = useAppStore((s) => s.openWorkspace);
  const setWorkspaceOpen = useAppStore((s) => s.setWorkspaceOpen);
  const detachedWorkspaceActive = useAppStore((s) => s.detachedWorkspaceActive);
  const focusDetachedWorkspace = useAppStore((s) => s.focusDetachedWorkspace);
  const recallDetachedWorkspace = useAppStore((s) => s.recallDetachedWorkspace);
  const proposals = useAppStore((s) => s.proposals[session.selectedGame] ?? EMPTY);
  const [controlsOpen, setControlsOpen] = useState(false);

  const game = session.selectedGame;
  const adaptive = session.condition === "adaptive";
  const pendingCount = proposals
    .filter((p) => p.status === "pending")
    .reduce((n, p) => n + p.items.filter((i) => i.status === "pending").length, 0);

  return (
    <header className="studybar">
      <div className="sb-brand" title="Adaptive Settings Simulator (unofficial academic research prototype)">
        <span className="sb-logo" aria-hidden>◆</span>
        <span className="sb-titles">
          <strong>{experimenterMode ? "Adapting Without Rearranging" : "Settings Assistant"}</strong>
          <small>{experimenterMode ? "CSC2524 prototype · Experimenter" : "Academic simulation"}</small>
        </span>
      </div>

      <span className="sb-sim-pill" role="note">
        Simulated settings — no real changes to VALORANT or CS2
      </span>

      <div className="sb-seg" role="group" aria-label="Game">
        {(["valorant", "cs2"] as GameId[]).map((g) => (
          <button key={g} type="button" aria-pressed={g === game} className={g === game ? "is-on" : ""} onClick={() => g !== game && void switchGame(g)}>
            {gameName(g)}
          </button>
        ))}
      </div>

      {experimenterMode ? (
        <div className="sb-seg" role="group" aria-label="Study condition">
          <button
            type="button"
            aria-pressed={session.condition === "baseline"}
            className={session.condition === "baseline" ? "is-on" : ""}
            onClick={() => session.condition !== "baseline" && void setCondition("baseline")}
          >
            A · Static baseline
          </button>
          <button
            type="button"
            aria-pressed={session.condition === "adaptive"}
            className={session.condition === "adaptive" ? "is-on" : ""}
            onClick={() => session.condition !== "adaptive" && void setCondition("adaptive")}
          >
            B · Adaptive
          </button>
        </div>
      ) : null}

      <SearchBox game={game} />

      <button type="button" className="sb-btn" onClick={() => setHistoryOpen(true)}>
        History
      </button>

      {adaptive ? (
        detachedWorkspaceActive ? (
          <div className="sb-detached-group" role="status" aria-label="Workspace relocated to detached window">
            <span className="sb-detached-pill">
              Workspace popped out{pendingCount ? ` (${pendingCount})` : ""}
            </span>
            <button type="button" className="sb-btn is-accent" onClick={focusDetachedWorkspace} title="Bring detached workspace window to front">
              Focus
            </button>
            <button type="button" className="sb-btn" onClick={() => void recallDetachedWorkspace()} title="Close detached view and restore assistant and workspace here">
              Dock here
            </button>
          </div>
        ) : (
          <button
            type="button"
            className={`sb-btn ${pendingCount ? "is-accent" : ""}`}
            aria-expanded={workspaceOpen}
            onClick={() => (workspaceOpen ? setWorkspaceOpen(false) : openWorkspace("changes"))}
          >
            Workspace{pendingCount ? ` (${pendingCount})` : ""}
          </button>
        )
      ) : null}

      {adaptive && !experimenterMode ? <ModelStatusPill compact /> : null}

      {experimenterMode ? (
        <div className="sb-controls">
          <button type="button" className="sb-btn" aria-expanded={controlsOpen} onClick={() => setControlsOpen((o) => !o)}>
            Study controls
          </button>
          {controlsOpen ? <ExperimenterDrawer onClose={() => setControlsOpen(false)} /> : null}
        </div>
      ) : null}

      <button
        type="button"
        className={`sb-btn sb-btn-subtle ${experimenterMode ? "is-on" : ""}`}
        aria-pressed={experimenterMode}
        title="Local study experimenter mode toggle (reveals A/B condition, scenarios, and diagnostics)"
        onClick={() => {
          const next = !experimenterMode;
          setExperimenterMode(next);
          if (!next) setControlsOpen(false);
        }}
      >
        {experimenterMode ? "Experimenter ✓" : "Experimenter"}
      </button>
    </header>
  );
}
