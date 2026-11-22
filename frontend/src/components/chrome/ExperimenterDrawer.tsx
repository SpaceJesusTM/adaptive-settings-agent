import { useState } from "react";
import { api } from "../../api/client";
import { gameName } from "../../lib/format";
import { useAppStore } from "../../store/useAppStore";

export function ExperimenterDrawer({ onClose }: { onClose: () => void }) {
  const session = useAppStore((s) => s.session)!;
  const modelStatus = useAppStore((s) => s.modelStatus);
  const scenarios = useAppStore((s) => s.scenarios);
  const contextTypes = useAppStore((s) => s.contextTypes);
  const relevant = useAppStore((s) => s.relevantNow[session.selectedGame]);
  const reset = useAppStore((s) => s.reset);
  const setAiMode = useAppStore((s) => s.setAiMode);
  const setAdaptation = useAppStore((s) => s.setAdaptation);
  const triggerContext = useAppStore((s) => s.triggerContext);
  const refreshModelStatus = useAppStore((s) => s.refreshModelStatus);
  const setExperimenterMode = useAppStore((s) => s.setExperimenterMode);
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
        <strong>Experimenter controls</strong>
        <div className="sc-head-actions">
          <button type="button" className="btn btn-small" onClick={() => { setExperimenterMode(false); onClose(); }}>
            Switch to participant view
          </button>
          <button type="button" className="sc-close" onClick={onClose} aria-label="Close study controls">
            ×
          </button>
        </div>
      </div>

      <fieldset>
        <legend>Scenario (synthetic demo state)</legend>
        <select value={scenario} onChange={(e) => setScenario(e.target.value)} aria-label="Scenario">
          {scenarios.map((sc) => (
            <option key={sc.name} value={sc.name}>
              {sc.title}
            </option>
          ))}
        </select>
        <p className="sc-help">{scenarios.find((sc) => sc.name === scenario)?.description}</p>
        {confirm ? (
          <div className="sc-confirm">
            <span>
              {confirm === "full"
                ? "Reset values, profile, pins, locks and history to this scenario?"
                : "Clear proposals, chat, Discover and session goals (keep values and history)?"}{" "}
              A backup is saved first.
            </span>
            <button type="button" className="btn btn-danger" onClick={() => { void reset(scenario, confirm); setConfirm(null); onClose(); }}>
              Confirm reset
            </button>
            <button type="button" className="btn" onClick={() => setConfirm(null)}>
              Cancel
            </button>
          </div>
        ) : (
          <div className="sc-row">
            <button type="button" className="btn" onClick={() => setConfirm("full")}>
              Full reset
            </button>
            <button type="button" className="btn" onClick={() => setConfirm("ai_only")}>
              Reset AI session only
            </button>
            <button type="button" className="btn" onClick={() => void exportState()}>
              Export state
            </button>
          </div>
        )}
      </fieldset>

      {adaptive ? (
        <>
          <fieldset>
            <legend>Assistant source &amp; Ollama diagnostics</legend>
            <label className="sc-radio">
              <input type="radio" checked={session.aiMode === "local"} onChange={() => void setAiMode("local")} /> Local model (Ollama, exact tag from .env)
            </label>
            <label className="sc-radio">
              <input type="radio" checked={session.aiMode === "fallback"} onChange={() => void setAiMode("fallback")} /> Offline fallback (rule-based, not AI)
            </label>
            <p className="sc-help">
              Status: <strong>{modelStatus?.indicatorLabel ?? "Checking…"}</strong>
              {modelStatus?.model ? ` · Model: ${modelStatus.model}` : ""}
              {modelStatus?.details?.quantization ? ` (${modelStatus.details.parameterSize ?? ""} ${modelStatus.details.quantization})` : ""}
              {modelStatus?.ollamaVersion ? ` · Ollama ${modelStatus.ollamaVersion}` : ""}
              {" · "}
              <button type="button" className="link" onClick={() => void refreshModelStatus(true)}>
                Re-check
              </button>
            </p>
            {modelStatus?.message ? <p className="sc-help">{modelStatus.message}</p> : null}
          </fieldset>

          <fieldset>
            <legend>Adaptation</legend>
            <label className="sc-radio">
              <input type="checkbox" checked={session.adaptationEnabled} onChange={(e) => void setAdaptation(e.target.checked)} /> Proactive “Discover” suggestions
            </label>
            <p className="sc-help">Turning this off removes proactive suggestions; the full menu, chat on request, pins and locks stay available.</p>
          </fieldset>

          <fieldset>
            <legend>Simulated context event ({gameName(session.selectedGame)})</legend>
            <div className="sc-events">
              {contextTypes.map((c) => (
                <button
                  key={c.eventType}
                  type="button"
                  className={`btn btn-small ${relevant?.context?.eventType === c.eventType ? "is-on" : ""}`}
                  onClick={() => void triggerContext(session.selectedGame, c.eventType)}
                >
                  {c.label}
                </button>
              ))}
              {relevant?.context ? (
                <button type="button" className="btn btn-small" onClick={() => void triggerContext(session.selectedGame, null)}>
                  Clear event
                </button>
              ) : null}
            </div>
            <p className="sc-help">Events are simulated for the study; nothing is measured on this computer.</p>
          </fieldset>
        </>
      ) : null}

      <fieldset>
        <legend>Simulated PC (scenario, not this computer)</legend>
        <p className="sc-help">
          {String(hw.gpu ?? "")} · {String(hw.cpuCores ?? "")} cores · {String(hw.ramGB ?? "")} GB RAM ·{" "}
          {String(hw.displayRefreshHz ?? "")} Hz display · G-Sync: {hw.gsyncDisplay ? "yes" : "no"}
        </p>
      </fieldset>
    </div>
  );
}
