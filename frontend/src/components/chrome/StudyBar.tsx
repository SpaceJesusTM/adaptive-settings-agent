import { useState } from "react";
import { api } from "../../api/client";
import type { GameId } from "../../api/types";
import { gameName } from "../../lib/format";
import { useAppStore } from "../../store/useAppStore";
import { SearchBox } from "./SearchBox";

export function ModelStatusPill({ compact = false }: { compact?: boolean }) {
  const status = useAppStore((s) => s.modelStatus);
  const refresh = useAppStore((s) => s.refreshModelStatus);
  if (!status) return <span className="ai-pill is-unknown">AI status…</span>;
  const det = status.details;
  const title = [
    status.indicatorLabel,
    status.model ? `Model: ${status.model}${det ? ` (${[det.family, det.parameterSize, det.quantization].filter(Boolean).join(", ")})` : ""}` : "Model: not configured",
    status.ollamaVersion ? `Ollama ${status.ollamaVersion} at ${status.baseUrl}` : status.message,
    "Click to re-check.",
  ].join("\n");
  return (
    <button type="button" className={`ai-pill is-${status.indicator}`} title={title} onClick={() => void refresh(true)}
      aria-label={`AI status: ${status.indicatorLabel}`}>
      <span className="ai-dot" aria-hidden />
      {compact ? status.indicatorLabel.split(" ")[0] + (status.indicator === "connected" ? " local AI" : "") : status.indicatorLabel}
      {!compact && status.indicator === "connected" && status.model ? <span className="ai-model">{status.model}</span> : null}
    </button>
  );
}

function StudyControls({ onClose }: { onClose: () => void }) {
  const session = useAppStore((s) => s.session)!;
  const scenarios = useAppStore((s) => s.scenarios);
  const contextTypes = useAppStore((s) => s.contextTypes);
  const relevant = useAppStore((s) => s.relevantNow[session.selectedGame]);
  const reset = useAppStore((s) => s.reset);
  const setAiMode = useAppStore((s) => s.setAiMode);
  const setAdaptation = useAppStore((s) => s.setAdaptation);
  const triggerContext = useAppStore((s) => s.triggerContext);
  const [scenario, setScenario] = useState(session.scenario ?? "default");
  const [confirm, setConfirm] = useState<null | "full" | "ai_only">(null);
  const adaptive = session.condition === "adaptive";
  const hw = session.hardware;

  const exportState = async () => {
    const data = await api.exportState();
    const blob = new Blob([JSON.stringify(data, null, 1)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `csc2524-state-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <div className="study-controls" role="dialog" aria-label="Study controls">
      <div className="sc-head">
        <strong>Study controls</strong>
        <button type="button" className="sc-close" onClick={onClose} aria-label="Close study controls">×</button>
      </div>
      <fieldset>
        <legend>Scenario (synthetic demo state)</legend>
        <select value={scenario} onChange={(e) => setScenario(e.target.value)} aria-label="Scenario">
          {scenarios.map((sc) => <option key={sc.name} value={sc.name}>{sc.title}</option>)}
        </select>
        <p className="sc-help">{scenarios.find((sc) => sc.name === scenario)?.description}</p>
        {confirm ? (
          <div className="sc-confirm">
            <span>{confirm === "full" ? "Reset values, profile, pins, locks and history to this scenario?" : "Clear proposals, chat, Relevant Now and session goals (keep values and history)?"} A backup is saved first.</span>
            <button type="button" className="btn btn-danger" onClick={() => { void reset(scenario, confirm); setConfirm(null); onClose(); }}>Confirm reset</button>
            <button type="button" className="btn" onClick={() => setConfirm(null)}>Cancel</button>
          </div>
        ) : (
          <div className="sc-row">
            <button type="button" className="btn" onClick={() => setConfirm("full")}>Full reset</button>
            <button type="button" className="btn" onClick={() => setConfirm("ai_only")}>Reset AI session only</button>
            <button type="button" className="btn" onClick={() => void exportState()}>Export state</button>
          </div>
        )}
      </fieldset>
      {adaptive ? (
        <>
          <fieldset>
            <legend>Assistant source</legend>
            <label className="sc-radio"><input type="radio" checked={session.aiMode === "local"} onChange={() => void setAiMode("local")} /> Local model (Ollama, exact tag from .env)</label>
            <label className="sc-radio"><input type="radio" checked={session.aiMode === "fallback"} onChange={() => void setAiMode("fallback")} /> Offline fallback (rule-based, not AI)</label>
          </fieldset>
          <fieldset>
            <legend>Adaptation</legend>
            <label className="sc-radio"><input type="checkbox" checked={session.adaptationEnabled} onChange={(e) => void setAdaptation(e.target.checked)} /> Proactive “Relevant now” suggestions</label>
            <p className="sc-help">Turning this off removes proactive suggestions; the full menu, chat on request, pins and locks stay available.</p>
          </fieldset>
          <fieldset>
            <legend>Simulated context event ({gameName(session.selectedGame)})</legend>
            <div className="sc-events">
              {contextTypes.map((c) => (
                <button key={c.eventType} type="button" className={`btn btn-small ${relevant?.context?.eventType === c.eventType ? "is-on" : ""}`}
                  onClick={() => void triggerContext(session.selectedGame, c.eventType)}>{c.label}</button>
              ))}
              {relevant?.context ? <button type="button" className="btn btn-small" onClick={() => void triggerContext(session.selectedGame, null)}>Clear event</button> : null}
            </div>
            <p className="sc-help">Events are simulated for the study; nothing is measured on this computer.</p>
          </fieldset>
        </>
      ) : null}
      <fieldset>
        <legend>Simulated PC (scenario, not this computer)</legend>
        <p className="sc-help">{hw.gpu} · {hw.cpuCores} cores · {hw.ramGB} GB RAM · {hw.displayRefreshHz} Hz display · G-Sync: {hw.gsyncDisplay ? "yes" : "no"}</p>
      </fieldset>
    </div>
  );
}

export function StudyBar() {
  const session = useAppStore((s) => s.session)!;
  const switchGame = useAppStore((s) => s.switchGame);
  const setCondition = useAppStore((s) => s.setCondition);
  const setHistoryOpen = useAppStore((s) => s.setHistoryOpen);
  const [controlsOpen, setControlsOpen] = useState(false);
  const game = session.selectedGame;

  return (
    <header className="studybar">
      <div className="sb-brand" title="Adapting Without Rearranging — CSC2524 research prototype (unofficial academic simulation)">
        <span className="sb-logo" aria-hidden>◆</span>
        <span className="sb-titles">
          <strong>Adapting Without Rearranging</strong>
          <small>CSC2524 prototype</small>
        </span>
      </div>
      <span className="sb-sim-pill" role="note">Simulated settings — no changes to VALORANT or CS2</span>
      <div className="sb-seg" role="group" aria-label="Game">
        {(["valorant", "cs2"] as GameId[]).map((g) => (
          <button key={g} type="button" aria-pressed={g === game} className={g === game ? "is-on" : ""} onClick={() => g !== game && void switchGame(g)}>
            {gameName(g)}
          </button>
        ))}
      </div>
      <div className="sb-seg" role="group" aria-label="Study condition">
        <button type="button" aria-pressed={session.condition === "baseline"} className={session.condition === "baseline" ? "is-on" : ""}
          onClick={() => session.condition !== "baseline" && void setCondition("baseline")}>A · Static baseline</button>
        <button type="button" aria-pressed={session.condition === "adaptive"} className={session.condition === "adaptive" ? "is-on" : ""}
          onClick={() => session.condition !== "adaptive" && void setCondition("adaptive")}>B · Adaptive</button>
      </div>
      <SearchBox game={game} />
      <button type="button" className="sb-btn" onClick={() => setHistoryOpen(true)}>History</button>
      <div className="sb-controls">
        <button type="button" className="sb-btn" aria-expanded={controlsOpen} onClick={() => setControlsOpen((o) => !o)}>Study controls</button>
        {controlsOpen ? <StudyControls onClose={() => setControlsOpen(false)} /> : null}
      </div>
    </header>
  );
}
