// Client-side mirror of backend availability rules (the backend re-checks every change).
import type { Hardware, Setting, Value } from "../api/types";
import { displayValue, sameValue } from "./format";

export interface AvailabilityState {
  hidden: boolean;
  disabledReason: string | null;
}

export function availability(
  setting: Setting,
  byKey: Record<string, Setting>,
  values: Record<string, Value>,
  hardware: Hardware | undefined,
): AvailabilityState {
  const av = setting.availability ?? {};
  const req = av.requires;
  if (av.visibleWhen) {
    const target = byKey[av.visibleWhen.setting];
    const cur = target ? values[target.id] : undefined;
    if (!av.visibleWhen.values.some((v) => sameValue(cur, v))) return { hidden: true, disabledReason: null };
  }
  if (req?.gpuVendor && !req.gpuVendor.includes(hardware?.gpuVendor ?? "")) {
    return { hidden: false, disabledReason: `Not available on this simulated PC (needs a ${req.gpuVendor.join("/")} GPU).` };
  }
  if (req?.gsyncDisplay && !hardware?.gsyncDisplay) {
    return { hidden: false, disabledReason: "Not available on this simulated PC (needs a G-Sync display)." };
  }
  if (av.enabledWhen) {
    const target = byKey[av.enabledWhen.setting];
    const cur = target ? values[target.id] : undefined;
    if (!av.enabledWhen.values.some((v) => sameValue(cur, v))) {
      const wanted = av.enabledWhen.values.map((v) => displayValue(target, v)).join(", ");
      return { hidden: false, disabledReason: `Disabled until ${target?.exactLabel ?? av.enabledWhen.setting} is set to ${wanted}.` };
    }
  }
  return { hidden: false, disabledReason: null };
}

export function derivePreset(preset: Setting, byKey: Record<string, Setting>, values: Record<string, Value>): string {
  if (!preset.preset) return "custom";
  for (const [pval, mapping] of Object.entries(preset.preset.values)) {
    const ok = Object.entries(mapping).every(([member, mv]) => {
      const s = byKey[member];
      return s ? sameValue(values[s.id], mv) : false;
    });
    if (ok) return pval;
  }
  return "custom";
}
