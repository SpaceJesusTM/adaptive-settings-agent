import { useEffect, useState } from "react";
import type { GameView } from "../../components/settings/useGameView";
import { rowDomId } from "../../lib/format";
import { useAppStore } from "../../store/useAppStore";

export function HudEdgeEditor({ view }: { view: GameView }) {
  const committedX = Number(view.values["cs2.video.hud_edge_x"] ?? 1.0);
  const committedY = Number(view.values["cs2.video.hud_edge_y"] ?? 1.0);
  const applyHudEdge = useAppStore((s) => s.applyHudEdgePositions);
  const togglePin = useAppStore((s) => s.togglePin);
  const toggleLock = useAppStore((s) => s.toggleLock);
  const prefill = useAppStore((s) => s.prefillComposer);
  const highlight = useAppStore((s) => s.highlight);

  const [x, setX] = useState(committedX);
  const [y, setY] = useState(committedY);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setX(committedX);
    setY(committedY);
  }, [committedX, committedY]);

  const settingX = view.byId["cs2.video.hud_edge_x"];
  const settingY = view.byId["cs2.video.hud_edge_y"];
  const dirty = Math.abs(x - committedX) > 1e-4 || Math.abs(y - committedY) > 1e-4;

  // Valve popup_hud_edge_positions.js safezone inset formula:
  // marginTop = marginBottom = (1 - Y) * 50%, marginLeft = marginRight = (1 - X) * 50%
  const padX = `${((1 - x) * 50).toFixed(2)}%`;
  const padY = `${((1 - y) * 50).toFixed(2)}%`;

  const saveDone = async () => {
    setBusy(true);
    await applyHudEdge(Number(x.toFixed(2)), Number(y.toFixed(2)));
    setBusy(false);
  };

  return (
    <div className="cs2-hud-editor" data-testid="cs2-hud-edge-editor">
      <div className="cs2-hud-head">
        <div>
          <h3>HUD Edge Positions</h3>
          <p className="muted">
            Pulls HUD elements inward from the screen edges (<code>safezonex</code> / <code>safezoney</code>). Saves immediately when you press{" "}
            <strong>Done</strong>, independent of Video Graphics Apply Changes.
          </p>
        </div>
        <span className="cs2-hud-sim-pill">Simulated HUD frame preview</span>
      </div>

      <div className="cs2-hud-frame" role="img" aria-label={`Simulated CS2 HUD frame: Horizontal ${(x * 100).toFixed(0)}%, Vertical ${(y * 100).toFixed(0)}%`}>
        <div
          className="cs2-hud-safezone"
          data-testid="cs2-hud-safezone"
          style={{ top: padY, bottom: padY, left: padX, right: padX }}
        >
          <div className="hud-anchor hud-radar">
            <span className="hud-radar-dot" aria-hidden />
            <small>RADAR</small>
          </div>
          <div className="hud-anchor hud-top">
            <span>CT 7 · 1:28 · T 5</span>
          </div>
          <div className="hud-anchor hud-health">
            <strong>+ 100</strong>
            <small>🛡 100</small>
          </div>
          <div className="hud-anchor hud-ammo">
            <strong>30 / 90</strong>
            <small>AK-47</small>
          </div>
        </div>
      </div>

      <div className="cs2-hud-controls">
        {[
          {
            setting: settingX,
            id: "cs2.video.hud_edge_x",
            label: "Horizontal Adjustment",
            min: 0.5,
            max: 1.0,
            val: x,
            setVal: setX,
          },
          {
            setting: settingY,
            id: "cs2.video.hud_edge_y",
            label: "Vertical Adjustment",
            min: 0.8,
            max: 1.0,
            val: y,
            setVal: setY,
          },
        ].map((ctrl) => {
          const pinned = view.adaptive && view.state?.pins.includes(ctrl.id);
          const locked = view.adaptive && view.state?.locks.includes(ctrl.id);
          const isHl = highlight?.game === "cs2" && highlight.settingId === ctrl.id;
          return (
            <div
              key={ctrl.id}
              id={rowDomId(ctrl.id)}
              tabIndex={-1}
              data-setting-id={ctrl.id}
              data-control="slider"
              className={`setting-row cs2-hud-row ${isHl ? "is-highlighted" : ""} ${locked ? "is-locked" : ""}`}
            >
              <div className="row-label">
                <span className="row-label-text" id={`lbl-${rowDomId(ctrl.id)}`}>
                  {ctrl.setting?.exactLabel ?? ctrl.label}
                </span>
                {view.adaptive ? (
                  <span className="row-flags">
                    {pinned ? <span className="flag flag-pin" title="Pinned">📌</span> : null}
                    {locked ? <span className="flag flag-lock" title="Locked from AI changes">🔒</span> : null}
                  </span>
                ) : null}
                {view.adaptive ? (
                  <span className="row-tools">
                    <button type="button" className={`tool ${pinned ? "is-on" : ""}`} aria-pressed={pinned}
                      aria-label={`${pinned ? "Unpin" : "Pin"} ${ctrl.label}`} onClick={() => void togglePin("cs2", ctrl.id)}>
                      📌
                    </button>
                    <button type="button" className={`tool ${locked ? "is-on" : ""}`} aria-pressed={locked}
                      aria-label={`${locked ? "Unlock" : "Lock"} ${ctrl.label}`} onClick={() => void toggleLock("cs2", ctrl.id)}>
                      {locked ? "🔒" : "🔓"}
                    </button>
                    <button type="button" className="tool" aria-label={`Ask the assistant about ${ctrl.label}`}
                      onClick={() => prefill("cs2", `What does ${ctrl.label} do?`)}>
                      ?
                    </button>
                  </span>
                ) : null}
              </div>
              <div className="row-control">
                <div className="ctl-slider">
                  <span className="ctl-slider-value" style={{ textAlign: "center" }}>
                    {ctrl.val.toFixed(2)}
                  </span>
                  <input
                    className="ctl-slider-range"
                    type="range"
                    min={ctrl.min}
                    max={ctrl.max}
                    step={0.01}
                    value={ctrl.val}
                    aria-label={ctrl.label}
                    style={{ ["--fill" as string]: `${((ctrl.val - ctrl.min) / (ctrl.max - ctrl.min)) * 100}%` }}
                    onChange={(e) => ctrl.setVal(Number(e.target.value))}
                  />
                  <span className="ctl-slider-suffix">{Math.round(ctrl.val * 100)}%</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="cs2-hud-actions">
        <button
          type="button"
          className="cs2-btn"
          disabled={busy || (Math.abs(x - 1) < 1e-4 && Math.abs(y - 1) < 1e-4)}
          onClick={() => {
            setX(1.0);
            setY(1.0);
          }}
        >
          Reset Defaults
        </button>
        <button
          type="button"
          className="cs2-btn"
          disabled={!dirty || busy}
          onClick={() => {
            setX(committedX);
            setY(committedY);
          }}
        >
          Cancel
        </button>
        <button type="button" className="cs2-btn cs2-btn-primary" disabled={busy} onClick={() => void saveDone()}>
          Done
        </button>
      </div>
    </div>
  );
}
