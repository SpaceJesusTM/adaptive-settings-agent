import { useState } from "react";
import type { Value } from "../../api/types";

const BACKGROUNDS = [
  "linear-gradient(180deg, #a9c3d8 0%, #d9cfb8 55%, #8c7a5c 56%, #6b5b42 100%)",
  "linear-gradient(180deg, #2e3640 0%, #4a4f58 60%, #24282e 61%, #191c20 100%)",
  "linear-gradient(180deg, #e8e4da 0%, #f4f1ea 50%, #b8b1a3 51%, #9a927f 100%)",
];

/** Live preview of CS2 crosshair using simulated style, size, gap, outline, color & alpha. */
export function CrosshairPreview({ values }: { values: Record<string, Value> }) {
  const [bg, setBg] = useState(0);
  const style = String(values["cs2.crosshair.xhair_style"] ?? "7");
  const t = Math.max(Number(values["cs2.crosshair.xhair_thickness"] ?? 2), 1);
  const len = Number(values["cs2.crosshair.xhair_length"] ?? 8);
  const gap = Number(values["cs2.crosshair.xhair_gap"] ?? 4);
  const dot = String(values["cs2.crosshair.xhair_center_dot"] ?? "0") === "1" || style === "6";
  const tStyle = String(values["cs2.crosshair.xhair_t"] ?? "0") === "1";
  const outline = String(values["cs2.crosshair.xhair_outline"] ?? "1");
  const color = String(values["cs2.crosshair.xhair_color_hex"] ?? "#00FF00");
  const alpha = Math.max(0, Math.min(255, Number(values["cs2.crosshair.xhair_alpha"] ?? 200))) / 255;

  const cx = 160;
  const cy = 90;
  const stroke = outline === "0" ? "none" : "#000";
  const sw = outline === "0" ? 0 : 1;

  const bars: { x: number; y: number; w: number; h: number; side: "top" | "bottom" | "left" | "right" }[] = [];
  const isCross = ["4", "0", "2", "5"].includes(style);
  if (isCross) {
    if (!tStyle) bars.push({ x: cx - t / 2, y: cy - gap - len, w: t, h: len, side: "top" });
    bars.push({ x: cx - t / 2, y: cy + gap, w: t, h: len, side: "bottom" });
    bars.push({ x: cx - gap - len, y: cy - t / 2, w: len, h: t, side: "left" });
    bars.push({ x: cx + gap, y: cy - t / 2, w: len, h: t, side: "right" });
  }
  const r = gap + len / 2;
  const quad = ["9", "7"].includes(style);

  return (
    <div className="cs2-xhair-preview" style={{ background: BACKGROUNDS[bg] }}>
      <svg viewBox="0 0 320 180" role="img" aria-label="Crosshair preview (simulated)">
        <g opacity={alpha}>
          {bars.map((b) => (
            <rect key={b.side} x={b.x} y={b.y} width={b.w} height={b.h} fill={color}
              stroke={outline === "2" && (b.side === "bottom" || b.side === "right") ? "none" : stroke} strokeWidth={sw} />
          ))}
          {["3", "1"].includes(style) ? <circle cx={cx} cy={cy} r={r} fill="none" stroke={color} strokeWidth={t} /> : null}
          {style === "8" ? <rect x={cx - r} y={cy - r} width={r * 2} height={r * 2} fill="none" stroke={color} strokeWidth={t} /> : null}
          {quad
            ? [[-1, -1], [1, -1], [-1, 1], [1, 1]].map(([sx, sy]) => (
                <path key={`${sx}${sy}`} d={`M ${cx + sx * gap} ${cy + sy * (gap + len)} L ${cx + sx * gap} ${cy + sy * gap} L ${cx + sx * (gap + len)} ${cy + sy * gap}`}
                  fill="none" stroke={color} strokeWidth={t} />
              ))
            : null}
          {dot ? <rect x={cx - t / 2} y={cy - t / 2} width={t} height={t} fill={color} stroke={stroke} strokeWidth={sw} /> : null}
        </g>
      </svg>
      <button type="button" className="cs2-xhair-arrow left" aria-label="Previous preview background" onClick={() => setBg((bg + BACKGROUNDS.length - 1) % BACKGROUNDS.length)}>‹</button>
      <button type="button" className="cs2-xhair-arrow right" aria-label="Next preview background" onClick={() => setBg((bg + 1) % BACKGROUNDS.length)}>›</button>
      <span className="cs2-xhair-caption">Preview (simplified, static — color &amp; alpha live)</span>
    </div>
  );
}
