import { useState } from "react";
import type { Value } from "../../api/types";

const COLOR_MAP: Record<string, string> = {
  white: "#FFFFFF",
  green: "#00FF00",
  yellow_green: "#7FFF00",
  green_yellow: "#CCFF00",
  yellow: "#FFFF00",
  cyan: "#00FFFF",
  pink: "#FF66FF",
  red: "#FF3B3B",
};

const BG_OPTIONS = [
  { id: "range", label: "Range (Sky)", bg: "linear-gradient(180deg, #6283a8 0%, #c6b89a 56%, #8b7b63 57%, #645845 100%)" },
  { id: "stone", label: "Ascent (Mid)", bg: "linear-gradient(180deg, #323c47 0%, #585f67 56%, #2a2e33 57%, #1c1f24 100%)" },
  { id: "dark", label: "Tunnel (Dark)", bg: "linear-gradient(180deg, #12171e 0%, #1e2630 56%, #14191f 57%, #0c0f14 100%)" },
];

export function ValorantCrosshairPreview({
  values,
  mode,
}: {
  values: Record<string, Value>;
  mode: "primary" | "ads" | "sniper";
}) {
  const [bgIdx, setBgIdx] = useState(0);
  const [simulateSpread, setSimulateSpread] = useState(false);

  const disabled = String(values["val.crosshair.disable_crosshair"] ?? "off") === "on";
  const adv = String(values["val.crosshair.use_advanced_options"] ?? "off") === "on";
  const effectiveMode = mode === "primary" || !adv ? "primary" : mode;

  const cx = 160;
  const cy = 76;

  if (disabled) {
    return (
      <div className="val-xhair-preview" style={{ background: BG_OPTIONS[bgIdx].bg }}>
        <div className="val-xhair-disabled">Crosshair Disabled</div>
        <div className="val-xhair-toolbar">
          <div className="val-xhair-bgs">
            {BG_OPTIONS.map((b, i) => (
              <button key={b.id} type="button" className={i === bgIdx ? "is-on" : ""} onClick={() => setBgIdx(i)}>
                {b.label}
              </button>
            ))}
          </div>
          <span className="val-xhair-caption">Simulated crosshair preview (illustrative approximation)</span>
        </div>
      </div>
    );
  }

  if (effectiveMode === "sniper") {
    const showDot = String(values["val.crosshair.sniper_center_dot"] ?? "on") === "on";
    const cKey = String(values["val.crosshair.sniper_dot_color"] ?? "red");
    const color =
      cKey === "custom"
        ? String(values["val.crosshair.sniper_dot_custom_color"] ?? "#FF0000")
        : COLOR_MAP[cKey] ?? "#FF3B3B";
    const dotOpacity = Number(values["val.crosshair.sniper_dot_opacity"] ?? 1);
    const dotSize = Math.max(0.5, Number(values["val.crosshair.sniper_dot_thickness"] ?? 1) * 2.5);

    return (
      <div className="val-xhair-preview" style={{ background: BG_OPTIONS[bgIdx].bg }} data-testid="val-crosshair-preview">
        <svg viewBox="0 0 320 152" role="img" aria-label="VALORANT Sniper Scope crosshair preview (simulated)">
          <rect x="0" y="0" width="320" height="152" fill="rgba(5,8,12,0.55)" />
          <circle cx={cx} cy={cy} r="62" fill="none" stroke="rgba(255,255,255,0.22)" strokeWidth="2" />
          <line x1={cx - 62} y1={cy} x2={cx + 62} y2={cy} stroke="rgba(10,12,16,0.9)" strokeWidth="1.5" />
          <line x1={cx} y1={cy - 62} x2={cx} y2={cy + 62} stroke="rgba(10,12,16,0.9)" strokeWidth="1.5" />
          {showDot ? <circle cx={cx} cy={cy} r={dotSize} fill={color} fillOpacity={dotOpacity} /> : null}
        </svg>
        <div className="val-xhair-toolbar">
          <div className="val-xhair-bgs">
            {BG_OPTIONS.map((b, i) => (
              <button key={b.id} type="button" className={i === bgIdx ? "is-on" : ""} onClick={() => setBgIdx(i)}>
                {b.label}
              </button>
            ))}
          </div>
          <span className="val-xhair-caption">Simulated Sniper Scope preview (illustrative)</span>
        </div>
      </div>
    );
  }

  const pfx = effectiveMode === "ads" ? "ads" : "primary";
  const colorKey = String(values[`val.crosshair.${pfx}_color`] ?? "white");
  const color =
    colorKey === "custom"
      ? String(values[`val.crosshair.${pfx}_custom_color`] ?? "#FFFFFF")
      : COLOR_MAP[colorKey] ?? "#FFFFFF";

  const outlines = String(values[`val.crosshair.${pfx}_outlines`] ?? "on") === "on";
  const outOpacity = Number(values[`val.crosshair.${pfx}_outline_opacity`] ?? 0.5);
  const outThick = Number(values[`val.crosshair.${pfx}_outline_thickness`] ?? 1);

  const centerDot = String(values[`val.crosshair.${pfx}_center_dot`] ?? "off") === "on";
  const dotOpacity = Number(values[`val.crosshair.${pfx}_center_dot_opacity`] ?? 1);
  const dotThick = Math.max(1, Number(values[`val.crosshair.${pfx}_center_dot_thickness`] ?? 2));

  const showInner = String(values[`val.crosshair.${pfx}_show_inner`] ?? "on") === "on";
  const inOp = Number(values[`val.crosshair.${pfx}_inner_opacity`] ?? 0.8);
  const inLen = Number(values[`val.crosshair.${pfx}_inner_length`] ?? 6);
  const inVLen = Number(values[`val.crosshair.${pfx}_inner_v_length`] ?? inLen);
  const inThick = Number(values[`val.crosshair.${pfx}_inner_thickness`] ?? 2);
  const inOffBase = Number(values[`val.crosshair.${pfx}_inner_offset`] ?? 3);
  const inErr =
    String(values[`val.crosshair.${pfx}_inner_movement_error`] ?? "off") === "on" ||
    String(values[`val.crosshair.${pfx}_inner_firing_error`] ?? "off") === "on";
  const inOff = inOffBase + (simulateSpread && inErr ? 8 : 0);

  const showOuter = String(values[`val.crosshair.${pfx}_show_outer`] ?? "on") === "on";
  const outLineOp = Number(values[`val.crosshair.${pfx}_outer_opacity`] ?? 0.35);
  const outLen = Number(values[`val.crosshair.${pfx}_outer_length`] ?? 2);
  const outLineThick = Number(values[`val.crosshair.${pfx}_outer_thickness`] ?? 2);
  const outOffBase = Number(values[`val.crosshair.${pfx}_outer_offset`] ?? 10);
  const outErr =
    String(values[`val.crosshair.${pfx}_outer_movement_error`] ?? "on") === "on" ||
    String(values[`val.crosshair.${pfx}_outer_firing_error`] ?? "on") === "on";
  const outOff = outOffBase + (simulateSpread && outErr ? 11 : 0);

  const fadeTop = simulateSpread && String(values["val.crosshair.fade_crosshair_firing_error"] ?? "off") === "on";

  const stroke = outlines ? `rgba(0,0,0,${outOpacity})` : "none";
  const sw = outlines ? outThick : 0;

  return (
    <div className="val-xhair-preview" style={{ background: BG_OPTIONS[bgIdx].bg }} data-testid="val-crosshair-preview">
      <svg viewBox="0 0 320 152" role="img" aria-label={`VALORANT ${effectiveMode} crosshair preview (simulated)`}>
        {showOuter && outLen > 0 && outLineThick > 0 ? (
          <g fill={color} fillOpacity={outLineOp} stroke={stroke} strokeWidth={sw}>
            {!fadeTop ? <rect x={cx - outLineThick / 2} y={cy - outOff - outLen} width={outLineThick} height={outLen} /> : null}
            <rect x={cx - outLineThick / 2} y={cy + outOff} width={outLineThick} height={outLen} />
            <rect x={cx - outOff - outLen} y={cy - outLineThick / 2} width={outLen} height={outLineThick} />
            <rect x={cx + outOff} y={cy - outLineThick / 2} width={outLen} height={outLineThick} />
          </g>
        ) : null}

        {showInner && inThick > 0 ? (
          <g fill={color} fillOpacity={inOp} stroke={stroke} strokeWidth={sw}>
            {!fadeTop && inVLen > 0 ? <rect x={cx - inThick / 2} y={cy - inOff - inVLen} width={inThick} height={inVLen} /> : null}
            {inVLen > 0 ? <rect x={cx - inThick / 2} y={cy + inOff} width={inThick} height={inVLen} /> : null}
            {inLen > 0 ? <rect x={cx - inOff - inLen} y={cy - inThick / 2} width={inLen} height={inThick} /> : null}
            {inLen > 0 ? <rect x={cx + inOff} y={cy - inThick / 2} width={inLen} height={inThick} /> : null}
          </g>
        ) : null}

        {centerDot ? (
          <rect
            x={cx - dotThick / 2}
            y={cy - dotThick / 2}
            width={dotThick}
            height={dotThick}
            fill={color}
            fillOpacity={dotOpacity}
            stroke={stroke}
            strokeWidth={sw}
          />
        ) : null}
      </svg>
      <div className="val-xhair-toolbar">
        <div className="val-xhair-bgs">
          {BG_OPTIONS.map((b, i) => (
            <button key={b.id} type="button" className={i === bgIdx ? "is-on" : ""} onClick={() => setBgIdx(i)}>
              {b.label}
            </button>
          ))}
        </div>
        <label className="val-xhair-spread">
          <input type="checkbox" checked={simulateSpread} onChange={(e) => setSimulateSpread(e.target.checked)} /> Test spread
        </label>
        <span className="val-xhair-caption">
          Simulated {effectiveMode.toUpperCase()} preview · not the Riot engine
        </span>
      </div>
    </div>
  );
}
