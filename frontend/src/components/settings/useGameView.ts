import { useMemo } from "react";
import type { GameId, Proposal, ProposalItem } from "../../api/types";
import { computeDisplayValues, useAppStore } from "../../store/useAppStore";

export interface StagedRef {
  proposal: Proposal;
  item: ProposalItem;
}

export function useGameView(game: GameId) {
  const catalog = useAppStore((s) => s.catalogs[game]);
  const state = useAppStore((s) => s.states[game]);
  const pending = useAppStore((s) => s.pendingVideo[game]);
  const byId = useAppStore((s) => s.byId[game]);
  const byKey = useAppStore((s) => s.byKey[game]);
  const proposals = useAppStore((s) => s.proposals[game]);
  const condition = useAppStore((s) => s.session?.condition);

  const values = useMemo(() => computeDisplayValues(state, pending, byId, byKey), [state, pending, byId, byKey]);
  const staged = useMemo(() => {
    const out: Record<string, StagedRef> = {};
    for (const p of proposals ?? []) {
      if (p.status !== "pending") continue;
      for (const item of p.items) if (item.status === "pending") out[item.settingId] = { proposal: p, item };
    }
    return out;
  }, [proposals]);

  return {
    game,
    catalog,
    state,
    values,
    pending: pending ?? {},
    byId: byId ?? {},
    byKey: byKey ?? {},
    staged,
    adaptive: condition === "adaptive",
    hardware: state?.hardware,
  };
}

export type GameView = ReturnType<typeof useGameView>;
