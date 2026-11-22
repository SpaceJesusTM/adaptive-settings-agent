import type { GameId, Setting, Value } from "../api/types";

export function displayValue(setting: Setting | undefined, value: Value | undefined | null): string {
  if (!setting) return String(value ?? "");
  if (value === undefined || value === null) return "–";
  if (setting.controlType === "dropdown" || setting.controlType === "segmented" || setting.controlType === "preset") {
    return setting.validOptions?.find((o) => o.value === String(value))?.label ?? String(value);
  }
  if (setting.controlType === "slider") {
    const n = Number(value);
    if (Number.isNaN(n)) return String(value);
    if (setting.display === "percent") return `${Math.round(n * 100)}%`;
    const dec = setting.precision ?? 2;
    const text = n.toFixed(dec);
    if (setting.unit === "%") return `${text}%`;
    return setting.unit ? `${text} ${setting.unit}` : text;
  }
  if (setting.controlType === "keybind") return value === "" ? "–" : String(value);
  return String(value);
}

export function sameValue(a: Value | undefined | null, b: Value | undefined | null): boolean {
  if (typeof a === "number" && typeof b === "number") return Math.abs(a - b) < 1e-9;
  return String(a) === String(b);
}

export function rowDomId(settingId: string): string {
  return `row-${settingId.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
}

export function gameName(game: GameId | string | null | undefined): string {
  return game === "valorant" ? "VALORANT" : game === "cs2" ? "CS2" : String(game ?? "");
}

export function timeAgo(iso: string): string {
  const t = new Date(iso).getTime();
  const diff = Math.max(0, Date.now() - t) / 1000;
  if (diff < 45) return "just now";
  if (diff < 3600) return `${Math.round(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)} h ago`;
  return new Date(iso).toLocaleDateString();
}

export function verificationLabel(status: string): string {
  switch (status) {
    case "verified-game-files":
      return "Verified in CS2 game files (build 2000948)";
    case "verified-official-doc":
      return "Verified in official Riot documentation";
    case "verified-official-screenshot":
      return "Verified in an official Riot menu screenshot";
    case "partially-verified":
      return "Partially verified (official + secondary sources)";
    case "secondary-only":
      return "Secondary sources only — not officially confirmed";
    default:
      return status;
  }
}

export function descriptionSourceLabel(source: string): string {
  switch (source) {
    case "official-tooltip":
      return "Valve's in-game tooltip";
    case "official-doc":
      return "Riot support documentation";
    case "official-notes":
      return "official patch/update notes";
    case "official-convar-help":
      return "Valve's console help text";
    default:
      return "prototype description (editorial)";
  }
}
